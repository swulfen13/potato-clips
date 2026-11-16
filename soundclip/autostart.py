"""Autostart-Verknuepfung im Windows-Autostart-Ordner (startet minimiert im Tray)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .config import APP_DIR, FROZEN, ICON_FILE

STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
LINK = STARTUP_DIR / "Potato Clips.lnk"
ICON = ICON_FILE
OLD_LINKS = [STARTUP_DIR / "SoundClip.lnk",
             Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "SoundClip.lnk"]


def _pythonw() -> Path:
    if FROZEN:
        return Path(sys.executable)
    p = APP_DIR / ".venv" / "Scripts" / "pythonw.exe"
    if p.exists():
        return p
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return w if w.exists() else exe


def is_enabled() -> bool:
    return LINK.exists()


def _make_shortcut(link: Path, args: str) -> None:
    env = dict(os.environ)
    env.update(SC_LNK=str(link), SC_TARGET=str(_pythonw()), SC_ARGS=args, SC_DIR=str(APP_DIR),
               SC_ICON=(str(sys.executable) if FROZEN else str(ICON)) if (FROZEN or ICON.exists()) else "")
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:SC_LNK);"
          "$s.TargetPath=$env:SC_TARGET;$s.Arguments=$env:SC_ARGS;$s.WorkingDirectory=$env:SC_DIR;"
          "$s.Description='Potato Clips - Soundboard & Clips';"
          "if($env:SC_ICON){$s.IconLocation=$env:SC_ICON};$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env=env, check=True,
                   capture_output=True, timeout=20, creationflags=0x08000000)


def enable() -> None:
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)
    _make_shortcut(LINK, "--minimized" if FROZEN else f'"{APP_DIR / "app.py"}" --minimized')


def disable() -> None:
    try:
        LINK.unlink()
    except FileNotFoundError:
        pass


def migrate_old_name() -> None:
    """Aus SoundClip wird Potato Clips: alte Verknuepfungen ersetzen."""
    had_autostart = OLD_LINKS[0].exists()
    for p in OLD_LINKS:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass
    try:
        if had_autostart and not LINK.exists():
            enable()
    except Exception:
        pass


def ensure_desktop_shortcut() -> None:
    """Startmenue-Eintrag 'Potato Clips' anlegen (einmalig), damit man es per Windows-Suche findet."""
    if FROZEN:      # macht der Installer
        return
    menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Potato Clips.lnk"
    if not menu.exists():
        try:
            _make_shortcut(menu, f'"{APP_DIR / "app.py"}"')
        except Exception:
            pass
