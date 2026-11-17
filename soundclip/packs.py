"""Sound-Packs: Sounds als eine Datei (.potatopack = ZIP) mit Freunden teilen."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from .capture import safe_name
from .config import SOUNDS_DIR

PACK_EXT = ".potatopack"
MAX_FILE = 60 * 1024 * 1024       # einzelne Datei hoechstens 60 MB
MAX_TOTAL = 400 * 1024 * 1024     # ganzes Pack hoechstens 400 MB (entpackt)


def export_pack(lib, sound_ids: list[str], dest: str | Path) -> int:
    """Gewaehlte Sounds (Name, Lautstaerke, Farbe, Datei) in ein Pack schreiben. Hotkeys bleiben privat."""
    dest = Path(dest)
    if dest.suffix.lower() != PACK_EXT:
        dest = dest.with_suffix(PACK_EXT)
    items = []
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for sid in sound_ids:
            s = lib.get(sid)
            if not s:
                continue
            src = lib.path(s)
            if not src.exists():
                continue
            arc = f"sounds/{len(items):03d}_{safe_name(s['name'])}{src.suffix.lower()}"
            z.write(src, arc)
            item = {"name": s["name"], "file": arc, "volume": float(s.get("volume", 1.0)),
                    "color": s.get("color", ""), "folder": s.get("folder", "")}
            if s.get("trim"):
                item["trim"] = list(s["trim"])
            items.append(item)
        z.writestr("pack.json", json.dumps({"format": 1, "app": "Potato Clips", "sounds": items},
                                           indent=2, ensure_ascii=False))
    return len(items)


def import_pack(lib, src: str | Path) -> int:
    """Sounds aus einem Pack ins Soundboard holen (ohne Hotkeys, gleichnamige bleiben erhalten)."""
    from .library import AUDIO_EXT, _unique
    src = Path(src)
    n = 0
    with zipfile.ZipFile(src) as z:
        meta = json.loads(z.read("pack.json").decode("utf-8"))
        total = 0
        for item in meta.get("sounds", []):
            arc = str(item.get("file", ""))
            if not arc.startswith("sounds/") or ".." in arc or "\\" in arc:
                continue                          # nur Dateien aus dem sounds/-Ordner, keine Pfad-Tricks
            ext = Path(arc).suffix.lower()
            if ext not in AUDIO_EXT:
                continue
            try:
                info = z.getinfo(arc)
            except KeyError:
                continue
            total += info.file_size
            if info.file_size > MAX_FILE or total > MAX_TOTAL:
                break
            name = str(item.get("name") or Path(arc).stem)[:80]
            dst = _unique(SOUNDS_DIR / (safe_name(name) + ext))
            with z.open(info) as fin, open(dst, "wb") as fout:
                fout.write(fin.read())
            with lib.lock:
                e = lib._new_entry(name, dst.name)
                try:
                    e["volume"] = max(0.0, min(2.0, float(item.get("volume", 1.0))))
                except (TypeError, ValueError):
                    pass
                col = str(item.get("color", ""))
                if col.startswith("#") and len(col) in (4, 7):
                    e["color"] = col
                e["folder"] = str(item.get("folder") or "")[:40]
                try:
                    t = item.get("trim")
                    if t and len(t) == 2 and 0 <= float(t[0]) < float(t[1]):
                        e["trim"] = [float(t[0]), float(t[1])]
                except (TypeError, ValueError):
                    pass
                lib.sounds.append(e)
                lib.save()
            n += 1
    return n
