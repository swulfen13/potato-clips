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
import struct
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
        _vocab_cache.pop(lang, None)
        shutil.rmtree(stage, ignore_errors=True)
        if progress:
            progress(1.0)
        return final
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


# ---------------------------------------------------------------- Wortschatz des Modells

_vocab_cache: dict[str, set] = {}


def vocab(lang: str) -> set[str]:
    """Alle Woerter, die das Sprachmodell kennt (stehen als Symboltabelle in graph/Gr.fst)."""
    if lang in _vocab_cache:
        return _vocab_cache[lang]
    words: set[str] = set()
    try:
        with open(model_dir(lang) / "graph" / "Gr.fst", "rb") as f:
            def rstr():
                n = struct.unpack("<i", f.read(4))[0]
                return f.read(n).decode("utf-8", "replace")
            if struct.unpack("<i", f.read(4))[0] != 2125659606:
                raise ValueError("kein FST")
            rstr(), rstr()
            _ver, flags = struct.unpack("<ii", f.read(8))
            f.read(32)
            if flags & 1:
                if struct.unpack("<i", f.read(4))[0] != 2125658996:
                    raise ValueError("keine Symboltabelle")
                rstr()
                _avail, size = struct.unpack("<qq", f.read(16))
                for _ in range(size):
                    w = rstr()
                    f.read(8)
                    words.add(w)
    except Exception:
        log.exception("Wortschatz lesen")
        return words                 # nicht merken - nach dem Download nochmal versuchen
    _vocab_cache[lang] = words
    return words


def known(lang: str, phrase: str) -> bool:
    """Kennt das Modell alle Woerter? (Unbekannte Woerter kann es nie erkennen.)"""
    v = vocab(lang)
    ws = norm_words(phrase)
    return bool(ws) and (not v or all(w in v for w in ws))


# ---------------------------------------------------------------- Sprachbefehle ("Potato, clip Spotify")

WAKE = {"de": ["potato", "kartoffel"], "en": ["potato"]}
NON_GAME = {"discord", "spotify", "chrome", "brave", "firefox", "msedge", "opera", "opera_gx", "steam", "steamwebhelper",
            "epicgameslauncher", "claude", "whatsapp", "whatsapp.root", "teams", "ms-teams", "zoom", "explorer",
            "obs64", "obs", "potatoclips", "python", "pythonw", "telegram", "slack", "vlc", "pcaui", "battle.net",
            "riotclientservices", "ea", "eadesktop", "ubisoftconnect", "goggalaxy", "applemusic", "tidal", "deezer",
            "itunes", "musicbee", "foobar2000", "winamp", "signal", "skype", "thunderbird", "outlook", "code"}
MUSIC = {"spotify", "applemusic", "tidal", "deezer", "itunes", "musicbee", "foobar2000", "winamp", "vlc"}
ALIASES = {
    "discord": ["discord", "disco kord", "disco ord", "dis kord"],
    "whatsapp": ["whatsapp", "whats app"], "whatsapp.root": ["whatsapp", "whats app"],
    "minecraft": ["minecraft", "mine craft"], "javaw": ["minecraft"],
    "fortniteclient-win64-shipping": ["fortnite", "fort night", "fort nait"],
    "valorant-win64-shipping": ["valorant", "valo rant"], "valorant": ["valorant", "valo rant"],
    "epicgameslauncher": ["epic", "epic games"], "msedge": ["edge"], "obs64": ["obs"],
    "cs2": ["counter strike", "counter"], "leagueclient": ["league"], "league of legends": ["league"],
    "rocketleague": ["rocket league"], "gta5": ["gta"], "r5apex": ["apex"],
}
_CMD = {
    "de": {
        "clip": [[], ["das"], ["it"], ["alles"], ["mal"]],
        "clip_heads": ["clip", "clips", "klipp"],
        "rec_start": [["aufnahme", "starten"], ["aufnahme", "start"], ["aufnahme", "an"], ["nimm", "auf"],
                      ["starte", "aufnahme"], ["aufnehmen"]],
        "rec_app": [["aufnahme", "{app}"], ["aufnahme", "{app}", "starten"], ["nimm", "{app}", "auf"]],
        "rec_stop": [["aufnahme", "stoppen"], ["aufnahme", "stopp"], ["aufnahme", "stop"], ["aufnahme", "beenden"],
                     ["aufnahme", "ende"], ["aufnahme", "aus"], ["stopp", "aufnahme"], ["stop", "aufnahme"]],
        "stop": [["stopp"], ["stop"], ["ruhe"], ["leise"]],
        "mic": ["mikro", "mikrofon"], "game": ["spiel", "game"], "music": ["musik"],
    },
    "en": {
        "clip": [[], ["it"], ["that"], ["everything"]],
        "clip_heads": ["clip", "clips"],
        "rec_start": [["start", "recording"], ["record"], ["record", "everything"], ["start", "record"]],
        "rec_app": [["record", "{app}"], ["start", "recording", "{app}"]],
        "rec_stop": [["stop", "recording"], ["end", "recording"], ["recording", "off"], ["stop", "record"]],
        "stop": [["stop"], ["be", "quiet"], ["shut", "up"]],
        "mic": ["mic", "microphone"], "game": ["game"], "music": ["music"],
    },
}


