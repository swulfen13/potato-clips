"""Backup & Umzug: alle Sounds, Einstellungen (und optional Clips) in eine .potatobackup-Datei.

Einspielen passiert in zwei Schritten, damit nichts halb ueberschrieben wird, solange die App laeuft:
1. restore_prepare() prueft die Datei und entpackt sie nach DATA_DIR/_restore_pending
2. beim naechsten Start tauscht apply_pending() die Daten aus - der alte Stand wandert nach
   DATA_DIR/_vor_backup_<Zeit>, geht also nie verloren.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from .config import DATA_DIR

log = logging.getLogger("soundclip")
EXT = ".potatobackup"
PENDING = DATA_DIR / "_restore_pending"
FILES = ("config.json", "sounds.json", "stats.json")
DIRS = ("sounds", "clips")
MAX_TOTAL = 20 * 1024 ** 3          # 20 GB entpackt - alles darueber ist kaputt oder boesartig
MAX_RATIO = 200                     # Zip-Bombe: entpackt hoechstens 200x so gross wie gepackt


class BackupError(Exception):
    pass


def _files(include_clips: bool):
    for name in FILES:
        p = DATA_DIR / name
        if p.is_file():
            yield p, name
    for d in DIRS:
        if d == "clips" and not include_clips:
            continue
        base = DATA_DIR / d
        if base.is_dir():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    yield p, p.relative_to(DATA_DIR).as_posix()


def estimate(include_clips: bool) -> int:
    return sum(p.stat().st_size for p, _ in _files(include_clips))


def create(out: str | Path, include_clips: bool, version: str = "", progress=None) -> Path:
    out = Path(out)
    if out.suffix.lower() != EXT:
        out = out.with_suffix(EXT)
    items = list(_files(include_clips))
    total = sum(p.stat().st_size for p, _ in items) or 1
    done = 0
    tmp = out.with_suffix(EXT + ".part")
    n_sounds = n_clips = 0
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as z:
            for p, arc in items:
                # Audio ist schon komprimiert -> nur speichern, geht viel schneller
                ct = zipfile.ZIP_STORED if p.suffix.lower() in (".mp3", ".ogg", ".flac", ".m4a", ".opus") \
                    else zipfile.ZIP_DEFLATED
                z.write(p, arc, compress_type=ct)
                if arc.startswith("sounds/"):
                    n_sounds += 1
                elif arc.startswith("clips/") and arc.endswith("/meta.json"):
                    n_clips += 1
                done += p.stat().st_size
                if progress:
                    progress(done / total)
            z.writestr("potato_backup.json", json.dumps({
                "app": "Potato Clips", "format": 1, "version": version,
                "created": _dt.datetime.now().isoformat(timespec="seconds"),
                "clips": include_clips, "sound_files": n_sounds, "clip_count": n_clips}, ensure_ascii=False))
        tmp.replace(out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return out


def _safe_name(name: str) -> str | None:
    """Nur erlaubte, relative Pfade (kein Zip-Slip, keine fremden Dateien)."""
    if "\\" in name or ":" in name or name.startswith("/"):
        return None
    pp = PurePosixPath(name)
    if any(part in ("..", "", ".") for part in pp.parts):
        return None
    if len(pp.parts) == 1 and pp.parts[0] in FILES + ("potato_backup.json",):
        return name
    if len(pp.parts) >= 2 and pp.parts[0] in DIRS:
        return name
    return None


def inspect(path: str | Path) -> dict:
    """Backup pruefen, ohne etwas zu veraendern. Wirft BackupError mit verstaendlicher Meldung."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise BackupError(f"Das ist keine gültige Backup-Datei ({e}).")
    with z:
        try:
            info = json.loads(z.read("potato_backup.json"))
        except Exception:
            raise BackupError("Das ist keine Potato-Clips-Backup-Datei.")
        if info.get("app") != "Potato Clips" or int(info.get("format", 0)) != 1:
            raise BackupError("Diese Backup-Datei stammt nicht von Potato Clips oder ist zu neu.")
        total = packed = 0
        for zi in z.infolist():
            if zi.is_dir():
                continue
            if _safe_name(zi.filename) is None:
                raise BackupError(f"Ungültiger Eintrag im Backup: {zi.filename}")
            total += zi.file_size
            packed += zi.compress_size
        if total > MAX_TOTAL or (packed and total / packed > MAX_RATIO and total > 2 * 1024 ** 3):
            raise BackupError("Das Backup ist ungewöhnlich groß – wird aus Sicherheitsgründen nicht eingespielt.")
        free = shutil.disk_usage(DATA_DIR).free
        if total * 1.1 > free:
            raise BackupError("Nicht genug freier Speicherplatz für das Backup.")
        info["bytes"] = total
        info["has_config"] = "config.json" in z.namelist()
        return info


def restore_prepare(path: str | Path) -> dict:
    info = inspect(path)
    shutil.rmtree(PENDING, ignore_errors=True)
    PENDING.mkdir(parents=True)
    root = PENDING.resolve()
    try:
        with zipfile.ZipFile(path) as z:
            for zi in z.infolist():
                if zi.is_dir():
                    continue
                name = _safe_name(zi.filename)
                dest = (PENDING / name).resolve()
                if root not in dest.parents:
                    raise BackupError(f"Ungültiger Eintrag im Backup: {zi.filename}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(zi) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
        (PENDING / ".ready").write_text("1", encoding="utf-8")
    except BaseException:
        shutil.rmtree(PENDING, ignore_errors=True)
        raise
    return info


def cancel_pending():
    shutil.rmtree(PENDING, ignore_errors=True)


def apply_pending() -> bool:
    """Beim Start (bevor irgendwas geladen wird): vorbereitetes Backup einspielen."""
    if not (PENDING / ".ready").exists():
        if PENDING.exists():
            shutil.rmtree(PENDING, ignore_errors=True)       # halb entpackt -> wegwerfen
        return False
    keep = DATA_DIR / ("_vor_backup_" + _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    keep.mkdir(parents=True, exist_ok=True)
    try:
        with_clips = (PENDING / "clips").is_dir()
        names = list(FILES) + ["sounds"] + (["clips"] if with_clips else [])
        for n in names:
            cur = DATA_DIR / n
            if cur.exists():
                shutil.move(str(cur), str(keep / n))
        for n in names:
            new = PENDING / n
            if new.exists():
                shutil.move(str(new), str(DATA_DIR / n))
        (DATA_DIR / "sounds").mkdir(exist_ok=True)
        (DATA_DIR / "clips").mkdir(exist_ok=True)
        cfg = DATA_DIR / "config.json"           # Einrichtung nicht nochmal zeigen
        if cfg.exists():
            try:
                d = json.loads(cfg.read_text(encoding="utf-8"))
                d["setup_done"] = True
                d.pop("pending_update", None)
                cfg.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                log.exception("Backup: config anpassen")
        shutil.rmtree(PENDING, ignore_errors=True)
        log.info("Backup eingespielt, alter Stand in %s", keep)
        return True
    except Exception:
        log.exception("Backup einspielen - alter Stand wird zurueckgeholt")
        for n in list(FILES) + list(DIRS):
            old = keep / n
            if old.exists():
                cur = DATA_DIR / n
                if cur.is_dir():
                    shutil.rmtree(cur, ignore_errors=True)
                elif cur.exists():
                    cur.unlink()
                shutil.move(str(old), str(cur))
        shutil.rmtree(PENDING, ignore_errors=True)
        return False
