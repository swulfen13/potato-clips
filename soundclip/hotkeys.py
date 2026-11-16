"""Globale Hotkeys (funktionieren auch, wenn das Spiel im Vordergrund ist)."""
from __future__ import annotations

import logging

import keyboard
from PySide6.QtCore import QObject, Signal

log = logging.getLogger("soundclip.hotkeys")

# Qt-Tastennamen -> Namen der keyboard-Bibliothek
_QT2KB = {
    "ctrl": "ctrl", "alt": "alt", "shift": "shift", "meta": "windows",
    "pgup": "page up", "pgdown": "page down", "del": "delete", "ins": "insert", "esc": "esc",
    "return": "enter", "enter": "enter", "space": "space", "backspace": "backspace", "tab": "tab",
    "print": "print screen", "pause": "pause", "home": "home", "end": "end",
    "left": "left", "right": "right", "up": "up", "down": "down", "capslock": "caps lock",
    "scrolllock": "scroll lock", "numlock": "num lock", "menu": "menu",
    "+": "plus", ",": ",", "-": "-", ".": ".",
}
_KB2QT = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "windows": "Meta", "page up": "PgUp",
          "page down": "PgDown", "delete": "Del", "insert": "Ins", "esc": "Esc", "enter": "Return",
          "space": "Space", "backspace": "Backspace", "tab": "Tab", "print screen": "Print", "pause": "Pause",
          "home": "Home", "end": "End", "left": "Left", "right": "Right", "up": "Up", "down": "Down",
          "caps lock": "CapsLock", "scroll lock": "ScrollLock", "num lock": "NumLock", "menu": "Menu",
          "plus": "+"}


def qt_to_combo(seq: str) -> str:
    """'Ctrl+Alt+C' -> 'ctrl+alt+c'"""
    if not seq:
        return ""
    seq = seq.split(", ")[0].strip()
    parts = []
    # '+' als Taste: "Ctrl++"
    tokens = seq.split("+")
    if seq.endswith("++"):
        tokens = seq[:-2].split("+") + ["+"]
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        low = t.lower()
        parts.append(_QT2KB.get(low, low))
    return "+".join(parts)


def combo_to_qt(combo: str) -> str:
    if not combo:
        return ""
    out = []
    for t in combo.split("+"):
        t = t.strip()
        out.append(_KB2QT.get(t, t.upper() if len(t) == 1 else t[:1].upper() + t[1:]))
    return "+".join(out)


def pretty(combo: str) -> str:
    if not combo:
        return ""
    from . import i18n
    txt = combo_to_qt(combo).replace("Meta", "Win")
    return txt if i18n.LANG == "en" else txt.replace("Ctrl", "Strg")


class HotkeyManager(QObject):
    triggered = Signal(str)

    def __init__(self):
        super().__init__()
        self._handles = []
        self.paused = False

    def set_bindings(self, mapping: dict[str, str]) -> list[str]:
        for h in self._handles:
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
        self._handles = []
        errors = []
        used = {}
        for name, combo in mapping.items():
            if not combo:
                continue
            if combo in used:
                errors.append(f"„{pretty(combo)}“ doppelt belegt ({used[combo]} / {name})")
                continue
            try:
                if name.endswith("_hold"):
                    # gedrueckt halten: Druecken und Loslassen getrennt melden
                    h = keyboard.add_hotkey(combo, self._fire, args=(name + ":down",), suppress=False)
                    self._handles.append(h)
                    h = keyboard.add_hotkey(combo, self._fire, args=(name + ":up",), suppress=False,
                                            trigger_on_release=True)
                else:
                    h = keyboard.add_hotkey(combo, self._fire, args=(name,), suppress=False)
                self._handles.append(h)
                used[combo] = name
            except Exception as e:
                errors.append(f"„{combo}“: {e}")
                log.warning("Hotkey %s=%s: %s", name, combo, e)
        return errors

    def _fire(self, name):
        if not self.paused:
            self.triggered.emit(name)

    def shutdown(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass
