"""Verbindet Engine, Bibliothek, Hotkeys und UI."""
from __future__ import annotations

import logging
import random
import threading

from PySide6.QtCore import QObject, Signal

from .capture import SourceManager
from .config import Config
from .hotkeys import HotkeyManager, pretty
from .library import ClipLibrary, SoundLibrary
from .effects import VOICE_PRESETS, voice_name
from .mixer import Mixer

log = logging.getLogger("soundclip")

ACTION_NAMES = {
    "clip": "Clip speichern (letzte X Sekunden)",
    "record": "Aufnahme starten/stoppen",
    "stop_all": "Alle Sounds stoppen",
    "overlay": "Overlay ein/aus",
    "passthrough": "Stimme an Discord ein/aus",
    "voice_toggle": "Stimmeffekt ein/aus",
    "voice_next": "Nächster Stimmeffekt",
    "voice_up": "Stimmeffekt stärker",
    "voice_down": "Stimmeffekt schwächer",
    "voice_hold": "Stimmeffekt nur solange gedrückt",
    "random_sound": "Zufälliger Sound",
}


class Controller(QObject):
    toast = Signal(str, str)            # text, art (info|ok|rec|warn)
    clipsChanged = Signal(str)          # id des neuen Clips ("" = nur neu laden)
    soundsChanged = Signal()
    recordingChanged = Signal(bool)
    overlayToggled = Signal(bool)
    settingsChanged = Signal()
    voiceChanged = Signal()
    shareReady = Signal(str)            # Datei fuer die Zwischenablage (aus Hintergrund-Thread)
    updateFound = Signal(dict)          # neue Version auf GitHub
    remoteCommand = Signal(str)         # Befehl vom Handy / Stream Deck (aus dem Server-Thread)
    triggerFired = Signal(str)          # Sprach-Trigger hat einen Sound erkannt
    autoClipFire = Signal()             # Auto-Clip: jetzt clippen

    def __init__(self):
        super().__init__()
        self.cfg = Config()
        from .effects import load_customs
        load_customs(self.cfg["custom_voices"])
        self.mixer = Mixer(self.cfg)
        self.sources = SourceManager(self.cfg, self.mixer)
        self.sounds = SoundLibrary()
        self.clips = ClipLibrary()
        self.hotkeys = HotkeyManager()
        self.hotkeys.triggered.connect(self._on_hotkey)
        self.hotkey_errors: list[str] = []
        self.shareReady.connect(self._copy_share)
        self._ducked = False
        self._duck_quiet_since = 0.0
        self._last_random = ""
        from .autoclip import AutoClip
        from .remote import RemoteServer
        from .triggers import VoiceTriggers
        self.autoclip = AutoClip(self.cfg, self.autoClipFire.emit)
        self.triggers = VoiceTriggers(self.cfg, self.sounds, self.triggerFired.emit)
        self.sources.listeners = [self.autoclip.on_chunk, self.triggers.on_chunk]
        self.remote = RemoteServer(self)
        self.remoteCommand.connect(self.run_command)
        self.triggerFired.connect(self.play_sound)
        self.autoClipFire.connect(lambda: self.clip_now(auto=True))

    def start(self):
        try:
            self.mixer.reopen()
        except Exception as e:
            log.exception("Mixer")
            self.toast.emit(f"Audio-Ausgabe: {e}", "warn")
        self.sources.start()
        self.apply_hotkeys()
        from PySide6.QtCore import QTimer
        self._duck_timer = QTimer(self)
        self._duck_timer.timeout.connect(self._duck_tick)
        self._duck_timer.start(80)
        self.check_updates(auto=True)
        try:
            self.remote.sync()
        except Exception:
            log.exception("Fernbedienung")
        self.triggers.sync()

    def shutdown(self):
        self.remote.stop()
        self.triggers.stop()
        self.autoclip.stop()
        self.hotkeys.shutdown()
        self.sources.shutdown()
        self.mixer.close()

    # ---------------------------------------------------------- Hotkeys
    def apply_hotkeys(self):
        mapping = {f"action:{k}": v for k, v in self.cfg["hotkeys"].items()}
        for s in self.sounds.sounds:
            if s.get("hotkey"):
                mapping[f"sound:{s['id']}"] = s["hotkey"]
        for preset, combo in (self.cfg["voice_hotkeys"] or {}).items():
            if combo:
                mapping[f"voice:{preset}"] = combo
        self.hotkey_errors = self.hotkeys.set_bindings(mapping)
        for err in self.hotkey_errors:
            self.toast.emit("Hotkey-Problem: " + err, "warn")

    def _on_hotkey(self, name: str):
        kind, _, arg = name.partition(":")
        if kind == "sound":
            self.play_sound(arg)
        elif kind == "voice":
            if self.cfg["voice_enabled"] and self.cfg["voice_preset"] == arg:
                self.set_voice(enabled=False)
            else:
                self.set_voice(arg, True)
        elif arg.startswith("voice_hold:"):
            down = arg.endswith(":down")
            if bool(self.cfg["voice_enabled"]) != down:
                self.set_voice(enabled=down, quiet=True)
        elif arg == "voice_toggle":
            self.set_voice(enabled=not self.cfg["voice_enabled"])
        elif arg in ("voice_up", "voice_down"):
            step = 0.1 if arg == "voice_up" else -0.1
            new = min(1.0, max(0.0, round(self.voice_amount() + step, 2)))
            self.set_voice(amount=new, quiet=True)
            if not self.cfg["voice_enabled"]:
                self.set_voice(enabled=True, quiet=True)
            self.toast.emit(f"🎭 {voice_name(self.cfg['voice_preset'])}: Stärke {int(new * 100)} %", "info")
        elif arg == "voice_next":
            keys = list(VOICE_PRESETS)
            cur = self.cfg["voice_preset"]
            nxt = keys[(keys.index(cur) + 1) % len(keys)] if cur in keys else keys[0]
            self.set_voice(nxt, True)
        elif arg == "clip":
            self.clip_now()
        elif arg == "random_sound":
            self.play_random()
        elif arg == "record":
            self.toggle_recording()
        elif arg == "stop_all":
            self.stop_all()
        elif arg == "overlay":
            self.cfg["overlay_enabled"] = not self.cfg["overlay_enabled"]
            self.overlayToggled.emit(self.cfg["overlay_enabled"])
        elif arg == "passthrough":
            self.cfg["mic_passthrough"] = not self.cfg["mic_passthrough"]
            self.mixer.live.clear()
            self.mixer.apply_voice_path()
            self.sources.poke()
            self.toast.emit("Mikro-Durchleitung " + ("AN" if self.cfg["mic_passthrough"] else "AUS"), "info")
            self.settingsChanged.emit()

    # ---------------------------------------------------------- Aktionen
    def play_sound(self, sid: str):
        s = self.sounds.get(sid)
        if not s:
            return
        try:
            data = self.sounds.audio(s)
        except Exception as e:
            self.toast.emit(f"„{s['name']}“ kann nicht geladen werden: {e}", "warn")
            return
        gain = self.sounds.gain_for(s, data, bool(self.cfg["normalize_sounds"]))
        v = self.mixer.play(data, gain=gain, sound_id=sid, name=s["name"])
        if v is None and not self.mixer.active_targets():
            self.toast.emit("Keine Audio-Ausgabe aktiv – siehe Einstellungen", "warn")
        elif v is not None:
            self.toast.emit("▶ " + s["name"], "info")

    def play_random(self, folder: str = ""):
        """Zufaelligen Sound abspielen (optional nur aus einem Ordner, "*fav" = Favoriten)."""
        pool = [s for s in self.sounds.sounds
                if not folder or (folder == "*fav" and s.get("fav")) or s.get("folder", "") == folder]
        if not pool:
            self.toast.emit("Keine Sounds für Zufall da", "warn")
            return
        choices = [s for s in pool if s["id"] != self._last_random] or pool
        s = random.choice(choices)
        self._last_random = s["id"]
        self.play_sound(s["id"])

    # ---------------------------------------------------------- Fernbedienung
    def remote_command_ok(self, cmd: str) -> bool:
        if cmd in ("stop", "clip", "record", "random", "voice/toggle"):
            return True
        if cmd.startswith("random:"):
            return True
        if cmd.startswith("play/"):
            return self.sounds.get(cmd[5:]) is not None
        if cmd.startswith("voice/set/"):
            return cmd[10:] in VOICE_PRESETS
        return False

    def run_command(self, cmd: str):
        """Befehl von Handy/Stream Deck ausfuehren (laeuft im GUI-Thread)."""
        if cmd.startswith("play/"):
            self.play_sound(cmd[5:])
        elif cmd == "stop":
            self.stop_all()
        elif cmd == "random" or cmd.startswith("random:"):
            self.play_random(cmd.partition(":")[2])
        elif cmd == "clip":
            self.clip_now()
        elif cmd == "record":
            self.toggle_recording()
        elif cmd == "voice/toggle":
            self.set_voice(enabled=not self.cfg["voice_enabled"])
        elif cmd.startswith("voice/set/") and cmd[10:] in VOICE_PRESETS:
            self.set_voice(cmd[10:], True)

    def remote_state(self) -> dict:
        from .i18n import tr
        playing = {v.sound_id for v in self.mixer.playing()}
        sounds = sorted(self.sounds.sounds, key=lambda s: not s.get("fav"))
        return {
            "sounds": [{"id": s["id"], "name": s["name"], "color": s.get("color", ""), "folder": s.get("folder", ""),
                        "fav": bool(s.get("fav")), "playing": s["id"] in playing} for s in sounds],
            "folders": self.sounds.folders(self.cfg["sound_folders"] or []),
            "voice": {"enabled": bool(self.cfg["voice_enabled"]), "preset": self.cfg["voice_preset"]},
            "presets": [{"key": k, "name": f"{VOICE_PRESETS[k][0]} {tr(voice_name(k))}"} for k in list(VOICE_PRESETS)],
            "recording": bool(self.sources.recording),
        }

    def remote_now(self) -> dict:
        from .i18n import tr
        playing = [{"name": v.name, "progress": round(v.progress(), 3)} for v in self.mixer.playing()
                   if v.sound_id not in ("__preview__", "__test__")]
        return {"playing": playing, "recording": bool(self.sources.recording),
                "voice": tr(voice_name(self.cfg["voice_preset"])) if self.cfg["voice_enabled"] else ""}

    def play_data(self, data, name="Vorschau", preview=True, sound_id="__preview__"):
        return self.mixer.play(data, sound_id=sound_id, name=name, preview=preview)

    def stop_all(self):
        self.mixer.stop_all()
        self.toast.emit("■ Alle Sounds gestoppt", "info")

    def clip_now(self, seconds=None, auto: bool = False):
        sec = seconds or self.cfg["buffer_seconds"]

        def work():
            try:
                meta = self.sources.make_clip(sec)
            except Exception as e:
                log.exception("clip")
                self.toast.emit(f"Clip fehlgeschlagen: {e}", "warn")
                return
            if meta is None:
                if not auto:
                    self.toast.emit("Clip: in den letzten Sekunden war alles still", "warn")
                return
            names = ", ".join(st["label"] for st in meta["stems"])
            if auto:
                meta["name"] = "Auto-" + meta["name"]
                try:
                    self.clips.save_meta(meta)
                except Exception:
                    log.exception("Auto-Clip")
                self.toast.emit(f"🔥 Auto-Clip gespeichert ({sec:g}s): {names}", "ok")
            else:
                self.toast.emit(f"✂ Clip gespeichert ({sec:g}s): {names}", "ok")
            self.clipsChanged.emit(meta["id"])
            if self.cfg["clip_autocopy"]:
                try:
                    from .library import render
                    from .share import encode
                    data = render(meta, self.clips.stems(meta), meta.get("edit") or {})
                    self.shareReady.emit(str(encode(data, meta["name"])))
                except Exception:
                    log.exception("Clip teilen")

        threading.Thread(target=work, daemon=True).start()

    def toggle_recording(self, keys=None):
        if self.sources.recording:
            self.stop_recording()
        else:
            self.start_recording(keys)

    def start_recording(self, keys=None):
        if self.sources.start_recording(keys):
            what = "alle Quellen"
            if keys or self.cfg["record_sources"]:
                ks = keys or self.cfg["record_sources"]
                labels = [self.sources.available.get(k, {}).get("label", k) for k in ks]
                what = ", ".join(labels)
            self.toast.emit(f"● Aufnahme läuft: {what}", "rec")
            self.recordingChanged.emit(True)

    def stop_recording(self):
        meta = self.sources.stop_recording()
        self.recordingChanged.emit(False)
        if meta:
            self.toast.emit(f"■ Aufnahme gespeichert ({meta['duration']:.0f}s)", "ok")
            self.clipsChanged.emit(meta["id"])
        else:
            self.toast.emit("Aufnahme verworfen (nur Stille)", "warn")

    def set_voice(self, preset: str | None = None, enabled: bool | None = None, amount: float | None = None,
                  quiet: bool = False):
        if preset is not None:
            self.cfg["voice_preset"] = preset
        if enabled is not None:
            self.cfg["voice_enabled"] = bool(enabled)
        if amount is not None:
            amts = dict(self.cfg["voice_amounts"] or {})
            amts[self.cfg["voice_preset"]] = round(float(amount), 3)
            self.cfg.update(voice_amounts=amts, voice_amount=float(amount))
        self.mixer.apply_voice()
        if preset is not None or enabled is not None:
            self.sources.poke()
        self.voiceChanged.emit()
        if quiet:
            return
        if self.cfg["voice_enabled"]:
            msg = f"🎭 Stimme: {voice_name(self.cfg['voice_preset'])} ({int(self.voice_amount() * 100)} %)"
            if not self.cfg["mic_passthrough"] and not self.cfg["voice_monitor"]:
                msg += " – Achtung: „Stimme an Discord“ ist aus"
            self.toast.emit(msg, "info")
        else:
            self.toast.emit("🎭 Stimmeffekt aus", "info")

    # ---------------------------------------------------------- Teilen / Ducking / Updates
    def _copy_share(self, path: str):
        from .share import copy_file, too_big
        copy_file(path)
        if too_big(path):
            self.toast.emit("Clip ist größer als 10 MB – Discord nimmt ihn evtl. nicht", "warn")
        else:
            self.toast.emit("📋 Clip kopiert – in Discord mit Strg+V einfügen", "ok")

    def _duck_tick(self):
        import time as _t
        want = False
        if self.cfg["duck_enabled"]:
            for v in self.mixer.playing():
                if "monitor" in v.pos and "monitor" not in v.done:
                    want = True
                    break
        now = _t.time()
        if want:
            self._duck_quiet_since = 0.0
            if not self._ducked:
                skip = [] if self.cfg["duck_discord"] else ["discord.exe", "discordptb.exe", "discordcanary.exe"]
                from .host import HelperHost
                HelperHost.get().command(f"duck {float(self.cfg['duck_level']):.2f} {','.join(skip) or '-'}")
                self._ducked = True
        elif self._ducked:
            if not self._duck_quiet_since:
                self._duck_quiet_since = now
            elif now - self._duck_quiet_since > 0.35:
                from .host import HelperHost
                HelperHost.get().command("unduck")
                self._ducked = False

    def check_updates(self, auto: bool = False):
        """Im Hintergrund auf GitHub nach einer neuen Version schauen (automatisch hoechstens 1x am Tag)."""
        import time as _t
        if auto and (not self.cfg["update_check"] or _t.time() - float(self.cfg["last_update_check"] or 0) < 86400):
            return

        def work():
            from . import updater
            try:
                info = updater.check()
            except Exception as e:
                log.info("Update-Pruefung: %s", e)
                if not auto:
                    self.toast.emit("Update-Prüfung fehlgeschlagen (offline?)", "warn")
                return
            self.cfg["last_update_check"] = _t.time()
            if info:
                self.updateFound.emit(info)
            elif not auto:
                self.toast.emit("Du hast die neueste Version", "ok")

        threading.Thread(target=work, daemon=True).start()

    def voice_amount(self, preset: str | None = None) -> float:
        pre = preset or self.cfg["voice_preset"]
        return float((self.cfg["voice_amounts"] or {}).get(pre, 0.5))

    def set_action_hotkey(self, action: str, combo: str):
        hk = dict(self.cfg["hotkeys"])
        hk[action] = combo
        self.cfg["hotkeys"] = hk
        self.apply_hotkeys()
        self.settingsChanged.emit()

    def hotkey_text(self, action: str) -> str:
        return pretty(self.cfg["hotkeys"].get(action, ""))
