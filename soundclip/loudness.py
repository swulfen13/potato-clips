"""Lautstaerke angleichen und Stille an den Raendern finden (fuer Soundboard-Sounds)."""
from __future__ import annotations

import numpy as np

from .config import SR

TARGET_DB = -18.0      # Ziel-Lautheit (RMS der lauten Stellen, in dBFS)
MAX_GAIN = 6.0         # hoechstens ~ +15,6 dB anheben
MIN_GAIN = 0.05


def norm_gain(data: np.ndarray) -> float:
    """Verstaerkung, mit der der Sound ungefaehr gleich laut wie alle anderen klingt.

    Gemessen wird der Effektivwert der lauten 50-ms-Bloecke (leise Pausen zaehlen nicht mit).
    Die Spitze wird dabei nie ueber 0 dBFS gehoben, damit nichts verzerrt."""
    if data is None or not len(data):
        return 1.0
    mono = data.mean(axis=1) if data.ndim == 2 else data
    mono = mono.astype(np.float64)
    blk = int(0.05 * SR)
    n = len(mono) // blk
    if n >= 1:
        blocks = np.sqrt((mono[: n * blk].reshape(n, blk) ** 2).mean(axis=1))
        floor = max(10 ** (-50 / 20), float(blocks.max()) * 0.1)
        loud = blocks[blocks >= floor]
        level = float(np.sqrt((loud ** 2).mean())) if len(loud) else float(blocks.max())
    else:
        level = float(np.sqrt((mono ** 2).mean()))
    if level < 1e-5:
        return 1.0
    g = 10 ** (TARGET_DB / 20) / level
    peak = float(np.abs(data).max())
    if peak > 0:
        g = min(g, 0.98 / peak)
    return float(round(min(MAX_GAIN, max(MIN_GAIN, g)), 4))


def silence_bounds(data: np.ndarray, threshold_db: float = -45.0, pad: float = 0.03) -> tuple[float, float] | None:
    """Start/Ende (Sekunden) ohne Stille vorne und hinten. None, wenn es nichts abzuschneiden gibt."""
    if data is None or not len(data):
        return None
    env = np.abs(data).max(axis=1) if data.ndim == 2 else np.abs(data)
    thr = 10 ** (threshold_db / 20)
    idx = np.flatnonzero(env > thr)
    if not len(idx):
        return None
    dur = len(env) / SR
    start = max(0.0, idx[0] / SR - pad)
    end = min(dur, (idx[-1] + 1) / SR + pad)
    if start < 0.05 and dur - end < 0.05:
        return None
    return round(start, 3), round(end, 3)


def apply_trim(data: np.ndarray, trim) -> np.ndarray:
    if not trim or data is None:
        return data
    try:
        start, end = float(trim[0]), float(trim[1])
    except Exception:
        return data
    a = max(0, int(start * SR))
    b = min(len(data), int(end * SR)) if end > 0 else len(data)
    if b - a < int(0.02 * SR):
        return data
    return data[a:b]
