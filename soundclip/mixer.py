"""Wiedergabe: Sounds an dich (Kopfhoerer) und an deine Freunde (virtuelles Mikro, z. B. VB-Cable)."""
from __future__ import annotations

import logging
import struct
import subprocess
import threading
import time
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from .config import FROZEN, HELPER, SR, Config, APP_DIR
from .effects import VoiceChanger
from .host import HelperHost, StreamHandler

CREATE_NO_WINDOW = 0x08000000

log = logging.getLogger("soundclip.mixer")

TARGETS = ("monitor", "virtual")


def to_stereo48k(data: np.ndarray, sr: int) -> np.ndarray:
    data = np.asarray(data, dtype=np.float32)
    if data.ndim == 1:
        data = data[:, None]
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    if sr != SR and len(data):
        fr = Fraction(SR, int(sr)).limit_denominator(1000)
        data = resample_poly(data, fr.numerator, fr.denominator, axis=0).astype(np.float32)
    return np.ascontiguousarray(data, dtype=np.float32)


_cache: dict[tuple, np.ndarray] = {}
_cache_lock = threading.Lock()


def load_audio(path: str | Path) -> np.ndarray:
    """Laedt WAV/MP3/OGG/FLAC als float32 Stereo 48 kHz (mit Cache)."""
    p = Path(path)
    key = (str(p), p.stat().st_mtime_ns)
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    data, sr = sf.read(str(p), dtype="float32", always_2d=True)
    out = to_stereo48k(data, sr)
    with _cache_lock:
        if len(_cache) > 200:
            _cache.clear()
        _cache[key] = out
    return out


class Voice:
    __slots__ = ("data", "gain", "pos", "done", "sound_id", "name", "started")

    def __init__(self, data, gain, targets, sound_id, name):
        self.data = data
        self.gain = float(gain)
        self.pos = {t: 0 for t in targets}
        self.done: set[str] = set()
        self.sound_id = sound_id
        self.name = name
        self.started = time.time()

    @property
    def finished(self):
        return self.done >= set(self.pos)

    def progress(self) -> float:
        if not self.pos or not len(self.data):
            return 1.0
        return max(self.pos.values()) / len(self.data)


class LiveFifo:
    """Puffer fuer Live-Audio (Mikro/Apps -> virtuelles Mikro). Haelt die Latenz klein (~30-60 ms)
    und blendet bei Luecken weich aus/ein, damit es nicht knackt."""
    FADE = 96  # 2 ms

    def __init__(self, max_frames=int(0.20 * SR), target=int(0.07 * SR), prime=int(0.045 * SR)):
        self.buf = np.zeros((max_frames * 4, 2), np.float32)
        self.n = 0
        self.max = max_frames
        self.target = target
        self.prime = prime
        self.priming = True
        self.fade_in = True
        self.lock = threading.Lock()
        self.underruns = 0
        self.drops = 0

    def push(self, data: np.ndarray):
        with self.lock:
            k = len(data)
            if k >= self.max:
                data = data[-self.max:]
                k = len(data)
            if self.n + k > self.max:  # zu viel Latenz angesammelt -> auf Ziel-Latenz zuruecksetzen
                keep = max(0, self.target - k)
                drop = self.n - keep
                if drop > 0:
                    self.buf[:keep] = self.buf[drop:self.n]
                    self.n = keep
                    self.drops += 1
                    self.fade_in = True
            self.buf[self.n:self.n + k] = data
            self.n += k

    def pull(self, frames: int) -> np.ndarray | None:
        with self.lock:
            if self.priming:
                if self.n < self.prime:
                    return None
                self.priming = False
            k = min(frames, self.n)
            out = np.zeros((frames, 2), np.float32)
            out[:k] = self.buf[:k]
            self.buf[: self.n - k] = self.buf[k:self.n]
            self.n -= k
            f = self.FADE
            if self.fade_in and k:
                m = min(f, k)
                out[:m] *= np.linspace(0.0, 1.0, m, dtype=np.float32)[:, None]
                self.fade_in = False
            if k < frames:          # Luecke: weich ausblenden statt hart abreissen
                m = min(f, k)
                if m:
                    out[k - m:k] *= np.linspace(1.0, 0.0, m, dtype=np.float32)[:, None]
                self.priming = True
                self.fade_in = True
                self.underruns += 1
            return out

    def clear(self):
        with self.lock:
            self.n = 0
            self.priming = True
            self.fade_in = True


