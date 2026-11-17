"""Ohrenschutz: faengt ploetzlich laute Apps (Discord-Schreier, Earrape-Sounds, Spiel-Explosionen) ab.

Jede App wird ohnehin einzeln mitgeschnitten (fuer Clips). Wird eine App zu laut, stellt der Audio-Helfer ihre
Windows-Lautstaerke sofort herunter und danach langsam wieder hoch. Der Mitschnitt liegt HINTER der
App-Lautstaerke (gemessen), deshalb wird der eigene Faktor beim Messen herausgerechnet.
Eigene Sounds werden zusaetzlich im Mixer direkt begrenzt (siehe Mixer._render)."""
from __future__ import annotations

import os
import threading
import time

import numpy as np

# Effektivwert (RMS) ueber ~30 ms, ab dem es "zu laut" ist
LEVELS = {"soft": 0.45, "normal": 0.32, "strict": 0.22}
HOLD = 1.5          # so lange bleibt es nach dem letzten zu lauten Moment leiser
RELEASE = 1.12      # danach pro Schritt (80 ms) wieder lauter
LATENCY = 0.08      # bis eine neue Lautstaerke im Mitschnitt ankommt


def _own_exes() -> set[str]:
    try:
        import psutil
        return {psutil.Process(os.getpid()).name().lower()}
    except Exception:
        return set()


class EarGuard:
    def __init__(self, cfg, send, duck_factor=lambda exe: 1.0):
        self.cfg = cfg
        self.send = send                      # send("guard x.exe 0.42") / send("unguard")
        self.duck_factor = duck_factor
        self.lock = threading.Lock()
        self.fac: dict[str, float] = {}       # exe -> aktueller Faktor
        self.prev: dict[str, tuple[float, float]] = {}   # exe -> (alter Faktor, seit wann der neue gilt)
        self.hold: dict[str, float] = {}
        self.win: dict[str, list[float]] = {}
        self.own = _own_exes()
        self.events = 0                        # wie oft eingegriffen (Statistik)
        self.last_event: tuple[str, float] = ("", 0.0)

    def enabled(self) -> bool:
        return bool(self.cfg.get("ear_guard", False))

    def threshold(self) -> float:
        return LEVELS.get(str(self.cfg.get("ear_guard_level", "normal")), LEVELS["normal"])

    def _measured_factor(self, exe: str, now: float) -> float:
        f = self.fac.get(exe, 1.0)
        old = self.prev.get(exe)
        if old and now - old[1] < LATENCY:
            f = old[0]                         # neue Lautstaerke ist noch nicht im Mitschnitt angekommen
        return max(0.05, f * max(0.05, float(self.duck_factor(exe))))

    # ---- aus dem Mitschnitt-Thread (alle ~10 ms je App)
    def on_chunk(self, key: str, data):
        if not key.startswith("app:") or not self.enabled() or not len(data):
            return
        exe = key[4:].lower()
        if exe in self.own:
            return
        rms = float(np.sqrt(np.mean(np.square(data, dtype=np.float32))))
        now = time.time()
        with self.lock:
            w = self.win.setdefault(exe, [])
            w.append(rms)
            if len(w) > 3:
                del w[0]
            est = max(w) / self._measured_factor(exe, now)   # so laut waere es ohne uns
            want = min(1.0, self.threshold() / est) if est > 0 else 1.0
            cur = self.fac.get(exe, 1.0)
            if want < 1.0:
                self.hold[exe] = now + HOLD
            if want < cur * 0.9:
                self._set(exe, want, now)
                self.events += 1
                self.last_event = (exe, now)

    def _set(self, exe: str, f: float, now: float):
        old = self.fac.get(exe, 1.0)
        self.prev[exe] = (old, now)
        if f >= 0.999:
            self.fac.pop(exe, None)
            self.send(f"guard {exe} 1")
        else:
            self.fac[exe] = f
            self.send(f"guard {exe} {f:.3f}")

    # ---- aus dem GUI-Takt (alle 80 ms): langsam wieder lauter
    def tick(self):
        now = time.time()
        with self.lock:
            if not self.enabled() and self.fac:
                self.fac.clear()
                self.send("unguard")
                return
            for exe, f in list(self.fac.items()):
                if now < self.hold.get(exe, 0):
                    continue
                self._set(exe, min(1.0, f * RELEASE), now)

    def reset(self):
        with self.lock:
            had = bool(self.fac)
            self.fac.clear()
            self.win.clear()
        if had:
            self.send("unguard")


class OutputLimiter:
    """Begrenzer fuer die eigenen Sounds auf dem Kopfhoerer (sofort leiser, langsam wieder lauter)."""

    def __init__(self):
        self.g = 1.0

    def process(self, out: np.ndarray, threshold: float) -> np.ndarray:
        if not len(out):
            return out
        rms = float(np.sqrt(np.mean(np.square(out))))
        peak = float(np.abs(out).max())
        want = 1.0
        if rms > threshold:
            want = threshold / rms
        if peak * want > 0.9:
            want = min(want, 0.9 / peak)
        if want < self.g:
            # sanft ueber den Block gleiten, damit es nicht knackt
            ramp = np.linspace(self.g, want, len(out), dtype=np.float32)[:, None]
            self.g = want
            return out * ramp
        self.g = min(want, self.g + (1.0 - self.g) * 0.03)
        return out * self.g if self.g < 0.999 else out
