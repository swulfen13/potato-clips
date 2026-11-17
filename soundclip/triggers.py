"""Sprach-Trigger: ein gesprochenes Wort spielt einen Sound ab.

Die Spracherkennung (Vosk) laeuft komplett lokal. Das Sprachmodell (~45 MB) wird beim ersten Einschalten
einmal heruntergeladen und liegt dann im Datenordner unter models/."""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

from .config import DATA_DIR

log = logging.getLogger("soundclip")

MODELS = {
    "de": ("vosk-model-small-de-0.15", 46_499_967),
    "en": ("vosk-model-small-en-us-0.15", 41_205_931),
}
MODEL_URL = "https://alphacephei.com/vosk/models/{name}.zip"
MODELS_DIR = DATA_DIR / "models"
COOLDOWN = 1.2           # gleicher Sound fruehestens nach so vielen Sekunden nochmal

_UML = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def norm_words(text: str) -> list[str]:
    t = text.lower().translate(_UML)
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    return [w for w in t.split() if w and w != "[unk]"]


def model_dir(lang: str) -> Path:
    return MODELS_DIR / MODELS[lang][0]


def model_ready(lang: str) -> bool:
    d = model_dir(lang)
    return (d / "am" / "final.mdl").exists() and (d / "conf" / "model.conf").exists()


def download_model(lang: str, progress=None, cancel: threading.Event | None = None) -> Path:
    """Sprachmodell herunterladen und entpacken. progress(0..1) wird aus dem Hintergrund-Thread aufgerufen."""
    name, size = MODELS[lang]
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkstemp(suffix=".zip", prefix="pc_model_")[1])
    try:
        req = urllib.request.Request(MODEL_URL.format(name=name), headers={"User-Agent": "PotatoClips"})
        with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or size)
            got = 0
            while True:
                if cancel is not None and cancel.is_set():
                    raise RuntimeError("abgebrochen")
                b = r.read(256 * 1024)
                if not b:
                    break
                f.write(b)
                got += len(b)
                if progress:
                    progress(min(0.97, got / max(1, total)))
        target = MODELS_DIR.resolve()
        stage = MODELS_DIR / (name + ".part")
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        with zipfile.ZipFile(tmp) as z:
            for info in z.infolist():
                out = (stage / info.filename).resolve()
                if not str(out).startswith(str(stage.resolve())):   # keine Pfad-Tricks im Zip
                    raise RuntimeError("Ungültiges Modell-Archiv")
            z.extractall(stage)
        inner = stage / name
        if not (inner / "am" / "final.mdl").exists():
            raise RuntimeError("Modell unvollständig")
        final = target / name
        shutil.rmtree(final, ignore_errors=True)
        os.replace(inner, final)
        shutil.rmtree(stage, ignore_errors=True)
        if progress:
            progress(1.0)
        return final
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


