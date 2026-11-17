"""Auto-Clip: speichert automatisch einen Clip, wenn es im Call/Spiel laut wird (Schreien, Lachen, Jubel)."""
from __future__ import annotations

import math
import threading
import time

import numpy as np

from .config import SR

WINDOW = 0.35      # Sekunden, ueber die die Lautstaerke gemittelt wird
HOLD = 0.25        # so lange muss es ueber der Schwelle bleiben


class AutoClip:
    """Bekommt die Audio-Bloecke aller Quellen (aus den Aufnahme-Threads) und meldet, wann geclippt werden soll."""

    def __init__(self, cfg, fire):
        self.cfg = cfg
        self.fire = fire                    # wird aus einem Hintergrund-Thread aufgerufen
        self.lock = threading.Lock()
        self.env: dict[str, float] = {}     # Quelle -> geglaettete Leistung
        self.over_frames: dict[str, int] = {}   # wie lange (in Samples) es schon laut ist
        self.last_fire = 0.0
        self.pending_at = 0.0
        self.peak_db = -90.0                # fuer die Anzeige in den Einstellungen
        self._timer: threading.Timer | None = None

    # ---- welche Quellen zaehlen?
    def apps(self) -> list[str]:
        """Gewaehlte Quellen ("*" = alle). Aeltere Einstellung (Discord/Mikro/alles) wird uebernommen."""
        apps = self.cfg.get("autoclip_apps")
        if isinstance(apps, list):
            return apps
        mode = self.cfg.get("autoclip_source", "discord")
        return {"mic": ["mic"], "any": ["*"]}.get(mode, ["app:discord.exe"])

    def watches(self, key: str) -> bool:
        apps = self.cfg.get("autoclip_apps")
        if isinstance(apps, list):
            return "*" in apps or key in apps
        mode = self.cfg.get("autoclip_source", "discord")
        if mode == "mic":
            return key == "mic"
        if mode == "discord":
            return "discord" in key
        return True                         # "any"

    def on_chunk(self, key: str, data: np.ndarray):
        if not self.cfg.get("autoclip_enabled") or not len(data) or not self.watches(key):
            return
        p = float(np.mean(np.square(data, dtype=np.float32)))
        a = math.exp(-(len(data) / SR) / WINDOW)
        now = time.time()
        with self.lock:
            e = self.env.get(key, 0.0) * a + p * (1 - a)
            self.env[key] = e
            db = 10 * math.log10(e + 1e-12)
            self.peak_db = max(self.peak_db, db)
            thr = float(self.cfg.get("autoclip_db", -14.0))
            if db < thr:
                self.over_frames.pop(key, None)
                return
            frames = self.over_frames.get(key, 0) + len(data)
            self.over_frames[key] = frames
            if frames < HOLD * SR:
                return
            cooldown = float(self.cfg.get("autoclip_cooldown", 30))
            if self.pending_at or now - self.last_fire < cooldown:
                return
            after = float(self.cfg.get("autoclip_after", 4))
            self.pending_at = now + after
            self._timer = threading.Timer(after, self._go)
            self._timer.daemon = True
            self._timer.start()

    def _go(self):
        with self.lock:
            self.pending_at = 0.0
            self.last_fire = time.time()
            self.over_frames.clear()
        try:
            self.fire()
        except Exception:
            pass

    def take_level_db(self) -> float:
        """Lautester Wert seit der letzten Abfrage (fuer den Pegel in den Einstellungen)."""
        with self.lock:
            v = self.peak_db
            self.peak_db = -90.0
        return v

    def stop(self):
        t = self._timer
        if t:
            t.cancel()