def fx_worker_cmd() -> str:
    """Befehlszeile fuer den Effekt-Prozess (siehe fxworker.py)."""
    import sys
    if FROZEN:
        return f'"{sys.executable}" --fxworker'
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return f'"{w if w.exists() else exe}" "{APP_DIR / "app.py"}" --fxworker'


def _render_devices() -> list[dict]:
    from .capture import run_helper_list
    try:
        return run_helper_list().get("render", [])
    except Exception:
        log.exception("Geraeteliste")
        return []


def list_output_devices() -> list[str]:
    """Namen aller Ausgabegeraete (direkt von Windows, inkl. Bluetooth)."""
    return [d["name"] for d in _render_devices()]


def _driver(name: str) -> str:
    """Text in der letzten Klammer, z. B. 'VB-Audio Virtual Cable' (bleibt auch nach Umbenennen gleich)."""
    if "(" in name and name.endswith(")"):
        return name[name.rfind("(") + 1:-1].strip().lower()
    return ""


def find_cable_device(devices: list[dict] | None = None) -> str:
    devs = devices if devices is not None else _render_devices()
    names = [d["name"] for d in devs]
    for n in names:   # VB-Cable (auch umbenannt, z. B. "Potato Clips Ausgang (VB-Audio Virtual Cable)")
        low = n.lower()
        if _driver(n) == "vb-audio virtual cable" and "16ch" not in low and "in 16" not in low:
            return n
    for n in names:
        if "cable input" in n.lower() and "16ch" not in n.lower():
            return n
    for n in names:
        low = n.lower()
        if "cable" in low or "voicemeeter input" in low or "potato clips" in low:
            return n
    return ""


HR_TEXT = {
    "0x8889000A": "Gerät wird gerade von einer anderen App exklusiv benutzt",
    "0x88890004": "Gerät wurde entfernt oder deaktiviert",
    "0x88890008": "Format wird vom Gerät nicht unterstützt",
    "0x80070490": "Gerät nicht gefunden",
}


def friendly_error(msg: str) -> str:
    for code, text in HR_TEXT.items():
        if code.lower() in msg.lower():
            return text
    return msg


def find_cable_capture(capture_devices: list[dict], render_name: str) -> dict | None:
    """Zum Wiedergabe-Ende eines virtuellen Kabels das passende Aufnahme-Ende finden
    (CABLE Input -> CABLE Output, auch wenn die Geraete umbenannt wurden)."""
    low = (render_name or "").lower()
    drv = _driver(render_name or "")
    if drv:
        cands = [d for d in capture_devices if _driver(d["name"]) == drv and "16ch" not in d["name"].lower()
                 and "out 16" not in d["name"].lower()]
        if len(cands) == 1:
            return cands[0]
        if cands:
            pref = [d for d in cands if "output" in d["name"].lower() or "out" in d["name"].lower()]
            return (pref or cands)[0]
    if "cable" in low:
        cands = [d for d in capture_devices if "cable output" in d["name"].lower()]
        if cands:
            return cands[0]
    if "voicemeeter" in low:
        cands = [d for d in capture_devices if "voicemeeter" in d["name"].lower() and "out" in d["name"].lower()]
        if cands:
            return cands[0]
    return None