def app_words(apps: dict[str, str], lang: str) -> dict[tuple, tuple[list[str], str]]:
    """Gesprochene App-Namen -> (Quellen-Schluessel, Anzeigename). Nur Woerter, die das Modell kennt."""
    v = vocab(lang)
    c = _CMD[lang]
    out: dict[tuple, tuple[list[str], str]] = {}

    def add(phrase: str, keys: list[str], label: str):
        ws = tuple(norm_words(phrase))
        if ws and (not v or all(w in v for w in ws)) and ws not in out:
            out[ws] = (keys, label)

    games, music = [], []
    for key, label in apps.items():
        if key == "mic":
            for w in c["mic"]:
                add(w, ["mic"], label)
            continue
        stem = key.replace("app:", "").lower()
        if stem.endswith(".exe"):
            stem = stem[:-4]
        for ph in ALIASES.get(stem, []) + [stem, label]:
            add(ph, [key], label)
        if stem in MUSIC:
            music.append(key)
        elif stem not in NON_GAME:
            games.append(key)
    if games:
        for w in c["game"]:
            add(w, games, ", ".join(apps[k] for k in games))
    if music:
        for w in c["music"]:
            add(w, music, ", ".join(apps[k] for k in music))
    return out


def build_commands(lang: str, apps: dict[str, str]) -> dict[tuple, tuple[str, list[str] | None, str]]:
    """Alle erlaubten Befehle: Wortfolge nach dem Weckwort -> (Aktion, Quellen, Anzeigename)."""
    v = vocab(lang)
    c = _CMD[lang]
    table: dict[tuple, tuple[str, list[str] | None, str]] = {}

    def add(words, action, keys=None, label=""):
        t = tuple(words)
        if t and t not in table and (not v or all(w in v for w in t)):
            table[t] = (action, keys, label)

    aw = app_words(apps, lang)
    for h in c["clip_heads"]:
        for tail in c["clip"]:
            add([h] + tail, "clip")
        for ws, (keys, label) in aw.items():
            add([h, *ws], "clip", keys, label)
    for f in c["rec_start"]:
        add(f, "rec_start")
    for f in c["rec_app"]:
        for ws, (keys, label) in aw.items():
            out = []
            for w in f:
                out.extend(ws if w == "{app}" else [w])
            add(out, "rec_start", keys, label)
    for f in c["rec_stop"]:
        add(f, "rec_stop")
    for f in c["stop"]:
        add(f, "stop")
    return table


def wake_words(lang: str) -> list[str]:
    v = vocab(lang)
    return [w for w in WAKE[lang] if not v or w in v]


FILLERS = {"it", "das", "mal", "that", "the", "hey", "bitte", "please", "ey", "jetzt", "now", "ja", "yo"}


