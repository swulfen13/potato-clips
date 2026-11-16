"""Zwei Gesichter von Potato Clips: "pro" (ruhig, dunkel) und "potato" (laut, gelb, trashig).

Das aktive Design wird beim Start gesetzt (set_mode), bevor die Oberflaeche gebaut wird.
Ein Wechsel startet die App neu.
"""
from __future__ import annotations

PALETTES: dict[str, dict[str, str]] = {
    "pro": {
        "accent": "#F2A93B", "accent_hover": "#FFC36B", "accent_text": "#1A1204", "accent_soft": "#1F1A12",
        "red": "#FF5A5F", "green": "#3DD6B5", "warn": "#FFB547", "info": "#8FB4FF",
        "bg": "#0D0E11", "sidebar": "#111317", "panel": "#16181D", "panel2": "#1C1F25", "panel_hover": "#1E2128",
        "border": "#23262D", "border2": "#2C3038", "text": "#E8EAED", "muted": "#9AA1AC", "sel": "#2A2418",
        "toggle_off": "#2C3038", "groove": "#2C3038", "meter_bg": "#23262D", "wave_off": "#3A3F49",
        "overlay_bg": "#111317", "overlay_text": "#E8EAED", "danger_bg": "#2A1517", "danger_border": "#5A2A2E",
        "danger_text": "#FFC9CB", "hint_bg": "#1F1A12", "hint_border": "#3A2E19", "hint_text": "#E6D6BC",
    },
    "potato": {
        "accent": "#FF3D8B", "accent_hover": "#FF6FA8", "accent_text": "#111111", "accent_soft": "#FFD3E5",
        "red": "#E8202A", "green": "#0E7A3C", "warn": "#B35400", "info": "#0A6FB8",
        "bg": "#FFE94D", "sidebar": "#FFE94D", "panel": "#FFFFFF", "panel2": "#FFFFFF", "panel_hover": "#FFF6B0",
        "border": "#111111", "border2": "#111111", "text": "#111111", "muted": "#3D3D3D", "sel": "#3DE8FF",
        "toggle_off": "#FFFFFF", "groove": "#FFFFFF", "meter_bg": "#FFFFFF", "wave_off": "#B9B9B9",
        "overlay_bg": "#FFE94D", "overlay_text": "#111111", "danger_bg": "#E8202A", "danger_border": "#111111",
        "danger_text": "#FFFFFF", "hint_bg": "#FFFFFF", "hint_border": "#111111", "hint_text": "#111111",
    },
}

# Kachelfarben im Potato-Modus (der Reihe nach)
POTATO_TILES = ["#FF3D8B", "#3DE8FF", "#B6FF3B", "#FF8A1F", "#C9A0FF", "#FFFFFF"]
POTATO_TILTS = [-1.6, 1.1, -0.6, 1.9, -1.9, 0.6, 1.4, -1.2]

MODE = "pro"
P: dict[str, str] = dict(PALETTES["pro"])


def set_mode(mode: str) -> None:
    global MODE
    MODE = mode if mode in PALETTES else "pro"
    P.clear()
    P.update(PALETTES[MODE])


def potato() -> bool:
    return MODE == "potato"


def font_family() -> str:
    return "Comic Neue" if potato() else "Inter"


def heading_family() -> str:
    return "Bungee" if potato() else "Inter"
