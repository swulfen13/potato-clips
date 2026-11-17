"""Maus-Seitentasten und Gamepad-Knoepfe als Hotkeys.

Maus: Windows "Raw Input" (RIDEV_INPUTSINK) - wir werden nur benachrichtigt und haengen NICHT in der
Eingabekette. Die Maus kann dadurch nie haken, auch wenn Python gerade beschaeftigt ist.
Gamepad: XInput (Xbox- und kompatible Controller), 100x pro Sekunde abgefragt.

Kombinationen im Konfig-Format:
  "mouse:x1" (Seitentaste hinten / Maus 4), "mouse:x2" (vorne / Maus 5), "mouse:middle", auch mit Tastatur davor:
  "ctrl+mouse:x2". Gamepad: "pad:a", "pad:lb+a", "pad:back+start" (alle gleichzeitig gedrueckt)."""
from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes

log = logging.getLogger("soundclip.inputs")

MOUSE_BUTTONS = {"x1": "Maus 4", "x2": "Maus 5", "middle": "Mausrad-Klick"}
PAD_BITS = {
    "up": 0x0001, "down": 0x0002, "left": 0x0004, "right": 0x0008, "start": 0x0010, "back": 0x0020,
    "ls": 0x0040, "rs": 0x0080, "lb": 0x0100, "rb": 0x0200, "a": 0x1000, "b": 0x2000, "x": 0x4000, "y": 0x8000,
}
PAD_NAMES = {"up": "↑", "down": "↓", "left": "←", "right": "→", "start": "Start", "back": "Back", "ls": "L3",
             "rs": "R3", "lb": "LB", "rb": "RB", "lt": "LT", "rt": "RT", "a": "A", "b": "B", "x": "X", "y": "Y"}
PAD_ORDER = ["lb", "rb", "lt", "rt", "back", "start", "ls", "rs", "up", "down", "left", "right", "a", "b", "x", "y"]
KB_MODS = ("ctrl", "alt", "shift", "windows")
WATCHER = None                         # die eine gemeinsame Abfrage (Raw Input gibt es nur einmal pro Programm)


def shared(callback=None):
    """Gemeinsame InputWatcher-Instanz - zwei Raw-Input-Fenster wuerden sich gegenseitig die Maus wegnehmen."""
    global WATCHER
    if WATCHER is None:
        WATCHER = InputWatcher(callback or (lambda c, p: None))
    elif callback is not None:
        WATCHER.callback = callback
    return WATCHER


def is_special(combo: str) -> bool:
    return "mouse:" in combo or "pad:" in combo


def parse(combo: str):
    """-> ("mouse", Taste, Modifikatoren) | ("pad", frozenset(Knoepfe)) | None"""
    if "mouse:" in combo:
        pre, _, btn = combo.partition("mouse:")
        mods = tuple(m for m in pre.split("+") if m)
        return ("mouse", btn, mods) if btn in MOUSE_BUTTONS else None
    if combo.startswith("pad:"):
        btns = frozenset(b for b in combo[4:].split("+") if b in PAD_NAMES)
        return ("pad", btns) if btns else None
    return None


def pad_combo(buttons) -> str:
    return "pad:" + "+".join(b for b in PAD_ORDER if b in buttons)


def pretty(combo: str) -> str:
    from .i18n import tr
    p = parse(combo)
    if not p:
        return combo
    if p[0] == "mouse":
        mods = [{"ctrl": "Strg" if _lang_de() else "Ctrl", "windows": "Win"}.get(m, m.capitalize()) for m in p[2]]
        return "+".join(mods + [tr(MOUSE_BUTTONS[p[1]])])
    return "🎮 " + "+".join(PAD_NAMES[b] for b in PAD_ORDER if b in p[1])


def _lang_de() -> bool:
    from . import i18n
    return i18n.LANG == "de"


# ---------------------------------------------------------------- Raw Input (Maus)
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_INPUT = 0x00FF
WM_QUIT = 0x0012
RIDEV_INPUTSINK = 0x00000100
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
HWND_MESSAGE = wintypes.HWND(-3)
_RI_FLAGS = {0x0010: ("middle", True), 0x0020: ("middle", False), 0x0040: ("x1", True), 0x0080: ("x1", False),
             0x0100: ("x2", True), 0x0200: ("x2", False)}

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT), ("dwFlags", wintypes.DWORD),
                ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD), ("hDevice", wintypes.HANDLE),
                ("wParam", wintypes.WPARAM)]