class OutputHelper(StreamHandler):
    """Ein Wiedergabe-Stream im gemeinsamen Helfer. Pull-Modell: der Helfer fragt Frames an."""

    def __init__(self, mixer: "Mixer", target: str, device_id: str, name: str):
        self.mixer, self.target, self.device_id, self.name = mixer, target, device_id, name
        self.error = ""
        self.ok = False
        self.ended = False
        self.started_at = time.time()
        self.sid = HelperHost.get().start("play", device_id, self)

    def alive(self) -> bool:
        return not self.ended and self.sid is not None

    def on_log(self, line: str):
        line = line.strip()
        if line.startswith("audiocap: ok"):
            self.ok = True
        elif line:
            self.error = friendly_error(line.replace("audiocap: ", ""))
            log.warning("play %s: %s", self.target, line)

    def on_request(self, frames: int) -> bytes:
        return self.mixer._render(self.target, frames).tobytes()

    def on_end(self, code: int):
        self.ended = True

    def close(self):
        HelperHost.get().stop(self.sid)
        self.sid = None
        self.ended = True


class VoiceIn(StreamHandler):
    """Stimme im Helfer: Mikro -> Rumpelfilter -> RNNoise -> Gate -> Discord/Kopfhoerer, komplett nativ.
    Ein Stimmeffekt wird in einem eigenen kleinen Prozess (fxworker) berechnet, mit dem der Helfer
    direkt spricht - die Haupt-App ist nie im Echtzeit-Pfad. Hier kommen nur Pegel an."""

    def __init__(self, mixer: "Mixer", source: str):
        self.mixer = mixer
        self.source = source
        self.ended = False
        self.ok = False
        self.error = ""
        self.started_at = time.time()
        self.sid = HelperHost.get().start("voicein", source, self)

    def on_log(self, line: str):
        if line.startswith("audiocap: ok"):
            self.ok = True
        elif line.strip():
            self.error = friendly_error(line.replace("audiocap: ", ""))
            log.warning("voicein: %s", line)

    def on_levels(self, a: float, b: float):
        self.mixer.voice_in = max(self.mixer.voice_in, a)
        self.mixer.voice_out = max(self.mixer.voice_out, b)

    def on_end(self, code: int):
        self.ended = True

    def close(self):
        HelperHost.get().stop(self.sid)
        self.sid = None
        self.ended = True


