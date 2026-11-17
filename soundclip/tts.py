"""Text vorlesen lassen – mit den Windows-Stimmen, komplett lokal (SAPI direkt per COM, ohne PowerShell)."""
from __future__ import annotations

import ctypes
import tempfile
import threading
import uuid
from pathlib import Path

_voices: list[dict] | None = None
_lock = threading.Lock()
SAFT48kHz16BitStereo = 39
SSFMCreateForWrite = 3
SVSFIsNotXML = 16


def _culture(lcid_hex: str) -> str:
    try:
        lcid = int(str(lcid_hex).split(";")[0], 16)
        buf = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.LCIDToLocaleName(lcid, buf, 85, 0):
            return buf.value
    except Exception:
        pass
    return ""


class _Com:
    """COM fuer den aktuellen Thread an- und wieder abmelden."""

    def __enter__(self):
        import comtypes
        try:
            comtypes.CoInitializeEx()
            self.inited = True
        except OSError:              # Thread hat COM schon in anderer Art gestartet - dann einfach nutzen
            self.inited = False
        return self

    def __exit__(self, *a):
        import comtypes
        if self.inited:
            comtypes.CoUninitialize()


def _tokens(sp):
    toks = sp.GetVoices()
    return [toks.Item(i) for i in range(toks.Count)]


def voices() -> list[dict]:
    """Installierte Windows-Stimmen: [{"name", "culture", "gender"}]."""
    global _voices
    if _voices is None:
        import comtypes.client as cc
        with _lock, _Com():
            sp = cc.CreateObject("SAPI.SpVoice", dynamic=True)
            out = []
            for t in _tokens(sp):
                out.append({"name": str(t.GetAttribute("Name") or t.GetDescription()),
                            "culture": _culture(t.GetAttribute("Language")),
                            "gender": str(t.GetAttribute("Gender") or "")})
            del sp
        _voices = out
    return _voices


def synth(text: str, voice: str = "", rate: int = 0) -> Path:
    """Text als WAV-Datei sprechen lassen und den Pfad zurueckgeben."""
    text = (text or "").strip()[:600]
    if not text:
        raise ValueError("kein Text")
    path = Path(tempfile.gettempdir()) / f"potato_tts_{uuid.uuid4().hex[:8]}.wav"
    rate = max(-10, min(10, int(rate)))
    import comtypes.client as cc
    with _lock, _Com():
        sp = cc.CreateObject("SAPI.SpVoice", dynamic=True)
        if voice:
            for t in _tokens(sp):
                if str(t.GetAttribute("Name")) == voice or str(t.GetDescription()).startswith(voice):
                    sp.Voice = t
                    break
        st = cc.CreateObject("SAPI.SpFileStream", dynamic=True)
        fmt = cc.CreateObject("SAPI.SpAudioFormat", dynamic=True)
        fmt.Type = SAFT48kHz16BitStereo
        st.Format = fmt
        st.Open(str(path), SSFMCreateForWrite, False)
        try:
            sp.AudioOutputStream = st
            sp.Rate = rate
            sp.Speak(text, SVSFIsNotXML)   # synchron; Text nie als Steuer-XML lesen (kommt evtl. vom Handy)
        finally:
            st.Close()
            del st, fmt, sp
    if not path.exists() or path.stat().st_size < 100:
        raise RuntimeError("keine Sprachausgabe erzeugt")
    return path
