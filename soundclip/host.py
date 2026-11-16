"""Ein einziger Helfer-Prozess (audiocap.exe server) fuer ALLE Audio-Streams.

Vorteil: Windows zeigt im Lautstaerkemixer nur noch einen Eintrag "Potato Clips" pro Geraet
statt einem "audiocap" pro Quelle. Protokoll siehe helper/audiocap.cpp (cmdServer).
"""
from __future__ import annotations

import io
import itertools
import logging
import queue
import struct
import subprocess
import threading
import time

import numpy as np

from .config import HELPER

log = logging.getLogger("soundclip.host")
CREATE_NO_WINDOW = 0x08000000
HDR = struct.Struct("<BHI")  # typ, id, laenge


class StreamHandler:
    """Schnittstelle fuer Empfaenger eines Streams."""
    inline = False      # True: Audio direkt im Lese-Thread verarbeiten (nur fuer kurze, eilige Arbeit)

    def on_audio(self, payload: bytes):
        pass

    def on_silence(self, frames: int):
        pass

    def on_levels(self, a: float, b: float):
        pass

    def on_log(self, line: str):
        pass

    def on_request(self, frames: int) -> bytes:
        return bytes(frames * 8)

    def on_end(self, code: int):
        pass


class HelperHost:
    _inst: "HelperHost | None" = None
    _inst_lock = threading.Lock()

    @classmethod
    def get(cls) -> "HelperHost":
        with cls._inst_lock:
            if cls._inst is None:
                cls._inst = HelperHost()
            return cls._inst

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.lock = threading.RLock()
        self.wlock = threading.Lock()
        self.handlers: dict[int, StreamHandler] = {}
        self._ids = itertools.count(1)
        self.starts = 0
        self.queue: "queue.SimpleQueue" = queue.SimpleQueue()
        self.max_request_ms = 0.0
        self.last_stats = ""
        threading.Thread(target=self._worker, daemon=True, name="audiocap-worker").start()

    # ---------------------------------------------------------- Prozess
    @property
    def pid(self) -> int | None:
        p = self.proc
        return p.pid if p is not None and p.poll() is None else None

    def _ensure(self):
        if self.proc is not None and self.proc.poll() is None:
            return
        self.proc = subprocess.Popen([str(HELPER), "server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, bufsize=0, creationflags=CREATE_NO_WINDOW)
        self.starts += 1
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True, name="audiocap-host").start()
        log.info("Audio-Helfer gestartet (pid %s)", self.proc.pid)

    def _new_id(self) -> int:
        while True:
            sid = next(self._ids) & 0xFFFF
            if sid and sid not in self.handlers:
                return sid

    def start(self, mode: str, arg, handler: StreamHandler) -> int:
        with self.lock:
            self._ensure()
            sid = self._new_id()
            self.handlers[sid] = handler
            self._send(1, sid, f"start {mode} {arg}".encode("utf-8"))
            return sid

    def stop(self, sid: int | None):
        if not sid:
            return
        with self.lock:
            self.handlers.pop(sid, None)
            if self.proc is not None and self.proc.poll() is None:
                self._send(1, sid, b"stop")

    def command(self, text: str, sid: int = 0):
        """Befehl an den Helfer (z. B. voiceconf, voicetarget, stats)."""
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                return
            self._send(1, sid, text.encode("utf-8"))

    def send_data(self, sid: int, payload: bytes):
        """Audiodaten an einen Stream im Helfer (z. B. Stimme mit Effekt zurueck)."""
        if self.proc is not None:
            self._send(2, sid, payload)

    def _send(self, typ: int, sid: int, payload: bytes):
        p = self.proc
        if p is None:
            return
        with self.wlock:
            try:
                p.stdin.write(HDR.pack(typ, sid, len(payload)))
                if payload:
                    p.stdin.write(payload)
            except Exception:
                pass

    def shutdown(self):
        with self.lock:
            p, self.proc = self.proc, None
            self.handlers.clear()
        if p is not None:
            try:
                p.stdin.close()
            except Exception:
                pass
            try:
                p.wait(2)
            except Exception:
                p.kill()

    # ---------------------------------------------------------- Empfang
    def _reader(self, proc: subprocess.Popen):
        f = io.BufferedReader(proc.stdout, buffer_size=1 << 16)
        try:
            while True:
                hdr = f.read(7)
                if len(hdr) < 7:
                    break
                typ, sid, ln = HDR.unpack(hdr)
                payload = f.read(ln) if ln else b""
                if len(payload) < ln:
                    break
                h = self.handlers.get(sid)
                try:
                    if typ == 1:
                        if h is not None:
                            if h.inline:                         # Stimme: sofort, nicht hinter Clip-Daten anstellen
                                h.on_audio(payload)
                            else:
                                self.queue.put((h, 1, payload))  # Aufnahme: im Worker verarbeiten
                    elif typ == 6:
                        if h is not None and len(payload) >= 8:
                            a, b = struct.unpack("<ff", payload[:8])
                            h.on_levels(a, b)
                    elif typ == 5:
                        if h is not None:
                            self.queue.put((h, 5, struct.unpack("<I", payload)[0]))
                    elif typ == 2:
                        line = payload.decode("utf-8", errors="replace")
                        if h is not None:
                            h.on_log(line)
                        elif sid == 0:
                            if line.startswith("stats"):
                                self.last_stats = line
                            log.info(line)
                    elif typ == 3:                              # Wiedergabe: sofort beantworten
                        t0 = time.perf_counter()
                        frames = struct.unpack("<I", payload)[0]
                        data = h.on_request(frames) if h is not None else bytes(frames * 8)
                        self._send(2, sid, data)
                        dt = (time.perf_counter() - t0) * 1000
                        if dt > self.max_request_ms:
                            self.max_request_ms = dt
                    elif typ == 4:
                        code = struct.unpack("<i", payload)[0] if len(payload) >= 4 else 0
                        with self.lock:
                            h = self.handlers.pop(sid, None)
                        if h is not None:
                            h.on_end(code)
                except Exception:
                    log.exception("Stream %s (Typ %s)", sid, typ)
        except Exception:
            log.exception("Helfer-Verbindung")
        # Prozess weg -> alle Streams als beendet melden (werden vom Watchdog neu gestartet)
        with self.lock:
            if self.proc is proc:
                self.proc = None
            hs = list(self.handlers.values())
            self.handlers.clear()
        if hs:
            log.warning("Audio-Helfer beendet – %d Streams werden neu gestartet", len(hs))
        for h in hs:
            try:
                h.on_end(-1)
            except Exception:
                pass


    def _worker(self):
        while True:
            h, typ, data = self.queue.get()
            try:
                if typ == 1:
                    h.on_audio(data)
                else:
                    h.on_silence(data)
            except Exception:
                log.exception("Aufnahme-Verarbeitung")


def zeros_bytes(frames: int) -> bytes:
    return np.zeros((frames, 2), np.float32).tobytes()
