"""Ansage nach dem Clippen ("Clip by Potato!") - Windows-Stimme mit Potato-Effekt.

Je nach Einstellung hoert man sie nur selbst oder auch die Freunde in Discord. Die fertige Ansage wird
zwischengespeichert, damit sie beim naechsten Mal sofort kommt."""
from __future__ import annotations

import logging
import os
import threading

log = logging.getLogger("soundclip")

DEFAULT_TEXT = "Clip by Potato!"
FIXED = {
    "de": {"rec_start": "Aufnahme läuft!", "rec_stop": "Aufnahme gespeichert!", "auto": "Auto-Clip by Potato!"},
    "en": {"rec_start": "Recording!", "rec_stop": "Recording saved!", "auto": "Auto clip by Potato!"},
}


def _lang() -> str:
    from . import i18n
    return "de" if i18n.LANG == "de" else "en"


def pick_voice(voices: list[dict], lang: str) -> str:
    for v in voices:
        if str(v.get("culture", "")).lower().startswith(lang):
            return v["name"]
    return voices[0]["name"] if voices else ""


class Announcer:
    def __init__(self, ctl):
        self.ctl = ctl
        self.cache: dict[tuple, object] = {}
        self.lock = threading.Lock()
        self._voices: list[dict] | None = None

    def text_for(self, kind: str) -> str:
        if kind == "clip":
            return (self.ctl.cfg.get("announce_text") or DEFAULT_TEXT).strip()[:120]
        return FIXED[_lang()].get(kind, DEFAULT_TEXT)

    def say(self, kind: str = "clip", force: bool = False):
        """Ansage abspielen (laeuft im Hintergrund; force = auch wenn ausgeschaltet, zum Testen)."""
        cfg = self.ctl.cfg
        mode = cfg.get("announce_mode", "off")
        if mode == "off" and not force:
            return
        if kind in ("rec_start", "rec_stop") and not cfg.get("announce_recording", True) and not force:
            return
        text = self.text_for(kind)
        if not text:
            return
        to_all = mode == "all"
        threading.Thread(target=self._work, args=(text, to_all), daemon=True).start()

    def _work(self, text: str, to_all: bool):
        try:
            data = self.render(text)
        except Exception as e:
            log.exception("Ansage")
            self.ctl.toast.emit(f"Ansage fehlgeschlagen: {e}", "warn")
            return
        if data is not None:
            self.ctl.announceReady.emit(data, to_all)

    def render(self, text: str):
        from . import tts
        from .effects import VOICE_PRESETS, apply_chain
        from .mixer import load_audio
        cfg = self.ctl.cfg
        effect = cfg.get("announce_effect", "potato")
        voice = cfg.get("announce_voice") or ""
        if not voice:
            if self._voices is None:
                try:
                    self._voices = tts.voices()
                except Exception:
                    self._voices = []
            voice = pick_voice(self._voices, _lang())
        key = (text, voice, effect)
        with self.lock:
            if key in self.cache:
                return self.cache[key]
        path = tts.synth(text, voice)
        try:
            data = load_audio(path)
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
        pre = VOICE_PRESETS.get(effect) if effect and effect != "none" else None
        if pre:
            data = apply_chain(data, [{"type": k, "amount": min(1.0, a * 1.1)} for k, a in pre[1]])
        with self.lock:
            if len(self.cache) > 12:
                self.cache.clear()
            self.cache[key] = data
        return data
