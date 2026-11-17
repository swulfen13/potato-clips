"""Pfade und Einstellungen.

Aus dem Quellcode gestartet: alles portabel im Projektordner unter data/.
Installierte Version (EXE): Einstellungen, Sounds und Clips unter %APPDATA%\\Potato Clips."""
from __future__ import annotations

import copy
import json
import os
import sys
import threading
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent
    RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
    DATA_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "Potato Clips"
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    RES_DIR = APP_DIR
    DATA_DIR = APP_DIR / "data"
if os.environ.get("POTATO_CLIPS_DATA"):      # Tests: eigener Ordner, echte Daten bleiben unberuehrt
    DATA_DIR = Path(os.environ["POTATO_CLIPS_DATA"])
ASSETS_DIR = RES_DIR / "assets"
ICON_FILE = ASSETS_DIR / "potato_clips.ico"
SOUNDS_DIR = DATA_DIR / "sounds"
CLIPS_DIR = DATA_DIR / "clips"
EXPORT_DIR = DATA_DIR / "exports"
CONFIG_FILE = DATA_DIR / "config.json"
SOUNDS_FILE = DATA_DIR / "sounds.json"
LOG_FILE = DATA_DIR / "soundclip.log"
HELPER = RES_DIR / "bin" / "audiocap.exe"

SR = 48000  # interne Samplerate fuer alles

for _d in (DATA_DIR, SOUNDS_DIR, CLIPS_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DEFAULTS: dict = {
    # Aufnahme / Clipping
    "buffer_seconds": 30,
    "capture_mode": "all",            # "all" = Mikro + alle Apps, "selected" = nur ausgewaehlte
    "selected_sources": ["mic"],
    "record_sources": [],             # leer = alle laufenden Quellen
    "capture_system": False,          # gesamter Systemsound als eigene Quelle
    "mic_device": "default",
    "ignore_apps": [],                # z. B. ["spotify.exe"]
    # Wiedergabe
    "monitor_device": "",             # "" = Windows-Standard
    "virtual_device": "auto",         # "auto" = CABLE Input suchen, "" = aus
    "play_to_monitor": True,
    "play_to_virtual": True,
    "mic_passthrough": True,
    "mic_passthrough_gain": 1.0,
    "clean_mic": True,                # KI-Rauschfilter + Gate fuer die Stimme
    "clean_strength": 0.85,
    "clean_gate": True,
    "route_sources": {},              # App-Quelle -> Lautstaerke (z. B. Spotify an Discord)
    "master_volume": 0.8,
    # Live-Stimmverzerrer
    "voice_enabled": False,
    "voice_preset": "potato",
    "voice_amount": 0.5,
    "voice_monitor": False,           # mich selbst (mit Effekt) hoeren
    "voice_monitor_gain": 0.8,
    "voice_hotkeys": {},              # preset -> hotkey
    "voice_amounts": {},              # preset -> Staerke 0..1 (pro Effekt gemerkt)
    "retrigger": "restart",           # restart | stop | overlap
    # Aussehen & Sprache
    "ui_theme": "pro",                # pro | potato
    "language": "auto",               # auto | de | en
    "setup_done": False,              # Einrichtungs-Assistent schon durch?
    # Neue Funktionen
    "custom_voices": {},              # eigene Stimmeffekte: key -> {name, emoji, chain}
    "duck_enabled": False,            # andere Apps leiser, wenn ein Sound laeuft
    "duck_level": 0.3,                # so laut bleiben die anderen Apps (0..1)
    "duck_discord": False,            # auch Discord leiser machen?
    "tts_voice": "",                  # Windows-Stimme fuers Vorlesen ("" = Standard)
    "tts_effect": True,               # Vorlesen mit aktuellem Stimmeffekt
    "clip_autocopy": False,           # neue Clips sofort als MP3 in die Zwischenablage
    "update_check": True,             # beim Start nach Updates schauen
    "last_update_check": 0,
    "update_mode": None,              # auto | ask | off  (None = wie update_check: ask/off)
    "update_declined": {},
    "pending_update": "",             # schon geladener Installer (wird beim naechsten Start installiert)            # {"version", "at"}: Nein geklickt -> 3 Tage Ruhe fuer diese Version
    # Soundboard
    "normalize_sounds": True,         # alle Sounds ungefaehr gleich laut
    "auto_trim": True,                # Stille vorne/hinten beim Import abschneiden
    "sound_folders": [],              # Reihenfolge der Ordner (auch leere)
    # Fernbedienung / Stream Deck / OBS
    "remote_enabled": False,          # Handy im WLAN
    "api_enabled": False,             # Links fuer Stream Deck / OBS (nur dieser PC)
    "remote_port": 8765,
    "remote_token": "",
    # Auto-Clip
    "autoclip_enabled": False,
    "autoclip_source": "discord",     # alt (1.2.0): discord | mic | any
    "autoclip_apps": None,            # Quellen, die Auto-Clip ausloesen ("*" = alle); None = wie autoclip_source
    "autoclip_db": -16.0,             # Schwelle in dBFS
    "autoclip_after": 4,              # Sekunden nach dem lauten Moment noch mitnehmen
    "autoclip_cooldown": 30,
    # Sprach-Trigger
    "triggers_enabled": False,
    "trigger_lang": "auto",           # auto | de | en
    "voice_commands": False,          # "Potato, clip it" usw.
    # Ansage nach dem Clip
    "announce_mode": "me",            # off | me (nur ich) | all (ich + Discord)
    "announce_text": "Clip by Potato!",
    "announce_effect": "potato",      # Stimmeffekt der Ansage ("none" = ohne)
    "announce_voice": "",             # Windows-Stimme ("" = passend zur Sprache)
    "announce_recording": True,       # auch bei Aufnahme Start/Ende
    # Video
    "video_format": "9:16",
    # Oberflaeche
    "overlay_enabled": True,
    "overlay_corner": "top-right",
    "minimize_to_tray": True,
    "hotkeys": {
        "clip": "ctrl+alt+c",
        "record": "ctrl+alt+r",
        "stop_all": "ctrl+alt+s",
        "overlay": "ctrl+alt+o",
        "passthrough": "",
        "voice_toggle": "ctrl+alt+v",
        "voice_next": "ctrl+alt+n",
        "voice_up": "ctrl+alt+page up",
        "voice_down": "ctrl+alt+page down",
        "voice_hold": "",
        "random_sound": "",
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, path: Path = CONFIG_FILE):
        self.path = path
        self._lock = threading.RLock()
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                data = {}
        if path.exists() and data and "setup_done" not in data:
            data["setup_done"] = True        # bestehende Nutzer nicht mit dem Assistenten nerven
        self.data = _merge(DEFAULTS, data)

    def __getitem__(self, key):
        with self._lock:
            return self.data[key]

    def get(self, key, default=None):
        with self._lock:
            return self.data.get(key, default)

    def __setitem__(self, key, value):
        with self._lock:
            self.data[key] = value
        self.save()

    def update(self, **kw):
        with self._lock:
            self.data.update(kw)
        self.save()

    def save(self):
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