class VoiceTriggers:
    """Hoert das Mikro mit (aus dem Clip-Puffer) und meldet erkannte Trigger-Woerter."""

    def __init__(self, cfg, sounds, fire):
        self.cfg = cfg
        self.sounds = sounds
        self.fire = fire                         # fire(sound_id), aus Hintergrund-Thread
        self.q: "queue.Queue[bytes | None]" = queue.Queue(maxsize=400)
        self.thread: threading.Thread | None = None
        self.running = False
        self.lang = ""
        self.heard = ""                          # zuletzt erkannter Text (Anzeige in den Einstellungen)
        self.heard_at = 0.0
        self.error = ""
        self._rest = np.zeros(0, np.float32)
        self._last_fire: dict[str, float] = {}

    def lang_wanted(self) -> str:
        lang = self.cfg.get("trigger_lang", "auto")
        if lang not in MODELS:
            from . import i18n
            lang = "de" if i18n.LANG == "de" else "en"
        return lang

    def active(self) -> bool:
        return self.running

    def wanted(self) -> bool:
        return bool(self.cfg.get("triggers_enabled")) and any(s.get("trigger") for s in self.sounds.sounds)

    def sync(self):
        """An- oder abschalten, je nach Einstellung (Sprache wechseln = neu starten)."""
        want = bool(self.cfg.get("triggers_enabled")) and model_ready(self.lang_wanted())
        if self.running and (not want or self.lang != self.lang_wanted()):
            self.stop()
        if want and not self.running:
            self.start()

    def start(self):
        self.lang = self.lang_wanted()
        self.running = True
        self.error = ""
        self.thread = threading.Thread(target=self._run, daemon=True, name="voice-triggers")
        self.thread.start()

    def stop(self):
        if not self.running:
            return
        self.running = False
        try:
            self.q.put_nowait(None)
        except queue.Full:
            pass
        t = self.thread
        if t:
            t.join(timeout=2)
        self.thread = None
        self._drain()

    def _drain(self):
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break

    # ---- aus dem Mikro-Thread
    def on_chunk(self, key: str, data: np.ndarray):
        if not self.running or key != "mic" or not len(data):
            return
        mono = data.mean(axis=1) if data.ndim == 2 else data
        buf = np.concatenate([self._rest, mono.astype(np.float32)])
        n = len(buf) - len(buf) % 3
        self._rest = buf[n:]
        if not n:
            return
        x = buf[:n].reshape(-1, 3).mean(axis=1)                 # 48 kHz -> 16 kHz (einfacher Tiefpass)
        pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
        try:
            self.q.put_nowait(pcm)
        except queue.Full:
            pass

    # ---- Erkennung
    def _triggers(self) -> list[tuple[list[str], str]]:
        out = []
        for s in self.sounds.sounds:
            for phrase in str(s.get("trigger") or "").split(","):
                w = norm_words(phrase)
                if w:
                    out.append((w, s["id"]))
        return out

    @staticmethod
    def _count(words: list[str], phrase: list[str]) -> int:
        n = len(phrase)
        return sum(1 for i in range(len(words) - n + 1) if words[i:i + n] == phrase)

    def _run(self):
        try:
            import vosk
            vosk.SetLogLevel(-1)
            model = vosk.Model(str(model_dir(self.lang)))
            rec = vosk.KaldiRecognizer(model, 16000)
        except Exception as e:
            log.exception("Spracherkennung")
            self.error = str(e)
            self.running = False
            return
        log.info("Sprach-Trigger aktiv (%s)", self.lang)
        fired: dict[tuple[str, ...], int] = {}
        triggers = self._triggers()
        last_tr = time.time()
        while self.running:
            try:
                pcm = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            if pcm is None:
                break
            parts = [pcm]                      # kleine Bloecke sammeln (bis ~0,2 s), spart Rechenzeit
            size = len(pcm)
            while size < 6400:
                try:
                    more = self.q.get_nowait()
                except queue.Empty:
                    break
                if more is None:
                    self.running = False
                    break
                parts.append(more)
                size += len(more)
            pcm = b"".join(parts)
            if time.time() - last_tr > 1.0:
                triggers = self._triggers()
                last_tr = time.time()
            try:
                final = rec.AcceptWaveform(pcm)
                text = json.loads(rec.Result() if final else rec.PartialResult()).get("text" if final else "partial", "")
            except Exception:
                log.exception("Spracherkennung")
                continue
            if text:
                self.heard = text
                self.heard_at = time.time()
            words = norm_words(text)
            for phrase, sid in triggers:
                k = tuple(phrase) + (sid,)
                c = self._count(words, phrase)
                if c > fired.get(k, 0):
                    fired[k] = c
                    now = time.time()
                    if now - self._last_fire.get(sid, 0) >= COOLDOWN:
                        self._last_fire[sid] = now
                        try:
                            self.fire(sid)
                        except Exception:
                            pass
            if final:
                fired.clear()