class Mixer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.voices: list[Voice] = []
        self.lock = threading.Lock()
        self.live = LiveFifo()
        self.live_mon = LiveFifo()
        self.routes: dict[str, LiveFifo] = {}       # App-Quellen -> Discord
        self.route_levels: dict[str, float] = {}
        self.cleaner = None
        self.voicein: VoiceIn | None = None
        self.voice_source_override = ""     # nur fuer Tests (z. B. "pid:1234")
        self._voice_lock = threading.RLock()
        self.voice = VoiceChanger()
        self.voice_in = 0.0
        self.voice_out = 0.0
        self.streams: dict[str, OutputHelper | None] = {t: None for t in TARGETS}
        self.devices: dict[str, str] = {t: "" for t in TARGETS}
        self.errors: dict[str, str] = {t: "" for t in TARGETS}
        self._want: dict[str, tuple[str, str] | None] = {t: None for t in TARGETS}  # (id, name)
        self._fails: dict[str, int] = {t: 0 for t in TARGETS}
        self._default_id = ""
        self._reopen_lock = threading.Lock()
        self.apply_clean()
        self.apply_voice()

    # ---------------------------------------------------------- Geraete
    def virtual_device_name(self, devices: list[dict] | None = None) -> str:
        v = self.cfg["virtual_device"]
        if v == "auto":
            return find_cable_device(devices)
        return v or ""

    def reopen(self, devices: list[dict] | None = None):
        with self._reopen_lock:
            devs = devices if devices is not None else _render_devices()
            self.close()
            default = next((d for d in devs if d.get("default")), None)
            self._default_id = default["id"] if default else ""
            # Kopfhoerer / Lautsprecher
            mname = self.cfg["monitor_device"]
            if mname:
                d = next((d for d in devs if d["name"] == mname), None)
                if d is None:
                    self.errors["monitor"] = f"„{mname}“ nicht gefunden – nutze Windows-Standard"
                    log.warning(self.errors["monitor"])
                    d = default
                want = (d["id"], d["name"]) if d else ("default", "Windows-Standard")
            else:
                want = ("default", (default["name"] + " (Standard)") if default else "Windows-Standard")
            self._want["monitor"] = want
            # virtuelles Mikro
            vname = self.virtual_device_name(devs)
            vd = next((d for d in devs if d["name"] == vname), None) if vname else None
            self._want["virtual"] = (vd["id"], vd["name"]) if vd else None
            if vname and not vd:
                self.errors["virtual"] = f"„{vname}“ nicht gefunden"
            elif not vname:
                self.errors["virtual"] = "kein virtuelles Mikro gewählt"
            for t in TARGETS:
                self._fails[t] = 0
                if self._want[t]:
                    self._open(t)
        self.apply_voice_path()

    def _open(self, target: str):
        self._close(target)
        want = self._want[target]
        if not want:
            return False
        dev_id, name = want
        if not HELPER.exists():
            self.errors[target] = "bin\\audiocap.exe fehlt"
            return False
        try:
            self.streams[target] = OutputHelper(self, target, dev_id, name)
            self.devices[target] = name
            self.errors[target] = ""
            log.info("Ausgabe %s -> %s", target, name)
            return True
        except Exception as e:
            self.errors[target] = str(e)
            log.warning("Ausgabe %s fehlgeschlagen: %s", target, e)
            return False

    def _close(self, target):
        s = self.streams.get(target)
        self.streams[target] = None
        if s is not None:
            s.close()

    def close(self):
        if getattr(self, "voicein", None) is not None:
            self.voicein.close()
            self.voicein = None
        for t in TARGETS:
            self._close(t)

    def watchdog(self, devices: list[dict]):
        """Vom Hintergrund-Thread aufgerufen: abgestuerzte Ausgaben neu starten,
        Windows-Standardgeraet gewechselt (z. B. Bluetooth-Kopfhoerer verbunden) -> umschalten."""
        default = next((d for d in devices if d.get("default")), None)
        if default and default["id"] != self._default_id and not self.cfg["monitor_device"]:
            log.info("Windows-Standardausgabe gewechselt -> %s", default["name"])
            self.reopen(devices)
            return
        vi = self.voicein
        if self.native_voice() and (vi is None or vi.ended) and time.time() - (vi.started_at if vi else 0) > 3:
            self.apply_voice_path()
        for t in TARGETS:
            s = self.streams.get(t)
            if self._want[t] and s is not None and not s.alive():
                self.errors[t] = s.error or "Ausgabe beendet"
                wait = min(30.0, 2.0 * (2 ** min(self._fails[t], 4)))
                if time.time() - s.started_at > wait:
                    self._fails[t] += 1
                    if self._fails[t] > 1:  # Geraeteliste koennte sich geaendert haben
                        self.reopen(devices)
                        return
                    self._open(t)
                    self.apply_voice_path()
            elif s is not None and s.ok and self._fails[t]:
                self._fails[t] = 0

    def device_id(self, target: str) -> str:
        w = self._want.get(target)
        return w[0] if w else ""

    def is_open(self, target: str) -> bool:
        s = self.streams.get(target)
        return s is not None and s.alive()

    # ---------------------------------------------------------- Mischen
    def _render(self, target: str, frames: int) -> np.ndarray:
        out = np.zeros((frames, 2), np.float32)
        with self.lock:
            voices = list(self.voices)
        for v in voices:
            p = v.pos.get(target)
            if p is None or target in v.done:
                continue
            chunk = v.data[p:p + frames]
            n = len(chunk)
            if n:
                out[:n] += chunk * v.gain
            v.pos[target] = p + n
            if p + n >= len(v.data):
                v.done.add(target)
        out *= float(self.cfg["master_volume"])
        if target == "virtual" and self.cfg["mic_passthrough"]:
            live = self.live.pull(frames)
            if live is not None:
                out += live * float(self.cfg["mic_passthrough_gain"])
        if target == "virtual" and self.routes:
            for f in list(self.routes.values()):
                r = f.pull(frames)
                if r is not None:
                    out += r
        if target == "monitor" and self.cfg["voice_monitor"] and not self.native_voice():
            live = self.live_mon.pull(frames)
            if live is not None:
                out += live * float(self.cfg["voice_monitor_gain"])
        np.clip(out, -1.0, 1.0, out=out)
        return out

    def apply_voice(self):
        """Stimm-Preset aus der Konfiguration uebernehmen."""
        if self.cfg["voice_enabled"]:
            pre = self.cfg["voice_preset"]
            amt = float((self.cfg["voice_amounts"] or {}).get(pre, self.cfg["voice_amount"]))
            self.voice.set(pre, amt)
        else:
            pre, amt = "", 0.0
            self.voice.set("", 0)
        HelperHost.get().command(f"fxset set {self.voice.key or '-'} {amt:.3f}")
        self.apply_voice_path()

    def apply_clean(self):
        """Mikro-Reinigung (KI-Rauschfilter + Gate) nach Einstellungen neu aufbauen."""
        if self.cfg["clean_mic"]:
            from .cleanmic import MicCleaner, available
            if available():
                self.cleaner = MicCleaner(float(self.cfg["clean_strength"]), bool(self.cfg["clean_gate"]))
            else:
                self.cleaner = None
        else:
            self.cleaner = None
        self.apply_voice_path()

    def feed_route(self, key: str, data: np.ndarray):
        """App-Audio (z. B. Spotify) zusaetzlich an Discord schicken."""
        routes = self.cfg["route_sources"] or {}
        if key not in routes or not self.is_open("virtual"):
            return
        f = self.routes.get(key)
        if f is None:
            f = self.routes[key] = LiveFifo()
        gain = float(routes.get(key, 0.6))
        y = data * gain
        self.route_levels[key] = max(self.route_levels.get(key, 0.0), float(np.abs(y).max()) if len(y) else 0.0)
        f.push(y)

    def prune_routes(self):
        keep = set((self.cfg["route_sources"] or {}).keys())
        for k in list(self.routes):
            if k not in keep:
                self.routes.pop(k, None)

    def native_voice(self) -> bool:
        """Stimme laeuft ueber den Helfer (Takt, Puffer, Rauschfilter nativ - stabil wie Voicemod)."""
        return bool(self.cfg["mic_passthrough"] or self.cfg["voice_monitor"])

    def voice_fx(self) -> bool:
        return bool(self.cfg["voice_enabled"] and self.voice.active())

    _fx_pid = None      # Helfer-Prozess, in dem der Effekt-Prozess schon gestartet wurde

    def wants_mic(self) -> bool:
        """Alter Python-Pfad fuer die Stimme (nur noch fuer Tests)."""
        return bool((self.cfg["mic_passthrough"] or self.cfg["voice_monitor"]) and not self.native_voice())

    def apply_voice_path(self):
        """Native Stimme ein-/ausschalten und konfigurieren."""
        with self._voice_lock:
            host = HelperHost.get()
            native = self.native_voice()
            mix = bool(self.cfg["mic_passthrough"]) and native and self.is_open("virtual")
            mon = bool(self.cfg["voice_monitor"]) and native and self.is_open("monitor")
            gain = float(self.cfg["mic_passthrough_gain"])
            fx = self.voice_fx()
            if native and host.pid is not None and (fx or self._fx_pid != host.pid):
                # Effekt-Prozess vorab starten, damit das Umschalten per Hotkey sofort klingt
                host.command(f"fxset set {self.voice.key or '-'} {self.voice.amount if fx else 0:.3f}")
                host.command("fxstart " + fx_worker_cmd())
                self._fx_pid = host.pid
            host.command(f"voiceconf {int(mix)} {int(bool(self.cfg['clean_mic']))} "
                         f"{int(bool(self.cfg['clean_gate']))} {float(self.cfg['clean_strength']):.3f} {gain:.3f} "
                         f"{2 if fx else 0} {int(mon)} {float(self.cfg['voice_monitor_gain']):.3f}")
            src = self.voice_source_override or (self.cfg["mic_device"] or "default")
            if native:
                vi = self.voicein
                if vi is None or vi.ended or vi.source != src:
                    if vi is not None:
                        vi.close()
                    self.voicein = VoiceIn(self, src)
                st = self.streams.get("virtual")
                if st is not None and st.sid:
                    host.command("voicetarget", st.sid)
                sm = self.streams.get("monitor")
                if sm is not None and sm.sid:
                    host.command("montarget", sm.sid)
            elif self.voicein is not None:
                self.voicein.close()
                self.voicein = None

    def feed_live(self, data: np.ndarray):
        """Mikrofon-Block (live): Stimmeffekt anwenden und an Discord / Mithoeren weitergeben."""
        to_virtual = self.cfg["mic_passthrough"] and self.is_open("virtual") and not self.native_voice()
        to_monitor = self.cfg["voice_monitor"] and self.is_open("monitor") and not self.native_voice()
        if not (to_virtual or to_monitor):
            return
        pk_in = float(np.abs(data).max()) if len(data) else 0.0
        cleaner = self.cleaner
        if cleaner is not None:
            try:
                mono = cleaner.process(data.mean(axis=1).astype(np.float32))
                data = np.repeat(mono[:, None], 2, axis=1)
            except Exception:
                log.exception("Mikro-Reinigung")
                self.cleaner = None
        try:
            y = self.voice.process(data)
        except Exception:
            log.exception("Stimmeffekt")
            self.voice.set("", 0)
            y = data
        pk_out = float(np.abs(y).max()) if len(y) else 0.0
        self.voice_in = max(self.voice_in, pk_in)
        self.voice_out = max(self.voice_out, pk_out)
        if to_virtual:
            self.live.push(y)
        if to_monitor:
            self.live_mon.push(y)

    def take_voice_levels(self):
        a, b = self.voice_in, self.voice_out
        self.voice_in = self.voice_out = 0.0
        return a, b

    # ---------------------------------------------------------- Abspielen
    def active_targets(self, preview=False) -> list[str]:
        ts = []
        if self.is_open("monitor") and (preview or self.cfg["play_to_monitor"]):
            ts.append("monitor")
        if not preview and self.is_open("virtual") and self.cfg["play_to_virtual"]:
            ts.append("virtual")
        return ts

    def play(self, data: np.ndarray, gain=1.0, sound_id=None, name="", preview=False, targets=None):
        ts = targets or self.active_targets(preview)
        if not ts or data is None or not len(data):
            return None
        mode = self.cfg["retrigger"]
        with self.lock:
            self.voices = [v for v in self.voices if not v.finished]
            if sound_id is not None:
                same = [v for v in self.voices if v.sound_id == sound_id]
                if same and mode == "stop":
                    self.voices = [v for v in self.voices if v.sound_id != sound_id]
                    return None
                if same and mode == "restart":
                    self.voices = [v for v in self.voices if v.sound_id != sound_id]
            v = Voice(data, gain, ts, sound_id, name)
            self.voices.append(v)
        return v

    def stop(self, sound_id):
        with self.lock:
            self.voices = [v for v in self.voices if v.sound_id != sound_id]

    def stop_all(self):
        with self.lock:
            self.voices = []

    def playing(self) -> list[Voice]:
        dead = [t for t in TARGETS if not self.is_open(t)]
        with self.lock:
            for v in self.voices:
                for t in dead:
                    if t in v.pos:
                        v.done.add(t)
            self.voices = [v for v in self.voices if not v.finished]
            return list(self.voices)

    def is_playing(self, sound_id) -> bool:
        return any(v.sound_id == sound_id for v in self.playing())
