"""Erzeugt assets/potato_clips.ico (fuer Verknuepfungen und den Helfer) und eine PNG-Vorschau."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PySide6.QtGui import QGuiApplication
app = QGuiApplication(sys.argv)
from soundclip.autostart import ICON
from soundclip.ui.widgets import _potato_pixmap, save_icon_file
save_icon_file(ICON)
_potato_pixmap(256).save(os.path.join(os.path.dirname(ICON), "potato_clips_256.png"))
for s in (16, 32):
    _potato_pixmap(s).scaled(128, 128).save(os.path.join(os.path.dirname(ICON), f"potato_clips_{s}_preview.png"))
print("Icon:", ICON, os.path.getsize(ICON), "Bytes")