def parse_command(words: list[str], confs: list[float], table: dict, wakes: list[str],
                  wake_conf: float = 0.6, cmd_conf: float = 0.5):
    """Sucht 'Weckwort + Befehl' in einem erkannten Satz. Gibt (Aktion, Quellen, Anzeigename, Text) oder None.

    Im Grammatik-Modus liefert Vosk nur Woerter aus der Befehlsliste, aber nicht immer in genau der Reihenfolge
    (z. B. "potato it klipp it"). Darum: Fuellwoerter direkt nach dem Weckwort ueberspringen und den laengsten
    passenden Befehl nehmen. Weckwort und Befehl muessen sicher genug erkannt sein."""
    if not confs:
        confs = [1.0] * len(words)
    longest = max((len(t) for t in table), default=0)
    for i, w in enumerate(words):
        if w not in wakes or confs[i] < wake_conf:
            continue
        j = i + 1
        while j < len(words) and j <= i + 3 and words[j] in FILLERS:
            j += 1
        for n in range(min(longest, len(words) - j), 0, -1):
            tail = tuple(words[j:j + n])
            hit = table.get(tail)
            if not hit:
                continue
            cs = confs[j:j + n]
            if min(cs) < 0.35 or sum(cs) / len(cs) < cmd_conf:
                continue
            return hit[0], hit[1], hit[2], " ".join((w,) + tail)
    return None


class VoiceTriggers:
    """Hoert das Mikro mit (aus dem Clip-Puffer) und meldet erkannte Trigger-Woerter."""

    def __init__(self, cfg, sounds, fire, command=None, apps=None):
        self.cfg = cfg
        self.sounds = sounds
        self.fire = fire                         # fire(sound_id), aus Hintergrund-Thread
        self.command = command                   # command(aktion, quellen, anzeigename), aus Hintergrund-Thread
        self.apps = apps or (lambda: {})         # aktuell verfuegbare Quellen: Schluessel -> Name
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

    def enabled(self) -> bool:
        return bool(self.cfg.get("triggers_enabled") or self.cfg.get("voice_commands"))

    def sync(self):
        """An- oder abschalten, je nach Einstellung (Sprache wechseln = neu starten)."""
        want = self.enabled() and model_ready(self.lang_wanted())
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
            vocab(self.lang)
        except Exception as e:
            log.exception("Spracherkennung")
            self.error = str(e)
            self.running = False
            return
        log.info("Sprach-Trigger aktiv (%s)", self.lang)
        fired: dict[tuple[str, ...], int] = {}
        triggers = self._triggers()
        last_tr = time.time()
        crec = None                  # zweiter Erkenner, der nur die Sprachbefehle kennt
        ctable: dict = {}
        cwakes: list[str] = []
        capps: dict = {}
        crec_dirty = True
        last_tr = 0.0                # gleich beim Start die App-Liste holen
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
                if self.cfg.get("voice_commands"):
                    try:
                        apps = dict(self.apps())
                    except Exception:
                        apps = capps
                    if apps != capps:
                        capps = apps
                        crec_dirty = True
                elif crec is not None:
                    crec = None
            if self.cfg.get("voice_commands") and (crec is None or crec_dirty):
                try:
                    ctable = build_commands(self.lang, capps)
                    cwakes = wake_words(self.lang)
                    phrases = sorted({" ".join([w, *t]) for w in cwakes for t in ctable})
                    crec = vosk.KaldiRecognizer(model, 16000, json.dumps(phrases + ["[unk]"], ensure_ascii=False))
                    crec.SetWords(True)
                    crec_dirty = False
                except Exception:
                    log.exception("Sprachbefehle")
                    crec = None
            if crec is not None:
                try:
                    if crec.AcceptWaveform(pcm):
                        res = json.loads(crec.Result())
                        ws = [x.get("word", "") for x in res.get("result", [])]
                        cf = [float(x.get("conf", 1.0)) for x in res.get("result", [])]
                        hit = parse_command(ws, cf, ctable, cwakes)
                        if hit and self.command:
                            self.heard = "▶ " + hit[3]
                            self.heard_at = time.time()
                            self.command(hit[0], hit[1], hit[2])
                except Exception:
                    log.exception("Sprachbefehle")
            if not self.cfg.get("triggers_enabled"):
                continue
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
