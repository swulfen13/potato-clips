"""Effekt-Prozess fuer die Live-Stimme.

Laeuft als eigener, kleiner Prozess (vom Audio-Helfer gestartet) und macht nur eins: Stimm-Bloecke
mit dem gewaehlten Effekt berechnen. Weil hier sonst nichts laeuft (keine Oberflaeche, kein
Quellen-Scan), gibt es keine Python-Haenger, die die Stimme abreissen lassen.

Protokoll (binaer, ueber stdin/stdout):
  rein : [u8 typ][u32 laenge][daten]   typ 1 = Mono-Block float32, typ 2 = Text "set <preset> <staerke>"
  raus : [u32 laenge][daten]           bearbeiteter Mono-Block float32 (laenge 0 = bereit)
"""
from __future__ import annotations

import os
import struct
import sys


def _std_streams():
    """Rohe Pipe-Handles holen - funktioniert auch in der Fenster-EXE, wo sys.stdin/stdout fehlen."""
    if sys.platform == "win32":
        import ctypes
        import msvcrt
        k32 = ctypes.windll.kernel32
        k32.GetStdHandle.restype = ctypes.c_void_p
        hin = k32.GetStdHandle(-10)
        hout = k32.GetStdHandle(-11)
        fin = os.fdopen(msvcrt.open_osfhandle(hin, os.O_RDONLY | os.O_BINARY), "rb", buffering=0)
        fout = os.fdopen(msvcrt.open_osfhandle(hout, os.O_WRONLY | os.O_BINARY), "wb", buffering=0)
        return fin, fout
    return sys.stdin.buffer, sys.stdout.buffer


def _read_exact(f, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = f.read(n - len(buf))
        if not chunk:
            return b""
        buf += chunk
    return bytes(buf)


def main() -> int:
    fin, fout = _std_streams()
    import gc

    import numpy as np

    from .effects import VoiceChanger

    vc = VoiceChanger()
    # einmal "aufwaermen", damit der erste echte Block nicht langsam ist
    for key in ("potato", "demon"):
        vc.set(key, 0.5)
        vc.process(np.zeros((480, 1), np.float32))
    vc.set("", 0)
    gc.collect()
    gc.freeze()            # alles Bisherige nie wieder pruefen -> keine spuerbaren GC-Pausen
    fout.write(struct.pack("<I", 0))          # bereit
    hdr = struct.Struct("<BI")
    while True:
        h = _read_exact(fin, 5)
        if not h:
            return 0
        typ, ln = hdr.unpack(h)
        payload = _read_exact(fin, ln) if ln else b""
        if ln and not payload:
            return 0
        if typ == 2:
            parts = payload.decode("utf-8", "replace").split(" ", 3)
            key = parts[1] if len(parts) > 1 and parts[1] != "-" else ""
            try:
                amount = float(parts[2]) if len(parts) > 2 else 0.5
            except ValueError:
                amount = 0.5
            try:
                if key.startswith("custom_") and len(parts) > 3:
                    import json
                    from .effects import register_custom
                    register_custom(key, "", "", json.loads(parts[3]))
                vc.set(key, amount)
            except Exception:
                vc.set("", 0)
            continue
        if typ != 1:
            continue
        x = np.frombuffer(payload, np.float32)
        try:
            y = vc.process(x[:, None])[:, 0]
            if len(y) != len(x):
                y = np.resize(y, len(x))
            y = np.ascontiguousarray(y, dtype=np.float32)
        except Exception:
            y = x
        try:
            fout.write(struct.pack("<I", y.nbytes) + y.tobytes())
        except OSError:
            return 0


if __name__ == "__main__":
    sys.exit(main())
