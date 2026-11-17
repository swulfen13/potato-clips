"""Clip als Video (MP4) exportieren: animierte Wellenform/Balken, Titel und Fortschritt.

Die Bilder werden mit Qt gezeichnet und per Pipe an ffmpeg gegeben (ffmpeg kommt aus dem Paket
imageio-ffmpeg und wird mitgeliefert)."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading

import numpy as np
import soundfile as sf

from .config import SR

log = logging.getLogger("soundclip")

FPS = 30
FORMATS = {"9:16": (720, 1280), "16:9": (1280, 720), "1:1": (1080, 1080)}
BARS = 48
MAX_SECONDS = 600


def ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _spectrum_frames(data: np.ndarray, n_frames: int) -> np.ndarray:
    """Pro Bild ein Satz Balkenhoehen 0..1 (logarithmisch verteilte Frequenzbaender, weich geglaettet)."""
    mono = data.mean(axis=1).astype(np.float32) if data.ndim == 2 else data.astype(np.float32)
    win = 2048
    hann = np.hanning(win).astype(np.float32)
    freqs = np.fft.rfftfreq(win, 1 / SR)
    edges = np.geomspace(50, 14000, BARS + 1)
    idx = [np.flatnonzero((freqs >= edges[i]) & (freqs < edges[i + 1])) for i in range(BARS)]
    idx = [ix if len(ix) else np.array([int(np.searchsorted(freqs, edges[i]))]) for i, ix in enumerate(idx)]
    out = np.zeros((n_frames, BARS), np.float32)
    padded = np.concatenate([np.zeros(win, np.float32), mono, np.zeros(win, np.float32)])
    for f in range(n_frames):
        c = int(f / FPS * SR) + win
        seg = padded[c - win // 2: c + win // 2]
        if len(seg) < win:
            continue
        mag = np.abs(np.fft.rfft(seg * hann))
        out[f] = [float(mag[ix].mean()) for ix in idx]
    db = 20 * np.log10(out + 1e-6)
    top = np.percentile(db, 99.5) if db.size else 0
    v = np.clip((db - (top - 55)) / 55, 0, 1)
    # Nachleuchten: fallen langsam, steigen sofort
    for f in range(1, n_frames):
        v[f] = np.maximum(v[f], v[f - 1] * 0.86)
    return v


def _overview(data: np.ndarray, n: int) -> np.ndarray:
    mono = np.abs(data).max(axis=1) if data.ndim == 2 else np.abs(data)
    if len(mono) < n:
        return np.pad(mono, (0, n - len(mono)))
    cut = len(mono) - len(mono) % n
    pk = mono[:cut].reshape(n, -1).max(axis=1)
    m = pk.max()
    return pk / m if m > 0 else pk


def render_video(data: np.ndarray, out_path: str, title: str, fmt: str = "9:16", style: str = "pro",
                 progress=None, cancel: threading.Event | None = None, words: list | None = None) -> str:
    """Rendert das Video. progress(0..1) kommt aus diesem (Hintergrund-)Thread."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPen

    if data is None or not len(data):
        raise ValueError("Der Clip ist leer")
    data = np.asarray(data, np.float32)
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    data = data[: MAX_SECONDS * SR]
    dur = len(data) / SR
    W, H = FORMATS.get(fmt, FORMATS["9:16"])
    n_frames = max(1, int(np.ceil(dur * FPS)))
    spec = _spectrum_frames(data, n_frames)
    over = _overview(data, 220)
    pot = style == "potato"

    tmp_wav = tempfile.mkstemp(suffix=".wav", prefix="pc_vid_")[1]
    sf.write(tmp_wav, np.clip(data, -1, 1), SR, subtype="PCM_16")
    err_path = tempfile.mkstemp(suffix=".txt", prefix="pc_vid_err_")[1]
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", tmp_wav, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_path]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with open(err_path, "wb") as err:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err,
                                creationflags=flags)
    img = QImage(W, H, QImage.Format_ARGB32)
    s = min(W, H) / 720.0
    if pot:
        bg1 = bg2 = QColor("#FFE94D")
        bar_col, bar_hi, text_col, sub_col = QColor("#111"), QColor("#FF3D8B"), QColor("#111"), QColor("#333")
        tfont = QFont("Bungee")
        tfont.setPixelSize(int(46 * s))
        sfont = QFont("Comic Neue")
        sfont.setBold(True)
        sfont.setPixelSize(int(24 * s))
    else:
        bg1, bg2 = QColor("#14161B"), QColor("#0B0C0F")
        bar_col, bar_hi, text_col, sub_col = QColor("#F2A93B"), QColor("#FFD08A"), QColor("#E9EAEE"), QColor("#8B909C")
        tfont = QFont("Inter")
        tfont.setPixelSize(int(44 * s))
        tfont.setBold(True)
        sfont = QFont("Inter")
        sfont.setPixelSize(int(22 * s))
    done_col = QColor("#FF3D8B") if pot else QColor("#F2A93B")
    lines = []
    if words:
        from .transcribe import subtitle_lines
        lines = subtitle_lines(words)
    sub_font = QFont("Bungee" if pot else "Inter")
    sub_font.setPixelSize(int(40 * s))
    sub_font.setBold(True)
    if not pot:
        sub_col = QColor("#3A3E47")
    ok = False
    try:
        for f in range(n_frames):
            if cancel is not None and cancel.is_set():
                raise RuntimeError("abgebrochen")
            t = f / FPS
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            g = QLinearGradient(0, 0, 0, H)
            g.setColorAt(0, bg1)
            g.setColorAt(1, bg2)
            p.fillRect(0, 0, W, H, g)
            if pot:   # Rahmen + schraege Streifen fuer den Trash-Look
                p.setPen(QPen(QColor("#111"), 10 * s))
                p.setBrush(Qt.NoBrush)
                p.drawRect(QRectF(5 * s, 5 * s, W - 10 * s, H - 10 * s))
            # Titel
            margin = 56 * s
            p.setFont(tfont)
            p.setPen(text_col)
            title_rect = QRectF(margin, H * (0.10 if H > W else 0.08), W - 2 * margin, H * 0.22)
            p.drawText(title_rect, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, title.upper() if pot else title)
            # Balken (gespiegelt um die Mitte)
            v = spec[f]
            cy = H * 0.52
            area_w = W - 2 * margin
            bw = area_w / BARS
            maxh = H * (0.20 if H > W else 0.26)
            p.setPen(Qt.NoPen)
            for i in range(BARS):
                h = max(3 * s, float(v[i]) * maxh)
                x = margin + i * bw + bw * 0.18
                w = bw * 0.64
                col = bar_hi if v[i] > 0.82 else bar_col
                if pot:
                    p.setBrush(QColor("#111"))
                    p.drawRect(QRectF(x + 3 * s, cy - h + 3 * s, w, 2 * h))
                    p.setBrush(QColor(["#FF3D8B", "#3DE8FF", "#B6FF3B", "#FFFFFF"][i % 4]))
                    p.setPen(QPen(QColor("#111"), 2 * s))
                    p.drawRect(QRectF(x, cy - h, w, 2 * h))
                    p.setPen(Qt.NoPen)
                else:
                    p.setBrush(col)
                    p.drawRoundedRect(QRectF(x, cy - h, w, 2 * h), w / 2, w / 2)
            # Uebersicht + Abspielkopf
            oy = H * (0.80 if H > W else 0.84)
            oh = 46 * s
            ow = area_w / len(over)
            pos = t / dur if dur else 0
            for i, a in enumerate(over):
                hh = max(2 * s, float(a) * oh)
                done = i / len(over) <= pos
                p.setBrush(done_col if done else sub_col)
                p.drawRect(QRectF(margin + i * ow, oy - hh / 2, max(1.0, ow * 0.7), hh))
            p.setBrush(bar_hi if not pot else QColor("#FF3D8B"))
            p.drawRect(QRectF(margin + area_w * pos - 2 * s, oy - oh * 0.75, 4 * s, oh * 1.5))
            # Untertitel: aktuelle Zeile, das gerade gesprochene Wort hervorgehoben
            line = next((ln for ln in lines if ln["s"] - 0.15 <= t <= ln["e"] + 0.6), None)
            if line:
                _draw_subtitle(p, line, t, sub_font, W, H, margin, pot, done_col, QColor, QFontMetricsF, QRectF, Qt)
            # Zeit + Wasserzeichen
            p.setFont(sfont)
            p.setPen(sub_col)
            p.drawText(QRectF(margin, oy + oh * 0.7, area_w, 40 * s), Qt.AlignLeft | Qt.AlignTop,
                       f"{int(t // 60)}:{int(t % 60):02d} / {int(dur // 60)}:{int(dur % 60):02d}")
            p.drawText(QRectF(margin, H - 70 * s, area_w, 40 * s), Qt.AlignHCenter | Qt.AlignVCenter,
                       "🥔 Potato Clips")
            p.end()
            proc.stdin.write(memoryview(img.constBits())[: W * H * 4])
            if progress and f % 10 == 0:
                progress(f / n_frames * 0.97)
        proc.stdin.close()
        code = proc.wait(timeout=300)
        if code != 0:
            with open(err_path, "rb") as e:
                msg = e.read().decode("utf-8", "replace").strip()[-400:]
            raise RuntimeError(f"ffmpeg: {msg or code}")
        ok = True
        if progress:
            progress(1.0)
        return out_path
    finally:
        if not ok:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                os.remove(out_path)
            except Exception:
                pass
        for f_ in (tmp_wav, err_path):
            try:
                os.remove(f_)
            except Exception:
                pass


