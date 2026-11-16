"""Mini-Overlay: immer im Vordergrund, klick-durchlaessig, zeigt Status + kurze Meldungen."""
from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from .widgets import ACCENT, GREEN, RED

KIND_COLORS = {"ok": GREEN, "rec": RED, "warn": "#ffb703", "info": ACCENT}


class Overlay(QWidget):
    def __init__(self, ctl):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.ctl = ctl
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.toasts: list[tuple[float, str, str]] = []
        self.setFixedSize(340, 200)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)
        self._raise_counter = 0
        ctl.toast.connect(self.add_toast)
        ctl.overlayToggled.connect(self.apply_visibility)

    def add_toast(self, text: str, kind: str):
        self.toasts.append((time.time(), text, kind))
        self.toasts = self.toasts[-4:]
        self.update()

    def apply_visibility(self, *_):
        if self.ctl.cfg["overlay_enabled"]:
            self._place()
            self.show()
            self.raise_()
        else:
            self.hide()

    def _place(self):
        scr = QGuiApplication.primaryScreen().availableGeometry()
        c = self.ctl.cfg["overlay_corner"]
        m = 14
        x = scr.right() - self.width() - m if "right" in c else scr.left() + m
        y = scr.top() + m if "top" in c else scr.bottom() - self.height() - m
        self.move(x, y)

    def _tick(self):
        now = time.time()
        self.toasts = [t for t in self.toasts if now - t[0] < 4.0]
        self._raise_counter += 1
        if self.isVisible() and self._raise_counter % 20 == 0:
            self.raise_()  # bleibt ueber randlosen Spielen
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        src = self.ctl.sources
        rec = src.recording is not None
        playing = self.ctl.mixer.playing()
        top_c = "top" in self.ctl.cfg["overlay_corner"]
        right = "right" in self.ctl.cfg["overlay_corner"]

        lines: list[tuple[str, str]] = []
        if rec:
            t = int(src.recording_seconds())
            blink = int(time.time() * 2) % 2 == 0
            lines.append((("● " if blink else "○ ") + f"REC {t // 60}:{t % 60:02d}", RED))
        n_src = src.running_count()
        status = f"Potato Clips · {n_src} Quelle(n) · Clip {self.ctl.cfg['buffer_seconds']}s"
        if self.ctl.cfg["mic_passthrough"]:
            status += " · 🎙"
        lines.append((status, "#c9c9d6"))
        if self.ctl.cfg["voice_enabled"]:
            from ..effects import voice_name
            lines.append((f"🎭 Stimme: {voice_name(self.ctl.cfg['voice_preset'])} · "
                          f"{int(self.ctl.voice_amount() * 100)} %", "#b9a8ff"))
        for v in playing[:3]:
            if v.sound_id != "__preview__":
                lines.append(("▶ " + v.name, ACCENT))
        for _t0, text, kind in self.toasts[-3:]:
            lines.append((text, KIND_COLORS.get(kind, ACCENT)))

        f = QFont("Segoe UI", 9)
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        lh = fm.height() + 8
        maxw = self.width() - 4
        y = 2 if top_c else self.height() - 2 - lh * len(lines)
        for text, col in lines:
            text = fm.elidedText(text, Qt.ElideRight, maxw - 24)
            w = fm.horizontalAdvance(text) + 24
            x = self.width() - 2 - w if right else 2
            r = QRectF(x, y, w, lh - 4)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(15, 16, 22, 215))
            p.drawRoundedRect(r, 8, 8)
            p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(x, y, 4, lh - 4), 2, 2)
            p.setPen(QColor(col) if col != "#c9c9d6" else QColor("#c9c9d6"))
            p.drawText(r.adjusted(14, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
            y += lh
