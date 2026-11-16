"""Sauberes Mikro: Rumpelfilter + KI-Rauschunterdrueckung (RNNoise) + Sprach-Gate.

RNNoise (BSD-Lizenz) laeuft lokal, braucht kaum CPU und arbeitet in 10-ms-Bloecken bei 48 kHz.
Die DLL liegt in bin/rnnoise.dll (Quelle: pyrnnoise).
"""
from __future__ import annotations

import ctypes
import logging
from pathlib import Path

import numpy as np

from .config import RES_DIR
from .effects import Filt

log = logging.getLogger("potatoclips.cleanmic")

FRAME = 480  # 10 ms bei 48 kHz
_lib = None


def _load():
    global _lib
    if _lib is not None:
        return _lib
    cands = [RES_DIR / "bin" / "rnnoise.dll"]
    try:
        import importlib.util
        spec = importlib.util.find_spec("pyrnnoise")
        if spec and spec.origin:
            cands.append(Path(spec.origin).parent / "rnnoise.dll")
    except Exception:
        pass
    for p in cands:
        if p.exists():
            try:
                lib = ctypes.CDLL(str(p))
                lib.rnnoise_create.argtypes = [ctypes.c_void_p]
                lib.rnnoise_create.restype = ctypes.c_void_p
                lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
                lib.rnnoise_process_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float),
                                                      ctypes.POINTER(ctypes.c_float)]
                lib.rnnoise_process_frame.restype = ctypes.c_float
                _lib = lib
                log.info("RNNoise geladen: %s", p)
                return lib
            except Exception as e:
                log.warning("RNNoise %s: %s", p, e)
    _lib = False
    return False


def available() -> bool:
    return bool(_load())


class MicCleaner:
    """Verarbeitet Mono-Bloecke beliebiger Laenge. Gibt immer genauso viele Samples zurueck
    (10 ms feste Verzoegerung)."""

    def __init__(self, strength: float = 0.85, gate: bool = True):
        self.lib = _load()
        self.state = self.lib.rnnoise_create(None) if self.lib else None
        self.strength = float(np.clip(strength, 0.0, 1.0))
        self.gate_on = gate
        self.hp = Filt("highpass", 85, 2)
        self.inbuf = np.zeros(0, np.float32)
        self.outbuf = np.zeros(FRAME, np.float32)   # 10 ms Vorlauf
        self.frame = np.zeros(FRAME, np.float32)
        self.gain = 1.0
        self.hold = 0
        self.vad = 0.0

    def close(self):
        if self.state and self.lib:
            self.lib.rnnoise_destroy(self.state)
            self.state = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _frame(self, x: np.ndarray) -> np.ndarray:
        """Ein 480er-Frame (float -1..1) -> bereinigt."""
        if self.state is None:
            return x
        f = np.ascontiguousarray(x * 32768.0, dtype=np.float32)
        ptr = f.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        prob = float(self.lib.rnnoise_process_frame(self.state, ptr, ptr))
        y = f / 32768.0
        self.vad = prob
        s = self.strength
        y = y * s + x * (1.0 - s)
        if self.gate_on:
            # Sanftes Sprach-Gate: oeffnet sofort, bleibt nach Sprache lange offen, schliesst nie ganz
            if prob > 0.30:
                self.hold = 45            # 450 ms nach Sprache offen halten
            elif self.hold > 0:
                self.hold -= 1
            target = 1.0 if (prob > 0.30 or self.hold > 0) else 0.18
            start = self.gain
            end = target if target > start else start + (target - start) * 0.08   # auf: sofort, zu: langsam
            y = y * np.linspace(start, end, FRAME, dtype=np.float32)
            self.gain = end
        return y

    def process(self, mono: np.ndarray) -> np.ndarray:
        n = len(mono)
        if n == 0:
            return mono
        x = self.hp(mono.reshape(-1, 1)).reshape(-1).astype(np.float32)
        self.inbuf = np.concatenate([self.inbuf, x])
        outs = []
        while len(self.inbuf) >= FRAME:
            fr = self.inbuf[:FRAME]
            self.inbuf = self.inbuf[FRAME:]
            outs.append(self._frame(fr))
        if outs:
            self.outbuf = np.concatenate([self.outbuf] + outs)
        if len(self.outbuf) < n:  # sollte nicht passieren – auffuellen statt Luecke
            self.outbuf = np.concatenate([np.zeros(n - len(self.outbuf), np.float32), self.outbuf])
        y = self.outbuf[:n]
        self.outbuf = self.outbuf[n:]
        return y
