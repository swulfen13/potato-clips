"""Audio-Quellen: Mikro, System und jede App einzeln (ueber bin/audiocap.exe).

Jede Quelle schreibt in einen Ringpuffer, der an einer gemeinsamen Uhr ausgerichtet ist.
Dadurch liegen alle Spuren eines Clips zeitlich exakt uebereinander.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path

import numpy as np
import psutil
import soundfile as sf

from .config import CLIPS_DIR, HELPER, SR, Config
from .host import HelperHost, StreamHandler

log = logging.getLogger("soundclip.capture")

CREATE_NO_WINDOW = 0x08000000
SLACK = SR // 10          # 100 ms Toleranz
SILENCE = 0.001           # darunter gilt eine Spur als stumm
BYTES_PER_FRAME = 8       # float32 * 2 Kanaele

PRETTY_NAMES = {
    "discord.exe": "Discord", "discordptb.exe": "Discord PTB", "discordcanary.exe": "Discord Canary",
    "spotify.exe": "Spotify", "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox",
    "brave.exe": "Brave", "opera.exe": "Opera", "steam.exe": "Steam", "steamwebhelper.exe": "Steam",
    "teamspeak.exe": "TeamSpeak", "ts3client_win64.exe": "TeamSpeak 3", "vlc.exe": "VLC",
    "obs64.exe": "OBS", "javaw.exe": "Minecraft (Java)", "valorant-win64-shipping.exe": "Valorant",
    "cs2.exe": "Counter-Strike 2", "fortniteclient-win64-shipping.exe": "Fortnite",
    "robloxplayerbeta.exe": "Roblox", "leagueclient.exe": "League Client",
    "league of legends.exe": "League of Legends", "r5apex.exe": "Apex Legends",
    "rocketleague.exe": "Rocket League", "gta5.exe": "GTA V", "whatsapp.exe": "WhatsApp",
    "whatsapp.root.exe": "WhatsApp", "epicgameslauncher.exe": "Epic Games", "audacity.exe": "Audacity",
    "audacity4.exe": "Audacity", "claude.exe": "Claude", "telegram.exe": "Telegram", "zoom.exe": "Zoom",
    "ms-teams.exe": "Teams", "medal.exe": "Medal", "battle.net.exe": "Battle.net", "riotclientservices.exe": "Riot Client",
}


def pretty_app_name(exe: str) -> str:
    low = exe.lower()
    if low in PRETTY_NAMES:
        return PRETTY_NAMES[low]
    base = re.sub(r"\.exe$", "", exe, flags=re.I)
    return base[:1].upper() + base[1:]


def safe_name(s: str) -> str:
    s = re.sub(r"[^\w\-. ]+", "_", s, flags=re.UNICODE).strip(" ._")
    return s[:60] or "audio"


def run_helper_list() -> dict:
    r = subprocess.run([str(HELPER), "list"], capture_output=True, timeout=8, creationflags=CREATE_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="replace"))
    return json.loads(r.stdout.decode("utf-8"))


SYSTEM_EXES = {
    "explorer.exe", "textinputhost.exe", "applicationframehost.exe", "systemsettings.exe",
    "shellexperiencehost.exe", "searchhost.exe", "startmenuexperiencehost.exe", "lockapp.exe",
    "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "openconsole.exe", "conhost.exe",
    "taskmgr.exe", "nvidia overlay.exe", "nvcontainer.exe", "rundll32.exe", "dllhost.exe",
    "msedgewebview2.exe", "widgets.exe", "phoneexperiencehost.exe", "gamebar.exe", "notepad.exe",
    "python.exe", "pythonw.exe", "code.exe", "devenv.exe", "mmc.exe", "regedit.exe", "control.exe",
    "securityhealthsystray.exe", "ctfmon.exe", "sihost.exe", "smartscreen.exe",
}


def windowed_pids() -> set[int]:
    """Prozesse mit sichtbarem Hauptfenster (nur Windows)."""
    pids: set[int] = set()
    try:
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32
        dwm = ctypes.windll.dwmapi
    except Exception:
        return pids

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lp):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) == 0:
                return True
            if user32.GetWindow(hwnd, 4):  # GW_OWNER: Dialoge/Tool-Fenster ueberspringen
                return True
            cloaked = wt.DWORD(0)
            dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
            # 1 = von der App selbst versteckt, 4 = geerbt -> ueberspringen.
            # 2 = von der Shell versteckt (anderer virtueller Desktop / im Hintergrund) -> trotzdem zaehlen
            if cloaked.value & (1 | 4):
                return True
            pid = wt.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                pids.add(pid.value)
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(cb, 0)
    except Exception:
        pass
    return pids


_desc_cache: dict[str, str] = {}


def exe_description(path: str) -> str:
    """'FileDescription' aus der EXE (z. B. 'Spotify', 'Brave Browser')."""
    if path in _desc_cache:
        return _desc_cache[path]
    desc = ""
    try:
        import ctypes
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(path, None)
        if size:
            buf = ctypes.create_string_buffer(size)
            if ver.GetFileVersionInfoW(path, 0, size, buf):
                ptr = ctypes.c_void_p()
                ln = ctypes.c_uint()
                if ver.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(ln)) \
                        and ln.value >= 4:
                    lang, cp = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ushort * 2)).contents
                    key = f"\\StringFileInfo\\{lang:04x}{cp:04x}\\FileDescription"
                    if ver.VerQueryValueW(buf, key, ctypes.byref(ptr), ctypes.byref(ln)) and ln.value:
                        desc = ctypes.wstring_at(ptr, ln.value).strip("\x00 ").strip()
    except Exception:
        desc = ""
    _desc_cache[path] = desc
    return desc


_label_cache: dict[tuple[int, str], str] = {}


def app_label(p: psutil.Process, name: str) -> str:
    low = name.lower()
    if low in PRETTY_NAMES:
        return PRETTY_NAMES[low]
    key = (p.pid, low)
    if key in _label_cache:
        return _label_cache[key]
    label = pretty_app_name(name)
    try:
        d = exe_description(p.exe())
        if d and len(d) <= 40 and d.lower() not in ("", "application", "launcher"):
            label = d
    except Exception:
        pass
    if len(_label_cache) > 2000:
        _label_cache.clear()
    _label_cache[key] = label
    return label


class LevelProbe(StreamHandler):
    """Misst den Pegel eines Eingabegeraets (z. B. CABLE Output = das, was Discord hoert)."""

    def __init__(self, device_id: str):
        self.peak = 0.0
        self.alive = True
        self.sid = HelperHost.get().start("mic", device_id, self)

    def on_audio(self, payload: bytes):
        n = len(payload) // 4
        if n:
            pk = float(np.abs(np.frombuffer(payload[: n * 4], np.float32)).max())
            if pk > self.peak:
                self.peak = pk

    def on_end(self, code: int):
        self.alive = False

    def take(self) -> float:
        v, self.peak = self.peak, 0.0
        return v

    def stop(self):
        HelperHost.get().stop(self.sid)
        self.sid = None
        self.alive = False


class Clock:
    """Gemeinsame Zeitbasis in Samples."""

    def __init__(self):
        self.t0 = time.perf_counter()

    def now(self) -> int:
        return int((time.perf_counter() - self.t0) * SR)


class Recorder:
    """Schreibt eine Quelle live in eine WAV-Datei (ab absolutem Sample-Index `start`)."""

    def __init__(self, path: Path, start_idx: int, key: str, label: str):
        self.path = Path(path)
        self.key = key
        self.label = label
        self.f = sf.SoundFile(str(self.path), "w", SR, 2, subtype="PCM_16")
        self.written_to = start_idx
        self.peak = 0.0

    def write(self, data: np.ndarray, idx: int):
        end = idx + len(data)
        if end <= self.written_to:
            return
        if idx < self.written_to:
            data = data[self.written_to - idx:]
            idx = self.written_to
        if idx > self.written_to:
            self._zeros(idx - self.written_to)
        if len(data):
            self.f.write(np.clip(data, -1.0, 1.0))
            self.peak = max(self.peak, float(np.abs(data).max()))
            self.written_to = end

    def _zeros(self, n: int):
        self.written_to += n
        while n > 0:
            k = min(n, SR)
            self.f.write(np.zeros((k, 2), np.float32))
            n -= k

    def finish(self, end_idx: int):
        if end_idx > self.written_to:
            self._zeros(end_idx - self.written_to)
        self.f.close()


class CaptureSource(StreamHandler):
    def __init__(self, key: str, label: str, kind: str, arg, clock: Clock, buffer_seconds: float,
                 on_chunk=None):
        self.key, self.label, self.kind, self.arg = key, label, kind, arg
        self.clock = clock
        self.cap = int((buffer_seconds + 5) * SR)
        self.ring: np.ndarray | None = None   # wird erst bei echtem Ton angelegt (spart RAM)
        self.wp = clock.now()
        self.lock = threading.RLock()
        self.sid: int | None = None
        self._rem = b""
        self.status = "aus"
        self.error = ""
        self._level = 0.0
        self.last_sound = 0.0
        self.recorder: Recorder | None = None
        self.on_chunk = on_chunk
        self.started_at = 0.0
        self.fail_count = 0

    # ---------------------------------------------------------- Stream (ueber den gemeinsamen Helfer)
    def start(self):
        self.stop()
        self.started_at = time.time()
        self.status = "startet"
        self.error = ""
        self._rem = b""
        try:
            self.sid = HelperHost.get().start(self.kind, self.arg, self)
        except Exception as e:  # pragma: no cover
            self.sid = None
            self.status, self.error = "Fehler", str(e)

    def stop(self):
        sid, self.sid = self.sid, None
        if sid:
            HelperHost.get().stop(sid)
            self.status = "aus"

    def alive(self) -> bool:
        return self.sid is not None

    def on_log(self, line: str):
        line = line.strip()
        if line.startswith("audiocap: ok"):
            self.status = "läuft"
            self.fail_count = 0
        elif line:
            self.error = line.replace("audiocap: ", "")
            log.warning("%s: %s", self.key, line)

    def on_audio(self, payload: bytes):
        b = self._rem + payload if self._rem else payload
        n = len(b) // BYTES_PER_FRAME
        self._rem = b[n * BYTES_PER_FRAME:]
        if n:
            self._push(np.frombuffer(b[: n * BYTES_PER_FRAME], np.float32).reshape(-1, 2))

    def on_silence(self, frames: int):
        if frames > 0:
            self._push(np.zeros((min(frames, SR), 2), np.float32))

    def on_end(self, code: int):
        self.sid = None
        self.status = "Fehler" if self.error else "beendet"
        self.fail_count += 1

    # ---------------------------------------------------------- Puffer
    def _push(self, data: np.ndarray):
        n = len(data)
        now = self.clock.now()
        with self.lock:
            if self.wp < now - n - SLACK:          # Luecke (z. B. Stille ohne Pakete) -> mit Nullen fuellen
                self._write_zeros(now - n - self.wp)
            elif self.wp > now + 2 * SLACK:        # Quelle laeuft der Uhr davon -> Block verwerfen
                return
            self._write(data)
        pk = float(np.abs(data).max())
        if pk > self._level:
            self._level = pk
        if pk > 0.004:
            self.last_sound = time.time()
        cb = self.on_chunk
        if cb:
            try:
                cb(self, data)
            except Exception:
                pass

    def _write(self, data: np.ndarray):
        n = len(data)
        if n == 0:
            return
        if self.recorder:
            self.recorder.write(data, self.wp)
        if self.ring is None:
            if not data.any():
                self.wp += n
                return
            self.ring = np.zeros((self.cap, 2), np.float32)
        if n >= self.cap:
            data = data[-self.cap:]
            self.wp += n - self.cap
            n = self.cap
        s = self.wp % self.cap
        e = s + n
        if e <= self.cap:
            self.ring[s:e] = data
        else:
            k = self.cap - s
            self.ring[s:] = data[:k]
            self.ring[: n - k] = data[k:]
        self.wp += n

    def _write_zeros(self, n: int):
        if n <= 0:
            return
        if n > self.cap or self.ring is None:  # riesige Luecke / noch nie Ton: nur vorspulen
            if self.ring is not None:
                self.ring[:] = 0
            if self.recorder:
                self.recorder.write(np.zeros((0, 2), np.float32), self.wp + n)
            self.wp += n
            return
        while n > 0:
            k = min(n, SR)
            self._write(np.zeros((k, 2), np.float32))
            n -= k

    def tick(self):
        now = self.clock.now()
        with self.lock:
            if self.wp < now - 2 * SLACK:
                self._write_zeros(now - SLACK - self.wp)

    def take_level(self) -> float:
        v, self._level = self._level, 0.0
        return v

    def read(self, start: int, end: int) -> np.ndarray:
        out = np.zeros((max(0, end - start), 2), np.float32)
        with self.lock:
            lo = max(start, self.wp - self.cap)
            hi = min(end, self.wp)
            if hi > lo and self.ring is not None:
                n = hi - lo
                s = lo % self.cap
                e = s + n
                o = lo - start
                if e <= self.cap:
                    out[o:o + n] = self.ring[s:e]
                else:
                    k = self.cap - s
                    out[o:o + k] = self.ring[s:]
                    out[o + k:o + n] = self.ring[: n - k]
        return out

    # ---------------------------------------------------------- Aufnahme
    def start_recording(self, path: Path, start_idx: int):
        with self.lock:
            rec = Recorder(path, start_idx, self.key, self.label)
            if self.wp > start_idx:
                rec.write(self.read(start_idx, self.wp), start_idx)
            self.recorder = rec

    def stop_recording(self, end_idx: int) -> Recorder | None:
        with self.lock:
            rec, self.recorder = self.recorder, None
        if rec:
            rec.finish(end_idx)
        return rec


def _own_ancestors() -> set[int]:
    out = {os.getpid()}
    try:
        for par in psutil.Process(os.getpid()).parents():
            out.add(par.pid)
    except Exception:
        pass
    return out


_OWN_ANCESTORS: set[int] | None = None

# psutil fragt den Elternprozess unter Windows ueber einen kompletten Prozess-Schnappschuss ab und haelt
# dabei Pythons GIL fest - bei vielen Aufrufen alle 3 s blockierte das die ganze App fuer 100+ ms
# (Soundboard stockte). Name und Elternprozess aendern sich nie -> pro Prozess nur einmal fragen.
_PINFO: dict[int, tuple[float, str, int]] = {}


def pinfo(pid: int) -> tuple[float, str, int] | None:
    """(Startzeit, Name, Eltern-PID) eines Prozesses, gecacht."""
    try:
        ct = psutil.Process(pid).create_time()
    except Exception:
        return None
    c = _PINFO.get(pid)
    if c is not None and c[0] == ct:
        return c
    try:
        p = psutil.Process(pid)
        c = (ct, p.name(), p.ppid())
    except Exception:
        return None
    if len(_PINFO) > 4000:
        _PINFO.clear()
    _PINFO[pid] = c
    return c


def parent_chain(pid: int, limit: int = 12) -> list[int]:
    """Elternprozesse (ohne pid selbst), naechster zuerst."""
    out: list[int] = []
    cur = pinfo(pid)
    seen = {pid}
    while cur is not None and len(out) < limit:
        ppid = cur[2]
        if not ppid or ppid in seen:
            break
        par = pinfo(ppid)
        if par is None or par[0] > cur[0]:     # PID wiederverwendet -> kein echter Elternteil
            break
        out.append(ppid)
        seen.add(ppid)
        cur = par
    return out


def _process_root(p: psutil.Process) -> int:
    """Oberster Elternprozess mit gleichem Programmnamen (z. B. Discord-Hauptprozess).
    Stoppt vor dem eigenen Prozessbaum – den schliesst Windows bei der Aufnahme aus."""
    global _OWN_ANCESTORS
    if _OWN_ANCESTORS is None:
        _OWN_ANCESTORS = _own_ancestors()
    me = pinfo(p.pid)
    if me is None:
        return p.pid
    name = me[1].lower()
    root = p.pid
    for par in parent_chain(p.pid, 10):
        if par in _OWN_ANCESTORS:
            break
        info = pinfo(par)
        if info is None or info[1].lower() != name:
            break
        root = par
    return root


class SourceManager:
    def __init__(self, cfg: Config, mixer=None):
        self.cfg = cfg
        self.mixer = mixer
        self.clock = Clock()
        self.sources: dict[str, CaptureSource] = {}
        self.available: dict[str, dict] = {}
        self.devices: dict = {"capture": [], "render": []}
        self.events: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self.recording: dict | None = None
        self.forced: set[str] = set()
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self.helper_ok = HELPER.exists()
        self.sessions: list[dict] = []
        self.listeners: list = []             # weitere Abnehmer der Audio-Bloecke (Auto-Clip, Sprach-Trigger)

    # ---------------------------------------------------------- Lebenszyklus
    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True, name="source-manager")
        self._thread.start()

    def shutdown(self):
        if self.recording:
            try:
                self.stop_recording()
            except Exception:
                log.exception("stop_recording beim Beenden")
        self._stop.set()
        self._wake.set()
        with self.lock:
            for s in self.sources.values():
                s.stop()
            self.sources.clear()
        HelperHost.get().shutdown()

    def poke(self):
        """Sofort neu scannen (z. B. nach Einstellungsaenderung)."""
        self._wake.set()

    def rebuild(self):
        """Alle Quellen neu erstellen (z. B. neue Pufferlaenge oder anderes Mikro)."""
        with self.lock:
            if self.recording:
                return False
            for s in self.sources.values():
                s.stop()
            self.sources.clear()
        self.poke()
        return True

    def _loop(self):
        last = 0.0
        while not self._stop.is_set():
            woke = self._wake.wait(0.2)
            if self._stop.is_set():
                break
            try:
                if woke or time.time() - last > 3.0:
                    self._wake.clear()
                    self.refresh()
                    self.reconcile()
                    if self.mixer is not None:
                        self.mixer.watchdog(self.devices.get("render", []))
                    last = time.time()
                with self.lock:
                    srcs = list(self.sources.values())
                for s in srcs:
                    s.tick()
            except Exception as e:
                log.exception("manager loop: %s", e)

    # ---------------------------------------------------------- Scannen
    def refresh(self):
        if not HELPER.exists():
            self.helper_ok = False
            return
        data = run_helper_list()
        self.devices = {"capture": data.get("capture", []), "render": data.get("render", [])}
        self.sessions = data.get("sessions", [])
        own = os.getpid()
        ignore = {x.lower().strip() for x in self.cfg["ignore_apps"]} | {"audiocap.exe"}
        apps: dict[str, dict] = {}
        session_roots: set[int] = set()

        def add(pid: int, weight: int, active: bool, from_window: bool):
            if pid == own:
                return
            info0 = pinfo(pid)
            if info0 is None:
                return
            name = info0[1]
            try:
                p = psutil.Process(pid)
            except Exception:
                return
            low = name.lower()
            if low in ignore or (from_window and low in SYSTEM_EXES):
                return
            try:
                root = _process_root(p)
            except Exception:
                root = pid
            if root == own:
                return
            if from_window:
                # Fenster gehoert zu einem Prozessbaum, der schon erfasst wird (z. B. steamwebhelper -> steam)?
                chain = {pid, root} | set(parent_chain(pid))
                if chain & session_roots:
                    return
            else:
                session_roots.add(root)
            info = apps.setdefault("app:" + low, {"label": app_label(p, name), "kind": "process",
                                                   "roots": Counter(), "active_roots": set(), "exe": low})
            if from_window and info["roots"] and root not in info["roots"]:
                return  # gleiche App laeuft schon mit Ton -> keine Dublette nur wegen eines Fensters
            info["roots"][root] += weight
            if active:
                info["active_roots"].add(root)

        for s in data.get("sessions", []):
            add(int(s["pid"]), 10, bool(s.get("active")), False)
        # Apps mit Fenster, die gerade keinen Ton haben (z. B. pausiertes Spotify) trotzdem anzeigen/mitschneiden
        for pid in windowed_pids():
            add(pid, 1, False, True)
        avail: dict[str, dict] = {}
        mic_id = self.cfg["mic_device"] or "default"
        mic_name = "Standard"
        for d in self.devices["capture"]:
            if (mic_id == "default" and d.get("default")) or d["id"] == mic_id:
                mic_name = d["name"]
        m = re.match(r"^(?:Mikrofon|Microphone|Headset)\s*\((.+)\)$", mic_name)
        if m:
            mic_name = m.group(1)
        avail["mic"] = {"label": f"Mikrofon · {mic_name}", "kind": "mic", "arg": mic_id, "active": True}
        if self.cfg["capture_system"]:
            avail["system"] = {"label": "System (alles zusammen)", "kind": "loopback", "arg": "default",
                               "active": True}
        with self.lock:
            running_args = {k: str(s.arg) for k, s in self.sources.items()}
        for key, info in sorted(apps.items(), key=lambda kv: kv[1]["label"].lower()):
            roots = [r for r, _ in info["roots"].most_common()]
            # bisherige Zuordnung behalten, damit laufende Quellen nicht neu starten
            prev = running_args.get(key)
            if prev is not None and int(prev) in roots:
                roots.remove(int(prev))
                roots.insert(0, int(prev))
            for i, root in enumerate(roots):
                k = key if i == 0 else f"{key}#{root}"
                avail[k] = {"label": info["label"] + ("" if i == 0 else f" ({i + 1})"), "kind": "process",
                            "arg": root, "active": root in info["active_roots"], "exe": info["exe"]}
        with self.lock:
            # Quellen, die gerade laufen (z. B. waehrend Aufnahme), nicht aus der Liste verlieren
            for key, src in self.sources.items():
                if key not in avail and src.kind == "process" and psutil.pid_exists(int(src.arg)):
                    avail[key] = {"label": src.label, "kind": "process", "arg": src.arg, "active": False,
                                  "exe": key[4:]}
            self.available = avail

    def desired_keys(self) -> set[str]:
        avail = set(self.available)
        if self.cfg["capture_mode"] == "all":
            keys = set(avail)
        else:
            keys = set(self.cfg["selected_sources"]) & avail
        keys |= self.forced & avail
        if self.cfg["mic_passthrough"] or self.cfg["voice_monitor"]:
            keys.add("mic")
        keys |= set((self.cfg["route_sources"] or {}).keys())
        if self.cfg.get("triggers_enabled") or self.cfg.get("voice_commands"):
            keys.add("mic")
        if self.cfg.get("autoclip_enabled"):
            ac = self.cfg.get("autoclip_apps")
            if isinstance(ac, list):
                keys |= set(avail) if "*" in ac else set(ac)
            elif self.cfg.get("autoclip_source") == "mic":
                keys.add("mic")
        return keys & avail

    def reconcile(self):
        with self.lock:
            desired = self.desired_keys()
            now = self.clock.now()
            for key in list(self.sources):
                s = self.sources[key]
                info = self.available.get(key)
                gone = info is None or str(info["arg"]) != str(s.arg)
                if key not in desired or gone:
                    if s.recorder and self.recording:
                        rec = s.stop_recording(now)
                        if rec:
                            self.recording["done"].append(rec)
                    s.stop()
                    del self.sources[key]
            for key in desired:
                info = self.available[key]
                s = self.sources.get(key)
                if s is None:
                    s = CaptureSource(key, info["label"], info["kind"], info["arg"], self.clock,
                                      float(self.cfg["buffer_seconds"]), on_chunk=self._on_chunk)
                    self.sources[key] = s
                    s.start()
                    if self.recording and self._rec_wants(key):
                        s.start_recording(self._rec_path(key), self.recording["start"])
                else:
                    s.label = info["label"]
                    if not s.alive():
                        wait = min(30.0, 2.0 * (2 ** min(s.fail_count, 4)))
                        if time.time() - s.started_at > wait:
                            s.start()

    def _on_chunk(self, src: CaptureSource, data: np.ndarray):
        if self.mixer is not None and src.key != "mic" and src.key in (self.cfg["route_sources"] or {}):
            self.mixer.feed_route(src.key, data)
        if src.key == "mic" and self.mixer is not None and self.mixer.wants_mic():
            self.mixer.feed_live(data)
        for fn in self.listeners:
            try:
                fn(src.key, data)
            except Exception:
                log.exception("Audio-Abnehmer")

    # ---------------------------------------------------------- Clips
    def snapshot(self):
        with self.lock:
            return [(s.key, s.label, s.status, s.error, s.take_level(), s.last_sound, s.recorder is not None)
                    for s in self.sources.values()]

    def apps_on_device(self, dev_id: str, only_active=True) -> list[str]:
        """Andere Apps, die gerade auf ein Ausgabegeraet (z. B. das virtuelle Kabel) Ton ausgeben."""
        if not dev_id:
            return []
        own = os.getpid()
        names = []
        for s in list(self.sessions):
            if s.get("dev") != dev_id or int(s["pid"]) == own:
                continue
            if only_active and not (s.get("active") and float(s.get("peak", 0)) > 0.0005):
                continue
            try:
                p = psutil.Process(int(s["pid"]))
                name = p.name()
            except Exception:
                continue
            if name.lower() == "audiocap.exe":
                continue
            label = app_label(p, name)
            if label not in names:
                names.append(label)
        return names

    def running_count(self) -> int:
        with self.lock:
            return sum(1 for s in self.sources.values() if s.status == "läuft")

    def make_clip(self, seconds: float | None = None, keys=None) -> dict | None:
        seconds = float(seconds or self.cfg["buffer_seconds"])
        end = self.clock.now()
        start = end - int(seconds * SR)
        with self.lock:
            srcs = list(self.sources.values())
        stamp = _dt.datetime.now()
        cid = stamp.strftime("%Y%m%d-%H%M%S-%f")[:-3]
        d = CLIPS_DIR / cid
        d.mkdir(parents=True, exist_ok=True)
        stems = []
        for s in srcs:
            if keys and s.key not in keys:
                continue
            a = s.read(start, end)
            pk = float(np.abs(a).max()) if len(a) else 0.0
            if pk < SILENCE:
                continue
            fn = safe_name(s.key.replace("app:", "")) + ".wav"
            sf.write(str(d / fn), np.clip(a, -1, 1), SR, subtype="PCM_16")
            stems.append({"key": s.key, "label": s.label, "file": fn, "peak": round(pk, 4)})
        if not stems:
            shutil.rmtree(d, ignore_errors=True)
            return None
        meta = {"id": cid, "name": "Clip " + stamp.strftime("%d.%m. %H:%M:%S"), "created": stamp.isoformat(),
                "duration": seconds, "kind": "clip", "stems": stems, "edit": {}}
        (d / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return meta

    # ---------------------------------------------------------- Aufnahme
    def _rec_wants(self, key: str) -> bool:
        keys = self.recording.get("keys") if self.recording else None
        return not keys or key in keys

    def _rec_path(self, key: str) -> Path:
        return self.recording["dir"] / (safe_name(key.replace("app:", "")) + ".wav")

    def start_recording(self, keys=None) -> bool:
        with self.lock:
            if self.recording:
                return False
            if keys is None:
                keys = list(self.cfg["record_sources"]) or None
            stamp = _dt.datetime.now()
            rid = stamp.strftime("%Y%m%d-%H%M%S-%f")[:-3]
            d = CLIPS_DIR / rid
            d.mkdir(parents=True, exist_ok=True)
            self.recording = {"id": rid, "dir": d, "start": self.clock.now(), "keys": set(keys) if keys else None,
                              "t": time.time(), "stamp": stamp, "done": []}
            if keys:
                self.forced |= set(keys)
            for s in self.sources.values():
                if self._rec_wants(s.key):
                    s.start_recording(self._rec_path(s.key), self.recording["start"])
        if keys:
            self.reconcile()
        return True

    def stop_recording(self) -> dict | None:
        with self.lock:
            rec = self.recording
            if not rec:
                return None
            end = self.clock.now()
            finished = list(rec["done"])
            for s in self.sources.values():
                if s.recorder:
                    r = s.stop_recording(end)
                    if r:
                        finished.append(r)
            self.recording = None
            if rec["keys"]:
                self.forced -= rec["keys"]
        stems = []
        for r in finished:
            if r.peak < SILENCE:
                try:
                    r.path.unlink()
                except Exception:
                    pass
                continue
            stems.append({"key": r.key, "label": r.label, "file": r.path.name, "peak": round(r.peak, 4)})
        d = rec["dir"]
        if not stems:
            shutil.rmtree(d, ignore_errors=True)
            return None
        dur = (end - rec["start"]) / SR
        meta = {"id": rec["id"], "name": "Aufnahme " + rec["stamp"].strftime("%d.%m. %H:%M:%S"),
                "created": rec["stamp"].isoformat(), "duration": dur, "kind": "recording", "stems": stems,
                "edit": {}}
        (d / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        self.poke()
        return meta

    def recording_seconds(self) -> float:
        rec = self.recording
        return time.time() - rec["t"] if rec else 0.0
