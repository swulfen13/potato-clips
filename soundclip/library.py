"""Soundboard-Sounds und gespeicherte Clips/Aufnahmen."""
from __future__ import annotations

import json
import shutil
import threading
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf

from .capture import safe_name
from .config import CLIPS_DIR, SOUNDS_DIR, SOUNDS_FILE, SR
from .effects import apply_chain
from .loudness import apply_trim, norm_gain, silence_bounds
from .mixer import load_audio

AUDIO_EXT = {".wav", ".mp3", ".ogg", ".flac", ".aiff", ".aif", ".opus"}
COLORS = ["#7c5cff", "#ff5c8a", "#2ec4b6", "#ff9f1c", "#3a86ff", "#8ac926", "#e63946", "#f15bb5"]


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    i = 2
    while True:
        p = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not p.exists():
            return p
        i += 1


class SoundLibrary:
    def __init__(self):
        self.lock = threading.RLock()
        self._fx_cache: dict = {}
        self.sounds: list[dict] = []
        if SOUNDS_FILE.exists():
            try:
                self.sounds = json.loads(SOUNDS_FILE.read_text(encoding="utf-8"))
            except Exception:
                self.sounds = []
        self.sounds = [s for s in self.sounds if (SOUNDS_DIR / s.get("file", "")).exists()]

    def save(self):
        with self.lock:
            SOUNDS_FILE.write_text(json.dumps(self.sounds, indent=2, ensure_ascii=False), encoding="utf-8")

    def path(self, s: dict) -> Path:
        return SOUNDS_DIR / s["file"]

    def get(self, sid: str) -> dict | None:
        return next((s for s in self.sounds if s["id"] == sid), None)

    def _new_entry(self, name: str, file: str) -> dict:
        return {"id": uuid.uuid4().hex[:10], "name": name, "file": file, "hotkey": "", "volume": 1.0,
                "color": COLORS[len(self.sounds) % len(COLORS)], "folder": "", "fav": False, "trigger": ""}

    def add_file(self, src: str | Path, auto_trim: bool = False, folder: str = "") -> dict | None:
        src = Path(src)
        if src.suffix.lower() not in AUDIO_EXT or not src.exists():
            return None
        data = load_audio(src)  # prueft, ob die Datei lesbar ist (wirft sonst)
        dst = _unique(SOUNDS_DIR / (safe_name(src.stem) + src.suffix.lower()))
        shutil.copy2(src, dst)
        with self.lock:
            e = self._new_entry(src.stem, dst.name)
            e["folder"] = folder
            if auto_trim:
                b = silence_bounds(data)
                if b:
                    e["trim"] = list(b)
            e["norm"] = norm_gain(apply_trim(data, e.get("trim")))
            self.sounds.append(e)
            self.save()
        return e

    def add_array(self, name: str, data: np.ndarray, folder: str = "") -> dict:
        dst = _unique(SOUNDS_DIR / (safe_name(name) + ".wav"))
        sf.write(str(dst), np.clip(data, -1, 1), SR, subtype="PCM_16")
        with self.lock:
            e = self._new_entry(name, dst.name)
            e["folder"] = folder
            e["norm"] = norm_gain(data)
            self.sounds.append(e)
            self.save()
        return e

    def update(self, sid: str, **kw):
        with self.lock:
            s = self.get(sid)
            if s:
                s.update(kw)
                self.save()

    def remove(self, sid: str):
        with self.lock:
            s = self.get(sid)
            if not s:
                return
            self.sounds.remove(s)
            self.save()
        try:
            self.path(s).unlink()
        except Exception:
            pass

    def move(self, sid: str, delta: int):
        with self.lock:
            s = self.get(sid)
            if not s:
                return
            i = self.sounds.index(s)
            j = max(0, min(len(self.sounds) - 1, i + delta))
            self.sounds.insert(j, self.sounds.pop(i))
            self.save()

    def audio_raw(self, s: dict) -> np.ndarray:
        """Die ganze Datei, ohne Zuschnitt."""
        return load_audio(self.path(s))

    def audio(self, s: dict) -> np.ndarray:
        """So wie er abgespielt wird: zugeschnitten."""
        return apply_trim(load_audio(self.path(s)), s.get("trim"))

    def set_trim(self, sid: str, trim) -> None:
        """Zuschnitt setzen (None = ganze Datei) und die Lautheit neu messen."""
        with self.lock:
            s = self.get(sid)
            if not s:
                return
            if trim:
                s["trim"] = [round(float(trim[0]), 3), round(float(trim[1]), 3)]
            else:
                s.pop("trim", None)
            s.pop("norm", None)
        try:
            data = self.audio(s)
            with self.lock:
                s["norm"] = norm_gain(data)
        except Exception:
            pass
        self.save()

    # ---- Effekt pro Sound
    @staticmethod
    def fx_chain(s: dict) -> list:
        """Effektkette eines Sounds ({"preset": Stimmeffekt, "amount": 0..1}) - leer, wenn keiner gesetzt ist."""
        from .effects import VOICE_PRESETS
        fx = s.get("fx") or {}
        pre = VOICE_PRESETS.get(fx.get("preset", "")) if isinstance(fx, dict) else None
        if not pre:
            return []
        scale = 0.4 + 1.2 * float(np.clip(float(fx.get("amount", 0.5)), 0.0, 1.0))
        return [{"type": k, "amount": min(1.0, a * scale)} for k, a in pre[1]]

    def playable(self, s: dict, normalize: bool) -> tuple[np.ndarray, float]:
        """Audio so, wie es abgespielt wird (zugeschnitten, mit Effekt) und die passende Lautstaerke.
        Sounds mit Effekt werden einmal berechnet und dann zwischengespeichert."""
        chain = self.fx_chain(s)
        if not chain:
            data = self.audio(s)
            return data, self.gain_for(s, data, normalize)
        try:
            mtime = self.path(s).stat().st_mtime
        except OSError:
            mtime = 0
        key = (s["id"], mtime, tuple(s.get("trim") or ()), repr(chain))
        hit = self._fx_cache.get(key)
        if hit is None:
            processed = apply_chain(self.audio(s), chain)
            hit = (processed, norm_gain(processed))
            if len(self._fx_cache) > 24:
                self._fx_cache.clear()
            self._fx_cache[key] = hit
        data, ng = hit
        g = float(s.get("volume", 1.0))
        return data, (g * ng if normalize else g)

    def gain_for(self, s: dict, data: np.ndarray | None, normalize: bool) -> float:
        """Abspiel-Lautstaerke: eigene Lautstaerke x Angleichung (wird beim ersten Mal gemessen)."""
        g = float(s.get("volume", 1.0))
        if not normalize:
            return g
        n = s.get("norm")
        if n is None and data is not None:
            n = norm_gain(data)
            with self.lock:
                s["norm"] = n
            self.save()
        return g * float(n if n is not None else 1.0)

    # ---- Ordner & Favoriten
    def folders(self, extra=()) -> list[str]:
        out: list[str] = []
        for f in list(extra) + [s.get("folder", "") for s in self.sounds]:
            if f and f not in out:
                out.append(f)
        return out

    def rename_folder(self, old: str, new: str):
        with self.lock:
            for s in self.sounds:
                if s.get("folder", "") == old:
                    s["folder"] = new
            self.save()


