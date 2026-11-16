"""Clips schnell teilen: als MP3 speichern und als Datei in die Zwischenablage legen
(in Discord dann einfach Strg+V)."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import numpy as np
import soundfile as sf

from .capture import safe_name
from .config import EXPORT_DIR, SR

SHARE_DIR = EXPORT_DIR / "Zum Teilen"
DISCORD_LIMIT = 9.5 * 1024 * 1024       # Discord erlaubt ohne Nitro 10 MB


def encode(data: np.ndarray, name: str) -> Path:
    """MP3 (klein, ueberall abspielbar); falls der MP3-Encoder fehlt: OGG."""
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%H%M%S")
    base = SHARE_DIR / f"{safe_name(name)}_{stamp}"
    data = np.clip(np.asarray(data, np.float32), -1.0, 1.0)
    for ext, kw in ((".mp3", {"format": "MP3", "subtype": "MPEG_LAYER_III"}), (".ogg", {"format": "OGG"})):
        path = base.with_suffix(ext)
        try:
            sf.write(str(path), data, SR, **kw)
            if path.exists() and path.stat().st_size > 0:
                return path
        except Exception:
            try:
                path.unlink()
            except Exception:
                pass
    path = base.with_suffix(".wav")
    sf.write(str(path), data, SR, subtype="PCM_16")
    return path


def copy_file(path: str | Path) -> None:
    """Datei so in die Zwischenablage legen, dass man sie in Discord/Explorer einfuegen kann (GUI-Thread!)."""
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtWidgets import QApplication
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(path))])
    QApplication.clipboard().setMimeData(md)


def too_big(path: str | Path) -> bool:
    return Path(path).stat().st_size > DISCORD_LIMIT
