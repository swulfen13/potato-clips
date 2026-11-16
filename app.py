"""Potato Clips – Soundboard, Clips (letzte X Sekunden), Aufnahme pro App, Effekte, Overlay.

Start:  start.bat   (oder: .venv\\Scripts\\pythonw.exe app.py)
"""
from __future__ import annotations

import sys

if __name__ == "__main__" and "--fxworker" in sys.argv:
    # Effekt-Prozess fuer die Live-Stimme (vom Audio-Helfer gestartet, ohne Oberflaeche)
    from soundclip.fxworker import main as _fx_main
    sys.exit(_fx_main())

import logging
import traceback

from PySide6.QtCore import Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from soundclip.config import LOG_FILE

INSTANCE_KEY = "PotatoClips-single-instance"


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")] +
                 ([logging.StreamHandler()] if sys.stdout else []),
    )


def main():
    setup_logging()
    log = logging.getLogger("soundclip")

    try:  # eigenes Taskleisten-Symbol statt Python-Symbol
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PotatoClips.App")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Potato Clips")
    app.setQuitOnLastWindowClosed(False)

    # nur eine Instanz: zweite Instanz holt das Fenster nach vorne
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        return 0

    from soundclip.controller import Controller
    from soundclip.ui.main_window import MainWindow
    from soundclip.ui.widgets import STYLE, app_icon

    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())

    def excepthook(et, ev, tb):
        msg = "".join(traceback.format_exception(et, ev, tb))
        log.error("Unbehandelter Fehler:\n%s", msg)
        try:
            QMessageBox.critical(None, "Potato Clips – Fehler", f"{ev}\n\nDetails in {LOG_FILE}")
        except Exception:
            pass

    sys.excepthook = excepthook

    try:
        from soundclip import autostart
        autostart.migrate_old_name()
        autostart.ensure_desktop_shortcut()
    except Exception:
        log.exception("Verknuepfungen")

    ctl = Controller()
    win = MainWindow(ctl)
    ctl.start()

    server = QLocalServer()
    QLocalServer.removeServer(INSTANCE_KEY)
    server.listen(INSTANCE_KEY)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.show_normal()))

    if "--minimized" in sys.argv:
        win.hide()
    else:
        win.show()
    log.info("Potato Clips gestartet")
    rc = app.exec()
    return rc


if __name__ == "__main__":
    sys.exit(main())
