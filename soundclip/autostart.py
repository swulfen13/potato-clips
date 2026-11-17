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


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Potato Clips"


def _command() -> str:
    if FROZEN:
        return f'"{_pythonw()}" --minimized'
    return f'"{_pythonw()}" "{APP_DIR / "app.py"}" --minimized'


def _run_value() -> str | None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return str(winreg.QueryValueEx(k, RUN_NAME)[0])
    except OSError:
        return None


def is_enabled() -> bool:
    return LINK.exists() or _run_value() is not None


def _make_shortcut(link: Path, args: str) -> None:
    """Nur noch fuer die Entwickler-Version (Startmenue-Eintrag); die App selbst startet kein PowerShell mehr."""
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
    """Autostart ueber den normalen Windows-Eintrag (wie Discord/Spotify) - kein PowerShell, keine Verknuepfung."""
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, _command())
    try:
        LINK.unlink()
    except FileNotFoundError:
        pass


def disable() -> None:
    import winreg
    try:
        LINK.unlink()
    except FileNotFoundError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, RUN_NAME)
    except OSError:
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
        if had_autostart:
            enable()
        elif LINK.exists():                 # alte Autostart-Verknuepfung -> normaler Windows-Eintrag
            enable()
        elif _run_value() not in (None, _command()):
            enable()                        # Programm wurde verschoben -> Pfad aktualisieren
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
