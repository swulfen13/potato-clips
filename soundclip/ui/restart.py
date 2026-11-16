"""Potato Clips neu starten (z. B. nach Wechsel von Design oder Sprache)."""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtWidgets import QApplication

from ..config import APP_DIR, FROZEN

DETACHED = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def restart_app() -> None:
    args = [sys.executable] if FROZEN else [sys.executable, str(APP_DIR / "app.py")]
    args += ["--wait-pid", str(os.getpid())]
    try:
        subprocess.Popen(args, cwd=str(APP_DIR), creationflags=DETACHED, close_fds=True)
    except Exception:
        return
    for w in QApplication.topLevelWidgets():
        if hasattr(w, "quit") and hasattr(w, "ctl"):
            w.quit()
            return
    QApplication.quit()
