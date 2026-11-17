"""Statistik fuer "Potato Wrapped": was wurde wie oft benutzt (alles nur lokal in stats.json)."""
from __future__ import annotations

import datetime as _dt
import json
import logging
import threading

from .config import DATA_DIR

log = logging.getLogger("soundclip")
STATS_FILE = DATA_DIR / "stats.json"
COUNTERS = ("clips", "autoclips", "recordings", "voice_cmds", "triggers", "tts", "videos", "remote", "wheel")


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = self._load()
        self.dirty = False

    def _fresh(self) -> dict:
        return {"since": _dt.date.today().isoformat(), "sounds": {}, "names": {}, "rec_seconds": 0.0,
                "voice_seconds": {}, **{k: 0 for k in COUNTERS}}

    def _load(self) -> dict:
        d = self._fresh()
        try:
            if STATS_FILE.exists():
                d.update(json.loads(STATS_FILE.read_text(encoding="utf-8")))
        except Exception:
            log.exception("Statistik laden")
        return d

    def save(self):
        with self.lock:
            if not self.dirty:
                return
            data = json.dumps(self.data, ensure_ascii=False)
            self.dirty = False
        try:
            tmp = STATS_FILE.with_suffix(".tmp")
            tmp.write_text(data, encoding="utf-8")
            tmp.replace(STATS_FILE)
        except Exception:
            log.exception("Statistik speichern")

    def add(self, key: str, n: float = 1):
        with self.lock:
            self.data[key] = self.data.get(key, 0) + n
            self.dirty = True

    def sound(self, sid: str, name: str):
        with self.lock:
            self.data["sounds"][sid] = self.data["sounds"].get(sid, 0) + 1
            self.data["names"][sid] = name
            self.dirty = True

    def voice(self, preset: str, seconds: float):
        with self.lock:
            vs = self.data["voice_seconds"]
            vs[preset] = vs.get(preset, 0) + seconds
            self.dirty = True

    def reset(self):
        with self.lock:
            self.data = self._fresh()
            self.dirty = True
        self.save()

    def summary(self, sounds_lib=None) -> dict:
        """Aufbereitet fuer das Wrapped-Bild."""
        with self.lock:
            d = json.loads(json.dumps(self.data))
        names = d.get("names", {})
        if sounds_lib is not None:                       # aktuelle Namen bevorzugen
            for s in sounds_lib.sounds:
                if s["id"] in d["sounds"]:
                    names[s["id"]] = s["name"]
        top = sorted(d["sounds"].items(), key=lambda kv: -kv[1])[:5]
        voice = sorted(d.get("voice_seconds", {}).items(), key=lambda kv: -kv[1])
        return {
            "since": d.get("since", ""),
            "plays": int(sum(d["sounds"].values())),
            "top": [(names.get(k, "?"), int(v)) for k, v in top],
            "clips": int(d.get("clips", 0)), "autoclips": int(d.get("autoclips", 0)),
            "recordings": int(d.get("recordings", 0)), "rec_minutes": int(d.get("rec_seconds", 0) // 60),
            "voice_top": voice[0][0] if voice else "", "voice_minutes": int(sum(v for _, v in voice) // 60),
            "voice_cmds": int(d.get("voice_cmds", 0)), "triggers": int(d.get("triggers", 0)),
            "tts": int(d.get("tts", 0)), "videos": int(d.get("videos", 0)), "wheel": int(d.get("wheel", 0)),
            "remote": int(d.get("remote", 0)),
        }


def title_for(s: dict) -> tuple[str, str]:
    """Ein lustiger Titel je nach Nutzung: (Titel, Untertitel) - auf Deutsch, tr() uebersetzt."""
    if s["plays"] >= 200:
        return "Soundboard-Terrorist", "Deine Freunde brauchen Ohropax."
    if s["clips"] + s["autoclips"] >= 50:
        return "Beweismittel-Sammler", "Niemand ist vor dir sicher."
    if s["voice_minutes"] >= 60:
        return "Stimmen-Chamäleon", "Wer bist du eigentlich wirklich?"
    if s["voice_cmds"] + s["triggers"] >= 30:
        return "Kartoffel-Flüsterer", "Du redest mit deiner Software. Respekt."
    if s["plays"] >= 30:
        return "Knöpfchen-Drücker", "Ein solider Lärm-Lieferant."
    if s["plays"] + s["clips"] > 0:
        return "Frische Kartoffel", "Das war erst der Anfang."
    return "Stille Kartoffel", "Noch nichts passiert – drück mal einen Sound!"
