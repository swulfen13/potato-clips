"""Profile pro Spiel: laeuft ein bestimmtes Spiel, gelten andere Sound-Hotkeys, ein anderes Sound-Rad und
optional eine andere Stimme. Erkannt wird am laufenden Prozess (auch wenn das Spiel noch keinen Ton macht)."""
from __future__ import annotations

import logging
import threading
import time
import uuid

log = logging.getLogger("soundclip")


def new_profile(name: str = "Neues Profil") -> dict:
    return {"id": uuid.uuid4().hex[:8], "name": name, "apps": [], "folder": "", "wheel_source": "",
            "voice": ""}


def clean(p: dict) -> dict:
    """Profil aus der Konfiguration absichern (fehlende Felder, Typen)."""
    out = new_profile()
    if isinstance(p, dict):
        out.update({k: p[k] for k in out if k in p})
    out["name"] = str(out["name"] or "Profil")[:40]
    apps = out["apps"] if isinstance(out["apps"], list) else []
    out["apps"] = [norm_exe(a) for a in apps if norm_exe(a)][:10]
    for k in ("folder", "wheel_source", "voice", "id"):
        out[k] = str(out[k] or "")
    return out


def norm_exe(name) -> str:
    n = str(name or "").strip().lower().replace("app:", "")
    if n and not n.endswith(".exe"):
        n += ".exe"
    return n if n and "\\" not in n and "/" not in n else ""


def running_exes() -> set[str]:
    try:
        import psutil
        return {(p.info.get("name") or "").lower() for p in psutil.process_iter(["name"])}
    except Exception:
        return set()


def match(profiles: list[dict], exes: set[str]) -> str:
    """Erstes Profil (in der Reihenfolge der Liste), dessen Spiel gerade laeuft -> id, sonst ""."""
    for p in profiles:
        if any(a in exes for a in p.get("apps", [])):
            return p["id"]
    return ""


class ProfileWatcher:
    """Schaut alle paar Sekunden im Hintergrund, welches Spiel laeuft, und meldet Wechsel."""

    def __init__(self, cfg, found, interval: float = 3.0):
        self.cfg = cfg
        self.found = found              # found(profile_id) - kommt aus dem Hintergrund-Thread
        self.interval = interval
        self._stop = threading.Event()
        self._last = None
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="profiles")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def poke(self):
        self._last = None

    def _loop(self):
        while not self._stop.is_set():
            try:
                profs = [clean(p) for p in (self.cfg.get("profiles") or [])]
                pid = match(profs, running_exes()) if profs and self.cfg.get("profile_auto", True) else ""
                if pid != self._last:
                    self._last = pid
                    self.found(pid)
            except Exception:
                log.exception("Profile")
            self._stop.wait(self.interval)
            time.sleep(0)
