"""Verbindet Engine, Bibliothek, Hotkeys und UI."""
from __future__ import annotations

import json
import logging
import random
import threading
import time

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
    "wheel_hold": "Sound-Rad (gedrückt halten)",
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
    updateFound = Signal(dict)          # neue Version auf GitHub (Modus "fragen" oder manuelle Pruefung)
    updateReady = Signal(str)           # Modus "automatisch": Update geladen, wartet auf ruhigen Moment
    installUpdate = Signal(str)         # jetzt installieren (Pfad zum Installer)
    remoteCommand = Signal(str)         # Befehl vom Handy / Stream Deck (aus dem Server-Thread)
    triggerFired = Signal(str)          # Sprach-Trigger hat einen Sound erkannt
    autoClipFire = Signal()             # Auto-Clip: jetzt clippen
    voiceCommand = Signal(str, object, str)   # Sprachbefehl: Aktion, Quellen, Anzeigename
    announceReady = Signal(object, bool)      # fertige Ansage: Audio, auch an Discord?
    speechReady = Signal(object, str)         # vorgelesener Text (vom Handy): Audio, Text
    wheelHold = Signal(bool)                  # Sound-Rad: Taste gedrueckt / losgelassen
    profileFound = Signal(str)                # Spiel erkannt (aus dem Hintergrund-Thread): Profil-id oder ""
    profileChanged = Signal(dict)             # aktives Profil ({} = Standard)
    wheelChanged = Signal()                   # Sound-Rad-Seiten geaendert

    def __init__(self):
        super().__init__()
        self.cfg = Config()
        from .effects import load_customs
        load_customs(self.cfg["custom_voices"])
        self.mixer = Mixer(self.cfg)
        self.sources = SourceManager(self.cfg, self.mixer)
        self.sounds = SoundLibrary()
        self.clips = ClipLibrary()
        from .stats import Stats
        self.stats = Stats()
        self._voice_tick = 0.0
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
        from .announce import Announcer
        self.announcer = Announcer(self)
        self.triggers = VoiceTriggers(self.cfg, self.sounds, self.triggerFired.emit,
                                      command=self.voiceCommand.emit, apps=self.app_labels)
        from .earguard import EarGuard
        self.guard = EarGuard(self.cfg, self._helper_cmd, self._duck_factor)
        self.sources.listeners = [self.guard.on_chunk, self.autoclip.on_chunk, self.triggers.on_chunk,
                                  self._activity]
        self.remote = RemoteServer(self)
        self.remoteCommand.connect(self.run_command)
        self.triggerFired.connect(self.play_sound)
        self.triggerFired.connect(lambda _sid: self.stats.add("triggers"))
        self.autoClipFire.connect(lambda: self.clip_now(auto=True))
        self.voiceCommand.connect(self.run_voice_command)
        self.announceReady.connect(self._play_announce)
        self.speechReady.connect(lambda data, text: self.mixer.play(data, sound_id="__tts__", name=text[:40],
                                                                    preview=False))
        self._rec_since = 0.0
        self.profile: dict | None = None
        self._profile_voice: tuple | None = None
        from .profiles import ProfileWatcher
        self.profile_watch = ProfileWatcher(self.cfg, self.profileFound.emit)
        self.profileFound.connect(self._profile_found)
        self._tts_voices: list | None = None
        self.pending_update: str = ""      # fertig geladener Installer (Modus automatisch)
        self._update_busy = False
        self._last_busy = 0.0

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
        from PySide6.QtCore import QTimer
        self._upd_timer = QTimer(self)          # auch waehrend die App laeuft regelmaessig nachschauen
        self._upd_timer.timeout.connect(lambda: self.check_updates(auto=True))
        self._upd_timer.start(30 * 60 * 1000)
        self._idle_timer = QTimer(self)         # geladenes Update in einem ruhigen Moment installieren
        self._idle_timer.timeout.connect(self._idle_install)
        self._idle_timer.start(20 * 1000)
        self._stats_timer = QTimer(self)        # Statistik ab und zu wegschreiben
        self._stats_timer.timeout.connect(self.stats.save)
        self._stats_timer.start(60 * 1000)
        self._resume_pending_update()
        try:
            self.remote.sync()
        except Exception:
            log.exception("Fernbedienung")
        self.triggers.sync()
        if self.cfg["profile_manual"]:
            self.set_profile(self.cfg["profile_manual"])
        self.profile_watch.start()

    def shutdown(self):
        self.stats.save()
        self.profile_watch.stop()
        if self._profile_voice is not None:     # Stimme vom Profil nicht dauerhaft gespeichert lassen
            en, pre = self._profile_voice
            self.cfg.update(voice_enabled=en, voice_preset=pre)
        self.remote.stop()
        self.triggers.stop()
        self.autoclip.stop()
        self.hotkeys.shutdown()
        self.sources.shutdown()
        self.mixer.close()

    # ---------------------------------------------------------- Hotkeys
    def apply_hotkeys(self):
        mapping = {f"action:{k}": v for k, v in self.cfg["hotkeys"].items()}
        folder = (self.profile or {}).get("folder", "")
        for s in self.sounds.sounds:
            if folder and not ((folder == "*fav" and s.get("fav")) or s.get("folder", "") == folder):
                continue                        # Profil: nur die Sounds aus seinem Ordner
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
        elif arg.startswith("wheel_hold:"):
            self.wheelHold.emit(arg.endswith(":down"))
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

    # ---------------------------------------------------------- Profile pro Spiel
    def profiles(self) -> list[dict]:
        from .profiles import clean
        return [clean(p) for p in (self.cfg["profiles"] or [])]

    def save_profiles(self, profs: list[dict]):
        self.cfg["profiles"] = profs
        if self.cfg["profile_manual"] and not any(p["id"] == self.cfg["profile_manual"] for p in profs):
            self.cfg["profile_manual"] = ""
        cur = (self.profile or {}).get("id", "")
        if cur and not any(p["id"] == cur for p in profs):
            cur = ""
        self.set_profile(cur, force=True)
        self.profile_watch.poke()

    def _profile_found(self, pid: str):
        if not self.cfg["profile_manual"]:
            self.set_profile(pid)

    def choose_profile(self, pid: str):
        """Von Hand waehlen ("" = wieder automatisch)."""
        self.cfg["profile_manual"] = pid
        if pid:
            self.set_profile(pid)
        else:
            self.set_profile("")
            self.profile_watch.poke()

    def wheel_source(self) -> str:
        return (self.profile or {}).get("wheel_source") or self.cfg.get("wheel_source", "fav")

    def save_wheel(self, pages: list[dict], use: bool = True):
        """Eigene Rad-Seiten speichern; use=True schaltet das Rad auf "Eigene Auswahl"."""
        from .ui.wheel import clean_pages
        pages = clean_pages(pages)
        filled = any(any(pg["slots"]) for pg in pages)
        self.cfg["wheel_pages"] = pages
        if use and filled:
            self.cfg["wheel_source"] = "custom"
        elif not filled and str(self.cfg.get("wheel_source", "")).startswith(("custom", "page:")):
            self.cfg["wheel_source"] = "fav"
        self.wheelChanged.emit()

    def wheel_add(self, sid: str, page: int | None) -> str:
        """Sound ins erste freie Feld einer Seite legen (page=None: neue Seite). Gibt die Seite zurueck."""
        from .ui.wheel import MAX_ITEMS, MAX_PAGES, clean_pages
        pages = clean_pages(self.cfg.get("wheel_pages"))
        if page is None or page >= len(pages):
            if len(pages) >= MAX_PAGES:
                self.toast.emit("Sound-Rad: höchstens 8 Seiten", "warn")
                return ""
            from .i18n import tr
            pages.append({"name": tr("Seite {n}").format(n=len(pages) + 1), "slots": [""] * MAX_ITEMS})
            page = len(pages) - 1
        slots = pages[page]["slots"]
        name = pages[page]["name"]
        if sid in slots:
            self.toast.emit(f"Schon auf dem Sound-Rad: {name}", "info")
            return name
        if "" not in slots:
            self.toast.emit(f"{name} ist voll – im Sound-Rad-Editor Platz machen", "warn")
            return ""
        slots[slots.index("")] = sid
        self.save_wheel(pages)
        self.toast.emit(f"🎡 Aufs Sound-Rad gelegt: {name}", "ok")
        return name

    def set_profile(self, pid: str, force: bool = False):
        prof = next((p for p in self.profiles() if p["id"] == pid), None) if pid else None
        if not force and (prof or {}).get("id") == (self.profile or {}).get("id"):
            return
        if self._profile_voice is not None:          # Stimme vom vorigen Profil zuruecknehmen
            en, pre = self._profile_voice
            self._profile_voice = None
            self.set_voice(pre, en, quiet=True)
        self.profile = prof
        if prof and prof.get("voice"):
            from .effects import VOICE_PRESETS
            self._profile_voice = (bool(self.cfg["voice_enabled"]), self.cfg["voice_preset"])
            if prof["voice"] == "off":
                self.set_voice(enabled=False, quiet=True)
            elif prof["voice"] in VOICE_PRESETS:
                self.set_voice(prof["voice"], True, quiet=True)
        self.apply_hotkeys()
        self.profileChanged.emit(dict(prof or {}))
        if not force:
            self.toast.emit(f"🎮 Profil: {prof['name']}" if prof else "🎮 Profil: Standard", "info")

    # ---------------------------------------------------------- Aktionen
    def play_sound(self, sid: str):
        s = self.sounds.get(sid)
        if not s:
            return
        try:
            data, gain = self.sounds.playable(s, bool(self.cfg["normalize_sounds"]))
        except Exception as e:
            self.toast.emit(f"„{s['name']}“ kann nicht geladen werden: {e}", "warn")
            return
        v = self.mixer.play(data, gain=gain, sound_id=sid, name=s["name"])
        if v is None and not self.mixer.active_targets():
            self.toast.emit("Keine Audio-Ausgabe aktiv – siehe Einstellungen", "warn")
        elif v is not None:
            self.toast.emit("▶ " + s["name"], "info")
            self.stats.sound(sid, s["name"])

    # ---------------------------------------------------------- Sprachbefehle & Ansage
    def app_labels(self) -> dict:
        """Aktuell verfuegbare Quellen: Schluessel -> Anzeigename (auch aus Hintergrund-Threads lesbar)."""
        try:
            return {k: str(v.get("label") or k) for k, v in dict(self.sources.available).items()}
        except Exception:
            return {}

    def run_voice_command(self, action: str, keys, label: str):
        keys = list(keys) if keys else None
        self.stats.add("voice_cmds")
        if action == "clip":
            self.toast.emit(f"🗣 Clip: {label}" if keys else "🗣 Clip!", "info")
            self.clip_now(keys=keys, label=label)
        elif action == "rec_start":
            if self.sources.recording:
                self.toast.emit("Es läuft schon eine Aufnahme", "warn")
            else:
                self.start_recording(keys)
        elif action == "rec_stop":
            if self.sources.recording:
                self.stop_recording()
            else:
                self.toast.emit("Es läuft gerade keine Aufnahme", "warn")
        elif action == "stop":
            self.stop_all()

    def _play_announce(self, data, to_all: bool):
        try:
            self.mixer.play(data, sound_id="__announce__", name="Ansage", preview=not to_all)
        except Exception:
            log.exception("Ansage")

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
    def _keys_ok(self, csv: str) -> list[str] | None:
        keys = [k for k in csv.split(",") if k]
        avail = self.app_labels()
        return keys if keys and all(k in avail for k in keys) else None

    def remote_command_ok(self, cmd: str) -> bool:
        if cmd in ("stop", "clip", "record", "random", "voice/toggle", "record/stop"):
            return True
        if cmd.startswith("random:"):
            return True
        if cmd.startswith(("clip:", "record:")):
            return self._keys_ok(cmd.partition(":")[2]) is not None
        if cmd.startswith("say:"):
            try:
                d = json.loads(cmd[4:])
                return isinstance(d, dict) and 0 < len(str(d.get("text", "")).strip()) <= 300
            except ValueError:
                return False
        if cmd.startswith("voice/amount/"):
            return cmd[13:].isdigit() and 0 <= int(cmd[13:]) <= 100
        if cmd.startswith("play/"):
            return self.sounds.get(cmd[5:]) is not None
        if cmd.startswith("voice/set/"):
            return cmd[10:] in VOICE_PRESETS
        return False

    def run_command(self, cmd: str):
        """Befehl von Handy/Stream Deck ausfuehren (laeuft im GUI-Thread)."""
        if cmd.startswith(("play/", "random")):
            self.stats.add("remote")
        if cmd.startswith("play/"):
            self.play_sound(cmd[5:])
        elif cmd == "stop":
            self.stop_all()
        elif cmd == "random" or cmd.startswith("random:"):
            self.play_random(cmd.partition(":")[2])
        elif cmd == "clip":
            self.clip_now()
        elif cmd.startswith("clip:"):
            keys = self._keys_ok(cmd[5:])
            if keys:
                labels = self.app_labels()
                self.clip_now(keys=keys, label=", ".join(labels[k] for k in keys))
        elif cmd == "record":
            self.toggle_recording()
        elif cmd == "record/stop":
            if self.sources.recording:
                self.stop_recording()
        elif cmd.startswith("record:"):
            if self.sources.recording:
                self.stop_recording()
            else:
                self.start_recording(self._keys_ok(cmd[7:]))
        elif cmd.startswith("say:"):
            d = json.loads(cmd[4:])
            self.speak(str(d.get("text", ""))[:300], str(d.get("voice") or ""), bool(d.get("fx")))
        elif cmd.startswith("voice/amount/"):
            self.set_voice(amount=int(cmd[13:]) / 100.0)
        elif cmd == "voice/toggle":
            self.set_voice(enabled=not self.cfg["voice_enabled"])
        elif cmd.startswith("voice/set/") and cmd[10:] in VOICE_PRESETS:
            self.set_voice(cmd[10:], True)

    def speak(self, text: str, voice: str = "", fx: bool = False):
        """Text vorlesen – hoeren man selbst und Discord (vom Handy aus)."""
        text = text.strip()
        if not text:
            return

        def work():
            from . import tts
            from .mixer import load_audio
            import os
            try:
                path = tts.synth(text, voice)
                data = load_audio(path)
                try:
                    os.remove(path)
                except Exception:
                    pass
                pre = VOICE_PRESETS.get(self.cfg["voice_preset"]) if fx else None
                if pre:
                    from .effects import apply_chain
                    scale = 0.4 + 1.2 * self.voice_amount()
                    data = apply_chain(data, [{"type": k, "amount": min(1.0, a * scale)} for k, a in pre[1]])
                self.speechReady.emit(data, text)
                self.stats.add("tts")
            except Exception as e:
                log.exception("Vorlesen")
                self.toast.emit(f"Vorlesen fehlgeschlagen: {e}", "warn")
        threading.Thread(target=work, daemon=True).start()
        self.toast.emit("🗣 Wird vorgelesen …", "info")

    def tts_voices(self) -> list:
        """Windows-Stimmen (beim ersten Mal im Hintergrund geholt, bis dahin leer)."""
        if self._tts_voices is None:
            self._tts_voices = []

            def load():
                from . import tts
                try:
                    out = []
                    for v in tts.voices():
                        short = v["name"].replace("Microsoft ", "").replace(" Desktop", "")
                        out.append({"name": v["name"], "label": f"{short} ({v.get('culture', '')})"})
                    self._tts_voices = out
                except Exception:
                    log.exception("Stimmen")
            threading.Thread(target=load, daemon=True).start()
        return self._tts_voices

    def remote_state(self) -> dict:
        from . import i18n
        from .i18n import tr
        playing = {v.sound_id for v in self.mixer.playing()}
        sounds = sorted(self.sounds.sounds, key=lambda s: not s.get("fav"))
        labels = self.app_labels()
        rec = self.sources.recording
        return {
            "theme": self.cfg["ui_theme"], "now": time.time(),
            "apps": [{"key": k, "label": (("Mikrofon" if i18n.LANG == "de" else "Microphone") if k == "mic" else v)}
                     for k, v in sorted(labels.items(), key=lambda kv: (kv[0] != "mic", kv[1].lower()))],
            "rec": {"active": bool(rec), "since": self._rec_since if rec else 0,
                    "keys": sorted(rec.get("keys") or []) if rec else []},
            "tts": self.tts_voices(),
            "amount": int(round(self.voice_amount() * 100)),
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
                   if v.sound_id not in ("__preview__", "__test__", "__announce__", "__tts__")]
        return {"playing": playing, "recording": bool(self.sources.recording),
                "voice": tr(voice_name(self.cfg["voice_preset"])) if self.cfg["voice_enabled"] else ""}

    def play_data(self, data, name="Vorschau", preview=True, sound_id="__preview__"):
        return self.mixer.play(data, sound_id=sound_id, name=name, preview=preview)

    def stop_all(self):
        self.mixer.stop_all()
        self.toast.emit("■ Alle Sounds gestoppt", "info")

    def clip_now(self, seconds=None, auto: bool = False, keys=None, label: str = ""):
        sec = seconds or self.cfg["buffer_seconds"]

        def work():
            try:
                meta = self.sources.make_clip(sec, keys=set(keys) if keys else None)
            except Exception as e:
                log.exception("clip")
                self.toast.emit(f"Clip fehlgeschlagen: {e}", "warn")
                return
            if meta is None:
                if keys and not auto:
                    self.toast.emit(f"Clip: {label or ', '.join(keys)} war in den letzten Sekunden still", "warn")
                elif not auto:
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
            self.announcer.say("auto" if auto else "clip")
            self.stats.add("autoclips" if auto else "clips")
            self.clipsChanged.emit(meta["id"])
            if self.cfg["clip_autocopy"]:
                try:
                    from .library import render
                    from .share import encode
                    data = render(meta, self.clips.stems(meta), meta.get("edit") or {})
                    self.shareReady.emit(str(encode(data, meta["name"])))
                except Exception:
                    log.exception("Clip teilen")
            self._auto_transcribe(meta)

        threading.Thread(target=work, daemon=True).start()

    def _auto_transcribe(self, meta: dict):
        """Neue Clips im Hintergrund in Text umwandeln (fuer die Suche), wenn eingeschaltet."""
        from . import triggers as trg
        lang = self.triggers.lang_wanted()
        if not self.cfg["clip_transcribe"] or not trg.model_ready(lang):
            return
        try:
            from .library import render
            from .transcribe import edit_sig, transcribe
            data = render(meta, self.clips.stems(meta), meta.get("edit") or {})
            meta["transcript"] = {"lang": lang, "sig": edit_sig(meta.get("edit") or {}, meta.get("duration")), "words": transcribe(data, lang)}
            self.clips.save_meta(meta)
            self.clipsChanged.emit(meta["id"])
        except Exception:
            log.exception("Clip in Text umwandeln")

    def toggle_recording(self, keys=None):
        if self.sources.recording:
            self.stop_recording()
        else:
            self.start_recording(keys)

    def start_recording(self, keys=None):
        if self.sources.start_recording(keys):
            self._rec_since = time.time()
            what = "alle Quellen"
            if keys or self.cfg["record_sources"]:
                ks = keys or self.cfg["record_sources"]
                labels = [self.sources.available.get(k, {}).get("label", k) for k in ks]
                what = ", ".join(labels)
            self.toast.emit(f"● Aufnahme läuft: {what}", "rec")
            self.recordingChanged.emit(True)
            self.announcer.say("rec_start")

    def stop_recording(self):
        meta = self.sources.stop_recording()
        self.recordingChanged.emit(False)
        if meta:
            self.toast.emit(f"■ Aufnahme gespeichert ({meta['duration']:.0f}s)", "ok")
            self.stats.add("recordings")
            self.stats.add("rec_seconds", float(meta.get("duration") or 0))
            self.announcer.say("rec_stop")
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

    def _helper_cmd(self, text: str):
        from .host import HelperHost
        HelperHost.get().command(text)

    def post_to_discord(self, path: str, text: str = "", done=None):
        """Datei im Hintergrund an den Discord-Webhook schicken; Ergebnis als Meldung."""
        from . import webhook
        url = str(self.cfg["discord_webhook"] or "").strip()
        if not webhook.valid(url):
            self.toast.emit("Erst einen Discord-Webhook eintragen: Einstellungen → Discord & Freunde", "warn")
            return False

        def work():
            try:
                webhook.post(url, path, text)
                self.toast.emit("📤 In Discord gepostet", "ok")
                ok = True
            except Exception as e:
                from .i18n import tr
                self.toast.emit("Discord: " + tr(str(e)), "warn")
                ok = False
            if done:
                done(ok)
        threading.Thread(target=work, daemon=True).start()
        return True

    def voice_apps(self) -> set[str]:
        """Apps, in denen deine Freunde reden (Discord, Voice-Chat im Spiel, WhatsApp ...)."""
        return {str(a).lower() for a in (self.cfg["voice_chat_apps"] or [])}

    def _duck_factor(self, exe: str) -> float:
        """Wie leise eine App gerade durchs Ducking ist (fuer den Ohrenschutz)."""
        if not self._ducked or (exe in self.voice_apps() and not self.cfg["duck_discord"]):
            return 1.0
        return max(0.05, float(self.cfg["duck_level"]))

    def _duck_tick(self):
        import time as _t
        try:
            self.guard.tick()
        except Exception:
            log.exception("Ohrenschutz")
        if self.cfg["voice_enabled"]:           # Statistik: wie lange mit welcher Stimme
            nowv = _t.time()
            if self._voice_tick and nowv - self._voice_tick < 1.0:
                self.stats.voice(self.cfg["voice_preset"], nowv - self._voice_tick)
            self._voice_tick = nowv
        else:
            self._voice_tick = 0.0
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
                skip = [] if self.cfg["duck_discord"] else sorted(self.voice_apps())
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

    UPDATE_EVERY = 6 * 3600            # automatisch hoechstens alle 6 Stunden nachschauen

    def update_mode(self) -> str:
        m = self.cfg.get("update_mode")
        if m in ("auto", "ask", "off"):
            return m
        return "ask" if self.cfg["update_check"] else "off"

    def check_updates(self, auto: bool = False):
        """Im Hintergrund auf GitHub nach einer neuen Version schauen."""
        mode = self.update_mode()
        if auto and (mode == "off" or self._update_busy or self.pending_update
                     or time.time() - float(self.cfg["last_update_check"] or 0) < self.UPDATE_EVERY):
            return
        self._update_busy = True

        def work():
            from . import updater
            try:
                info = updater.check()
            except Exception as e:
                log.info("Update-Pruefung: %s", e)
                if not auto:
                    self.toast.emit("Update-Prüfung fehlgeschlagen (offline?)", "warn")
                self._update_busy = False
                return
            self.cfg["last_update_check"] = time.time()
            if not info:
                self._update_busy = False
                if not auto:
                    self.toast.emit("Du hast die neueste Version", "ok")
                return
            if auto and mode == "auto" and info.get("url") and updater.can_self_update():
                try:
                    path = updater.download(info["url"], sha256=info.get("sha256", ""))
                except Exception as e:
                    log.warning("Update-Download: %s", e)
                    self._update_busy = False
                    return
                self.pending_update = str(path)
                self.cfg["pending_update"] = str(path)
                self._last_busy = time.time()
                self._update_busy = False
                log.info("Update %s geladen, wird in einem ruhigen Moment installiert", info["version"])
                self.updateReady.emit(info["version"])
                return
            self._update_busy = False
            dec = self.cfg["update_declined"] or {}
            if auto and dec.get("version") == info["version"] and time.time() - float(dec.get("at", 0)) < 3 * 86400:
                return
            self.updateFound.emit(info)

        threading.Thread(target=work, daemon=True).start()

    def decline_update(self, version: str):
        self.cfg["update_declined"] = {"version": version, "at": time.time()}

    def _activity(self, key: str, data):
        """Mikro oder Discord aktiv (jemand redet)? Dann kein automatisches Update - sonst bricht der Call kurz ab."""
        if key == "mic" or (key.startswith("app:") and key[4:].lower() in self.voice_apps()):
            try:
                if len(data) and float(abs(data).max()) > 0.03:
                    self._last_busy = time.time()
            except Exception:
                pass

    def _idle_install(self):
        """Modus automatisch: erst installieren, wenn 10 Minuten lang nichts los war."""
        if not self.pending_update:
            return
        busy = bool(self.sources.recording) or bool(self.cfg["voice_enabled"]) or bool(self.mixer.playing())
        now = time.time()
        if busy:
            self._last_busy = now
            return
        if now - self._last_busy >= 600:
            path, self.pending_update = self.pending_update, ""
            self.cfg["pending_update"] = ""
            self.installUpdate.emit(path)

    def _resume_pending_update(self):
        """Beim letzten Mal schon geladen, aber nicht installiert? Dann jetzt beim Start installieren."""
        import os
        from pathlib import Path
        from . import __version__, updater
        p = str(self.cfg["pending_update"] or "")
        self.cfg["pending_update"] = ""
        if not p or not os.path.exists(p) or not updater.can_self_update():
            return
        if updater._ver(Path(p).name) <= updater._ver(__version__) or self.update_mode() != "auto":
            return
        from PySide6.QtCore import QTimer
        QTimer.singleShot(8000, lambda: self.installUpdate.emit(p))

    def take_pending_update(self) -> str:
        """Beim Beenden: geladenes Update mitnehmen (wird dann ohne Neustart installiert)."""
        p, self.pending_update = self.pending_update, ""
        self.cfg["pending_update"] = ""
        return p

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
