"""Text vorlesen lassen – mit den Windows-Stimmen, komplett lokal (System.Speech ueber PowerShell)."""
from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import uuid
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000
_voices: list[dict] | None = None


def _ps(script: str, timeout: float = 30) -> str:
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
                       capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:300] or "PowerShell-Fehler")
    return r.stdout.decode("utf-8", "replace")


def voices() -> list[dict]:
    """Installierte Windows-Stimmen: [{"name", "culture", "gender"}]."""
    global _voices
    if _voices is None:
        out = _ps("[Console]::OutputEncoding=[Text.Encoding]::UTF8; Add-Type -AssemblyName System.Speech;"
                  "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                  "$s.GetInstalledVoices() | Where-Object {$_.Enabled} | ForEach-Object {"
                  "[pscustomobject]@{name=$_.VoiceInfo.Name; culture=$_.VoiceInfo.Culture.Name;"
                  "gender=[string]$_.VoiceInfo.Gender}} | ConvertTo-Json -Compress")
        out = out.strip()
        data = json.loads(out) if out else []
        _voices = data if isinstance(data, list) else [data]
    return _voices


def synth(text: str, voice: str = "", rate: int = 0) -> Path:
    """Text als WAV-Datei sprechen lassen und den Pfad zurueckgeben."""
    text = (text or "").strip()[:600]
    if not text:
        raise ValueError("kein Text")
    path = Path(tempfile.gettempdir()) / f"potato_tts_{uuid.uuid4().hex[:8]}.wav"
    # Text und Stimme als Base64, damit keine Zeichen das Skript kaputt machen koennen
    t64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    v64 = base64.b64encode((voice or "").encode("utf-8")).decode("ascii")
    rate = max(-10, min(10, int(rate)))
    _ps("Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$t=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{t64}'));"
        f"$v=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{v64}'));"
        "if($v){ try { $s.SelectVoice($v) } catch {} };"
        f"$s.Rate={rate};"
        f"$s.SetOutputToWaveFile('{str(path).replace(chr(39), chr(39) * 2)}');"
        "$s.Speak($t); $s.Dispose()", timeout=60)
    if not path.exists() or path.stat().st_size < 100:
        raise RuntimeError("keine Sprachausgabe erzeugt")
    return path