class _RAWMOUSE_BUTTONS(ctypes.Structure):
    _fields_ = [("usButtonFlags", wintypes.USHORT), ("usButtonData", wintypes.USHORT)]


class _RAWMOUSE_U(ctypes.Union):
    _anonymous_ = ("b",)
    _fields_ = [("ulButtons", wintypes.ULONG), ("b", _RAWMOUSE_BUTTONS)]


class RAWMOUSE(ctypes.Structure):
    # wie in winuser.h: nach usFlags kommt eine Union mit 4-Byte-Ausrichtung (usButtonFlags liegt bei Offset 4!)
    _anonymous_ = ("u",)
    _fields_ = [("usFlags", wintypes.USHORT), ("u", _RAWMOUSE_U),
                ("ulRawButtons", wintypes.ULONG), ("lLastX", wintypes.LONG), ("lLastY", wintypes.LONG),
                ("ulExtraInformation", wintypes.ULONG)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(wintypes.UINT),
                                   wintypes.UINT]
user32.GetRawInputData.restype = wintypes.UINT
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


# ---------------------------------------------------------------- XInput (Gamepad)
class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [("wButtons", wintypes.WORD), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short),
                ("sThumbRY", ctypes.c_short)]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", XINPUT_GAMEPAD)]


def _load_xinput():
    for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            dll = ctypes.WinDLL(name)
            dll.XInputGetState.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
            dll.XInputGetState.restype = wintypes.DWORD
            return dll
        except OSError:
            continue
    return None


