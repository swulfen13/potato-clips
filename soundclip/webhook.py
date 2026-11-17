"""Clip direkt in einen Discord-Kanal posten (ueber einen Webhook - kein Bot, kein Login noetig)."""
from __future__ import annotations

import json
import mimetypes
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path

_RX = re.compile(r"^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/\d{5,25}/[A-Za-z0-9_\-]{20,100}$")
LIMIT = 10 * 1024 * 1024 - 64 * 1024       # Discord: 10 MB pro Datei ohne Boost


class WebhookError(Exception):
    pass


def valid(url: str) -> bool:
    return bool(_RX.match((url or "").strip()))


def _multipart(fields: dict, path: Path):
    boundary = "----potato" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n"
                "Content-Type: application/json\r\n\r\n").encode() + v.encode("utf-8") + b"\r\n"
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    fname = re.sub(r'[\r\n"]', "_", path.name)
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{fname}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + path.read_bytes() + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def post(url: str, path: str | Path, text: str = "", name: str = "Potato Clips", _check=True,
         timeout: float = 60) -> dict:
    """Datei (+ kurzer Text) an den Webhook schicken. Wirft WebhookError mit verstaendlicher Meldung."""
    url = (url or "").strip()
    if _check and not valid(url):
        raise WebhookError("Das ist kein Discord-Webhook-Link.")
    path = Path(path)
    if path.stat().st_size > LIMIT:
        raise WebhookError("Die Datei ist größer als 10 MB – Discord nimmt sie nicht an.")
    payload = {"content": (text or "")[:1900], "username": name[:80],
               "allowed_mentions": {"parse": []},           # nie @everyone/@here auslösen
               "attachments": [{"id": 0, "filename": path.name}]}
    body, ctype = _multipart({"payload_json": json.dumps(payload, ensure_ascii=False)}, path)
    req = urllib.request.Request(url + ("&" if "?" in url else "?") + "wait=true", data=body, method="POST",
                                 headers={"Content-Type": ctype, "User-Agent": "PotatoClips (webhook)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise WebhookError("Der Webhook existiert nicht mehr oder wurde gelöscht.")
        if e.code == 413:
            raise WebhookError("Die Datei ist zu groß für Discord.")
        if e.code == 429:
            raise WebhookError("Discord sagt: zu viele Nachrichten – kurz warten.")
        raise WebhookError(f"Discord-Fehler {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise WebhookError(f"Keine Verbindung zu Discord ({getattr(e, 'reason', e)}).")
