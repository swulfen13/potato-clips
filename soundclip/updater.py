"""Updates: neue Version auf GitHub finden, Installer laden und starten."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from . import __version__
from .config import FROZEN

log = logging.getLogger("soundclip.updater")
REPO = "swulfen13/potato-clips"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"


def _ver(s: str) -> tuple:
    nums = re.findall(r"\d+", s or "")
    return tuple(int(x) for x in (nums + ["0", "0", "0"])[:3])


def check() -> dict | None:
    """Neuere Version? -> {"version", "url" (Installer), "notes", "page"} sonst None."""
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"PotatoClips/{__version__}"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    tag = data.get("tag_name", "")
    if _ver(tag) <= _ver(__version__):
        return None
    url = ""
    for a in data.get("assets", []):
        if a.get("name", "").lower().endswith(".exe") and "setup" in a.get("name", "").lower():
            url = a.get("browser_download_url", "")
    return {"version": tag.lstrip("vV"), "url": url, "notes": data.get("body", "")[:1500],
            "page": data.get("html_url", PAGE)}


def download(url: str, progress=None) -> Path:
    """Installer nach %TEMP% laden. progress(0..1) wird zwischendurch aufgerufen."""
    if not url.startswith("https://github.com/") and not url.startswith("https://objects.githubusercontent.com/"):
        raise ValueError("unerwartete Download-Adresse")
    dest = Path(tempfile.gettempdir()) / Path(url).name
    req = urllib.request.Request(url, headers={"User-Agent": f"PotatoClips/{__version__}"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    return dest


def can_self_update() -> bool:
    return FROZEN


def run_installer(path: Path) -> None:
    """Installer leise starten; er beendet Potato Clips, installiert und startet es neu."""
    subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                     creationflags=0x00000008, close_fds=True, cwd=os.path.dirname(str(path)))
