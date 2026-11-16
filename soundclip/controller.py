"""Verbindet Engine, Bibliothek, Hotkeys und UI."""
from __future__ import annotations

import logging
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
}


class Controller(QObject):
    toast = Signal(str, str)            # text, art (info|ok|rec|warn)
    clipsChanged = Signal(str)          # id des neuen Clips ("" = nur neu laden)
    soundsChanged = Signal()
    recordingChanged = Signal(bool)
    overlayToggled = Signal(bool)
    settingsChanged = Signal()
    voiceChanged = Signal()

    def __init__(self):
        super().__init__()
        self.cfg = Config()
        self.mixer = Mixer(self.cfg)
        self.sources = SourceManager(self.cfg, self.mixer)
        self.sounds = SoundLibrary()
        self.clips = ClipLibrary()
        self.hotkeys = HotkeyManager()
        self.hotkeys.triggered.connect(self._on_hotkey)
        self.hotkey_errors: list[str] = []

    def start(self):
        try:
            self.mixer.reopen()
        except Exception as e:
            log.exception("Mixer")
            self.toast.emit(f"Audio-Ausgabe: {e}", "warn")
        self.sources.start()
        self.apply_hotkeys()

    def shutdown(self):
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
        v = self.mixer.play(data, gain=float(s.get("volume", 1.0)), sound_id=sid, name=s["name"])
        if v is None and not self.mixer.active_targets():
            self.toast.emit("Keine Audio-Ausgabe aktiv – siehe Einstellungen", "warn")
        elif v is not None:
            self.toast.emit("▶ " + s["name"], "info")

    def play_data(self, data, name="Vorschau", preview=True, sound_id="__preview__"):
        return self.mixer.play(data, sound_id=sound_id, name=name, preview=preview)

    def stop_all(self):
        self.mixer.stop_all()
        self.toast.emit("■ Alle Sounds gestoppt", "info")

    def clip_now(self, seconds=None):
        sec = seconds or self.cfg["buffer_seconds"]

        def work():
            try:
                meta = self.sources.make_clip(sec)
            except Exception as e:
                log.exception("clip")
                self.toast.emit(f"Clip fehlgeschlagen: {e}", "warn")
                return
            if meta is None:
                self.toast.emit("Clip: in den letzten Sekunden war alles still", "warn")
                return
            names = ", ".join(st["label"] for st in meta["stems"])
            self.toast.emit(f"✂ Clip gespeichert ({sec:g}s): {names}", "ok")
            self.clipsChanged.emit(meta["id"])

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