class ClipLibrary:
    def list(self) -> list[dict]:
        out = []
        for d in CLIPS_DIR.iterdir():
            m = d / "meta.json"
            if d.is_dir() and m.exists():
                try:
                    meta = json.loads(m.read_text(encoding="utf-8"))
                    meta["_dir"] = str(d)
                    out.append(meta)
                except Exception:
                    pass
        out.sort(key=lambda m: m.get("created", ""), reverse=True)
        return out

    def dir(self, meta: dict) -> Path:
        return Path(meta.get("_dir") or (CLIPS_DIR / meta["id"]))

    def save_meta(self, meta: dict):
        d = self.dir(meta)
        clean = {k: v for k, v in meta.items() if not k.startswith("_")}
        (d / "meta.json").write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")

    def delete(self, meta: dict):
        shutil.rmtree(self.dir(meta), ignore_errors=True)

    def stems(self, meta: dict) -> dict[str, np.ndarray]:
        d = self.dir(meta)
        out = {}
        for st in meta.get("stems", []):
            p = d / st["file"]
            if p.exists():
                out[st["key"]] = load_audio(p)
        return out

    def from_sound(self, name: str, data: np.ndarray) -> dict:
        """Einen Soundboard-Sound als Clip anlegen, damit man ihn im Editor bearbeiten kann."""
        import datetime as _dt
        stamp = _dt.datetime.now()
        cid = stamp.strftime("%Y%m%d-%H%M%S-%f")[:-3]
        d = CLIPS_DIR / cid
        d.mkdir(parents=True, exist_ok=True)
        sf.write(str(d / "sound.wav"), np.clip(data, -1, 1), SR, subtype="PCM_16")
        meta = {"id": cid, "name": name, "created": stamp.isoformat(), "duration": len(data) / SR,
                "kind": "sound", "stems": [{"key": "sound", "label": "Sound", "file": "sound.wav",
                                             "peak": float(np.abs(data).max()) if len(data) else 0}],
                "edit": {}, "_dir": str(d)}
        self.save_meta(meta)
        return meta


def mix_stems(meta: dict, stems: dict[str, np.ndarray], edit: dict) -> np.ndarray:
    """Spuren nach Auswahl/Lautstaerke mischen (ohne Schnitt/Effekte)."""
    length = max((len(a) for a in stems.values()), default=0)
    mix = np.zeros((length, 2), np.float32)
    settings = edit.get("stems", {})
    for st in meta.get("stems", []):
        a = stems.get(st["key"])
        if a is None:
            continue
        s = settings.get(st["key"], {})
        if not s.get("on", True):
            continue
        mix[: len(a)] += a * float(s.get("gain", 1.0))
    return mix


def render(meta: dict, stems: dict[str, np.ndarray], edit: dict) -> np.ndarray:
    mix = mix_stems(meta, stems, edit)
    dur = len(mix) / SR
    start = max(0.0, float(edit.get("start", 0.0)))
    end = float(edit.get("end", dur) or dur)
    end = min(max(end, start + 0.01), dur)
    mix = mix[int(start * SR):int(end * SR)]
    return apply_chain(mix, edit.get("effects", []))