def _draw_subtitle(p, line, t, font, W, H, margin, pot, hi_col, QColor, QFontMetricsF, QRectF, Qt):
    """Eine Untertitel-Zeile mittig im unteren Drittel, aktuelles Wort farbig."""
    words = [w["w"].upper() if pot else w["w"] for w in line["words"]]
    f = type(font)(font)                           # Kopie - die Grundgroesse bleibt fuer die naechste Zeile
    size = f.pixelSize()
    area = W - 2 * margin
    fm = QFontMetricsF(f)
    space = fm.horizontalAdvance(" ")
    total = sum(fm.horizontalAdvance(w) for w in words) + space * (len(words) - 1)
    while total > area and size > 18:              # zu breit -> Schrift kleiner
        size = int(size * 0.9)
        f.setPixelSize(size)
        fm = QFontMetricsF(f)
        space = fm.horizontalAdvance(" ")
        total = sum(fm.horizontalAdvance(w) for w in words) + space * (len(words) - 1)
    p.setFont(f)
    y = H * (0.66 if H > W else 0.70)
    h = fm.height() * 1.35
    box = QRectF((W - total) / 2 - 18, y - h / 2, total + 36, h)
    p.setPen(QColor("#111") if pot else Qt.NoPen)
    p.setBrush(QColor("#FFFFFF") if pot else QColor(0, 0, 0, 170))
    if pot:
        p.drawRect(box)
    else:
        p.drawRoundedRect(box, 12, 12)
    x = (W - total) / 2
    for w, word in zip(line["words"], words):
        cur = w["s"] - 0.05 <= t <= w["e"] + 0.05
        p.setPen(hi_col if cur else (QColor("#111") if pot else QColor("#FFFFFF")))
        wd = fm.horizontalAdvance(word)
        p.drawText(QRectF(x, y - h / 2, wd + 2, h), Qt.AlignVCenter | Qt.AlignLeft, word)
        x += wd + space