class InputWatcher:
    """Meldet Maus-/Gamepad-Kombinationen. callback(combo, pressed) kommt aus einem Hintergrund-Thread."""

    def __init__(self, callback):
        self.callback = callback
        self.combos: set[str] = set()
        self.capture = None            # Aufnahme fuer das Hotkey-Feld: callback(combo)
        self._mouse_thread = None
        self._mouse_tid = 0
        self._pad_thread = None
        self._running = False
        self._held: set[str] = set()   # gerade ausgeloeste (gedrueckte) Kombinationen
        self._pad_down: frozenset = frozenset()
        self._cap_pad: set[str] = set()
        self.pad_connected = False
        self.tracking = False          # Sound-Rad: Mausbewegung mitzaehlen (auch wenn das Spiel den Zeiger festhaelt)
        self.dx = 0
        self.dy = 0
        self.mouse_ok = False

    # ---- Steuerung
    def set_combos(self, combos):
        self.combos = {c for c in combos if parse(c)}
        self._ensure()

    def track_motion(self, on: bool):
        self.dx = self.dy = 0
        self.tracking = on
        if on:
            self._ensure(mouse=True)

    def start_capture(self, fn):
        self.capture = fn
        self._cap_pad = set()
        self._ensure(force=True)

    def stop_capture(self):
        self.capture = None
        self._ensure()

    def _ensure(self, force=False, mouse=False):
        need_mouse = force or mouse or self.tracking or any(parse(c)[0] == "mouse" for c in self.combos)
        need_pad = force or any(parse(c)[0] == "pad" for c in self.combos)
        self._running = True
        if need_mouse and not (self._mouse_thread and self._mouse_thread.is_alive()):
            self._mouse_thread = threading.Thread(target=self._mouse_loop, daemon=True, name="mouse-rawinput")
            self._mouse_thread.start()
        if need_pad and not (self._pad_thread and self._pad_thread.is_alive()):
            self._pad_thread = threading.Thread(target=self._pad_loop, daemon=True, name="gamepad")
            self._pad_thread.start()

    def shutdown(self):
        self._running = False
        if self._mouse_tid:
            user32.PostThreadMessageW(self._mouse_tid, WM_QUIT, 0, 0)

    # ---- Ereignisse
    def _mods(self):
        try:
            import keyboard
            return tuple(m for m in KB_MODS if keyboard.is_pressed(m))
        except Exception:
            return ()

    def _mouse_event(self, btn: str, down: bool):
        if down:
            mods = self._mods()
            combo = "+".join(mods + ("mouse:" + btn,))
            cap = self.capture
            if cap:
                self.capture = None
                cap(combo)
                return
            if combo in self.combos:
                self._held.add(combo)
                self.callback(combo, True)
        else:
            for combo in [c for c in self._held if c.endswith("mouse:" + btn)]:
                self._held.discard(combo)
                self.callback(combo, False)

    def _pad_update(self, pressed: frozenset):
        prev = self._pad_down
        self._pad_down = pressed
        if self.capture:
            self._cap_pad |= set(pressed)
            if not pressed and self._cap_pad:          # alles losgelassen -> aufgenommen
                cap, self.capture = self.capture, None
                cap(pad_combo(self._cap_pad))
                self._cap_pad = set()
            return
        for combo in self.combos:
            p = parse(combo)
            if p[0] != "pad":
                continue
            btns = p[1]
            now = btns <= pressed
            was = btns <= prev
            if now and not was and combo not in self._held:
                self._held.add(combo)
                self.callback(combo, True)
            elif not now and combo in self._held:
                self._held.discard(combo)
                self.callback(combo, False)

    # ---- Threads
    def _mouse_loop(self):
        self._mouse_tid = kernel32.GetCurrentThreadId()
        hinst = kernel32.GetModuleHandleW(None)
        cls_name = "PotatoClipsRawInput%d" % self._mouse_tid

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_INPUT:
                try:
                    size = wintypes.UINT(ctypes.sizeof(RAWINPUT))
                    buf = RAWINPUT()
                    if user32.GetRawInputData(lparam, RID_INPUT, ctypes.byref(buf), ctypes.byref(size),
                                              ctypes.sizeof(RAWINPUTHEADER)) != 0xFFFFFFFF \
                            and buf.header.dwType == RIM_TYPEMOUSE:
                        flags = buf.mouse.usButtonFlags
                        if self.tracking and not (buf.mouse.usFlags & 0x01):     # relative Bewegung
                            self.dx += buf.mouse.lLastX
                            self.dy += buf.mouse.lLastY
                        if flags:
                            for bit, (btn, down) in _RI_FLAGS.items():
                                if flags & bit:
                                    self._mouse_event(btn, down)
                except Exception:
                    log.exception("Raw Input")
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROC(wndproc)          # Referenz halten (sonst raeumt Python sie weg)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.lpszClassName = cls_name
        if not user32.RegisterClassW(ctypes.byref(wc)):
            log.warning("Raw Input: RegisterClass fehlgeschlagen (%s)", ctypes.get_last_error())
            return
        hwnd = user32.CreateWindowExW(0, cls_name, "PotatoClipsInput", 0, 0, 0, 0, 0, HWND_MESSAGE, None, hinst, None)
        if not hwnd:
            log.warning("Raw Input: Fenster fehlgeschlagen (%s)", ctypes.get_last_error())
            return
        rid = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, hwnd)      # Generic Desktop / Maus
        if not user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)):
            log.warning("Raw Input: Registrierung fehlgeschlagen (%s)", ctypes.get_last_error())
            return
        log.info("Maustasten aktiv (Raw Input)")
        self.mouse_ok = True
        msg = wintypes.MSG()
        while self._running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.DestroyWindow(hwnd)
        user32.UnregisterClassW(cls_name, hinst)
        self._mouse_tid = 0
        self.mouse_ok = False

    def _pad_loop(self):
        x = _load_xinput()
        if x is None:
            log.warning("XInput nicht gefunden - keine Gamepad-Tasten")
            return
        state = XINPUT_STATE()
        idle = 0
        while self._running:
            pressed = set()
            connected = False
            for i in range(4):
                if x.XInputGetState(i, ctypes.byref(state)) == 0:
                    connected = True
                    w = state.Gamepad.wButtons
                    pressed |= {name for name, bit in PAD_BITS.items() if w & bit}
                    if state.Gamepad.bLeftTrigger > 128:
                        pressed.add("lt")
                    if state.Gamepad.bRightTrigger > 128:
                        pressed.add("rt")
            self.pad_connected = connected
            fs = frozenset(pressed)
            if fs != self._pad_down:
                try:
                    self._pad_update(fs)
                except Exception:
                    log.exception("Gamepad")
            # ohne Controller seltener nachschauen (spart CPU)
            if connected:
                idle = 0
                time.sleep(0.01)
            else:
                idle += 1
                time.sleep(0.5)
