"""Clips in Text umwandeln (offline, Vosk) - mit Zeit pro Wort fuer Untertitel und die Clip-Suche."""
from __future__ import annotations

import hashlib
import json
import logging
import threading

import numpy as np

log = logging.getLogger("soundclip")
_models: dict = {}
_lock = threading.Lock()


def _model(lang: str):
    from . import triggers
    import vosk
    with _lock:
        m = _models.get(lang)
        if m is None:
            vosk.SetLogLevel(-1)
            m = vosk.Model(str(triggers.model_dir(lang)))
            _models[lang] = m
        return m


def edit_sig(edit: dict | None, dur: float | None = None) -> str:
    """Kennung des Schnitts - aendert sich der Schnitt, passen die Wortzeiten nicht mehr.
    Standardwerte (ganze Laenge, alle Spuren an, keine Effekte) zaehlen wie "nicht bearbeitet"."""
    e = edit or {}
    start = e.get("start")
    if start is not None and float(start) <= 0.001:
        start = None
    end = e.get("end")
    if end is not None and dur and float(end) >= float(dur) - 0.02:
        end = None
    stems = {k: v for k, v in (e.get("stems") or {}).items()
             if not (isinstance(v, dict) and v.get("on", True) and abs(float(v.get("gain", 1.0)) - 1.0) < 1e-6)}
    key = {"start": start, "end": end, "stems": stems or None, "effects": e.get("effects") or None}
    return hashlib.md5(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()[:12]


def transcribe(data: np.ndarray, lang: str) -> list[dict]:
    """48 kHz Audio -> [{"w": Wort, "s": Start, "e": Ende}] (Sekunden)."""
    import vosk
    if data is None or not len(data):
        return []
    mono = data.mean(axis=1) if data.ndim == 2 else data
    n = len(mono) - len(mono) % 3
    x = mono[:n].reshape(-1, 3).mean(axis=1)                    # 48 kHz -> 16 kHz
    peak = float(np.abs(x).max()) if len(x) else 0.0
    if peak > 0:
        x = x * min(8.0, 0.7 / peak)                            # leise Clips anheben
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    rec = vosk.KaldiRecognizer(_model(lang), 16000)
    rec.SetWords(True)
    words: list[dict] = []

    def take(res: str):
        for w in json.loads(res).get("result", []):
            if w.get("word") and w["word"] != "[unk]":
                words.append({"w": w["word"], "s": round(float(w["start"]), 2), "e": round(float(w["end"]), 2)})

    step = 16000 * 2 // 2                                       # 0,5 s pro Block
    for i in range(0, len(pcm), step):
        if rec.AcceptWaveform(pcm[i:i + step]):
            take(rec.Result())
    take(rec.FinalResult())
    return words


def text_of(meta: dict) -> str:
    t = meta.get("transcript") or {}
    return " ".join(w["w"] for w in t.get("words", []))


def subtitle_lines(words: list[dict], max_words: int = 6, max_len: float = 2.8, gap: float = 0.8) -> list[dict]:
    """Woerter zu kurzen Untertitel-Zeilen buendeln: [{"s", "e", "words": [...]}]"""
    lines: list[dict] = []
    cur: list[dict] = []
    for w in words:
        if cur and (len(cur) >= max_words or w["s"] - cur[-1]["e"] > gap or w["e"] - cur[0]["s"] > max_len):
            lines.append({"s": cur[0]["s"], "e": cur[-1]["e"], "words": cur})
            cur = []
        cur.append(w)
    if cur:
        lines.append({"s": cur[0]["s"], "e": cur[-1]["e"], "words": cur})
    return lines
