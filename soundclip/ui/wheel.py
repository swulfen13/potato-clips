"""Sound-Rad: Taste gedrueckt halten -> rundes Menue ueber dem Spiel, Maus in eine Richtung, loslassen = Sound.

Die Richtung kommt aus der rohen Mausbewegung (Raw Input) - das klappt auch in Spielen, die den Mauszeiger
festhalten. Ohne Raw Input wird die Zeigerposition benutzt."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import theme
from .theme import P

MAX_ITEMS = 8
DEAD_ZONE = 40          # so weit (in Pixeln Mausbewegung) muss man in eine Richtung, bevor etwas gewaehlt ist


def wheel_items(ctl) -> list[dict]:
    """Bis zu 8 Sounds: aus dem gewaehlten Ordner, sonst Favoriten zuerst."""
    src = ctl.cfg.get("wheel_source", "fav")
    sounds = list(ctl.sounds.sounds)
    if src not in ("", "fav"):
        sel = [s for s in sounds if s.get("folder", "") == src]
        if sel:
            return sel[:MAX_ITEMS]
    sounds.sort(key=lambda s: not s.get("fav"))
    return sounds[:MAX_ITEMS]


class SoundWheel(QWidget):
    def __init__(self, ctl):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.ctl = ctl
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(480, 480)
        self.items: list[dict] = []
        self.sel = -1
        self._start = QPointF()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        ctl.wheelHold.connect(self.hold)

    # ---- Ablauf
    def hold(self, down: bool):
        if down:
            self.open()
        else:
            self.release()

    def open(self):
        if self.isVisible():                    # Tasten-Wiederholung beim Halten -> nichts tun
            return
        self.items = wheel_items(self.ctl)
        if not self.items:
            import time
            if time.time() - getattr(self, "_warned", 0) > 3:
                self._warned = time.time()
                self.ctl.toast.emit("Sound-Rad: noch keine Sounds im Soundboard", "warn")
            return
        self.sel = -1
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = scr.geometry()
        self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
        self._start = QPointF(QCursor.pos())
        w = self._watcher()
        if w is not None:
            w.track_motion(True)
        self.show()
        self.raise_()
        self.timer.start(16)

    def release(self):
        if not self.isVisible():
            return
        self.timer.stop()
        self._tick()
        w = self._watcher()
        if w is not None:
            w.track_motion(False)
        self.hide()
        if 0 <= self.sel < len(self.items):
            self.ctl.stats.add("wheel")
            self.ctl.play_sound(self.items[self.sel]["id"])

    def _watcher(self):
        try:
            return self.ctl.hotkeys.watcher()
        except Exception:
            return None

    def _tick(self):
        dx = dy = 0.0
        w = self._watcher()
        if w is not None and w.mouse_ok and (w.dx or w.dy):
            dx, dy = float(w.dx), float(w.dy)
        else:
            d = QPointF(QCursor.pos()) - self._start
            dx, dy = d.x(), d.y()
        n = len(self.items)
        sel = -1
        if n and math.hypot(dx, dy) > DEAD_ZONE:
            ang = (math.degrees(math.atan2(dx, -dy)) + 360) % 360          # 0 Grad = oben, im Uhrzeigersinn
            sel = int(((ang + 180 / n) % 360) // (360 / n))
        if sel != self.sel:
            self.sel = sel
            self.update()

    # ---- Zeichnen
    def paintEvent(self, e):
        n = len(self.items)
        if not n:
            return
        pot = theme.potato()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        r_out, r_in = 220.0, 70.0
        span = 360.0 / n
        f = QFont(P.get("font_body", "Inter"))
        f.setPixelSize(15)
        f.setBold(True)
        p.setFont(f)
        for i, s in enumerate(self.items):
            start = 90 - (i * span) + span / 2          # Qt: 0 Grad = rechts, gegen den Uhrzeigersinn
            path = QPainterPath()
            path.moveTo(c)
            path.arcTo(QRectF(c.x() - r_out, c.y() - r_out, 2 * r_out, 2 * r_out), start, -span)
            path.closeSubpath()
            hole = QPainterPath()
            hole.addEllipse(c, r_in, r_in)
            path = path.subtracted(hole)
            on = i == self.sel
            if pot:
                fill = QColor("#FF3D8B") if on else QColor("#FFE94D")
                pen = QPen(QColor("#111"), 3)
            else:
                fill = QColor("#F2A93B") if on else QColor(22, 24, 29, 235)
                pen = QPen(QColor("#2C3038") if not on else QColor("#F2A93B"), 1.5)
            p.setPen(pen)
            p.setBrush(fill)
            p.drawPath(path)
            mid = math.radians(i * span)
            tx = c.x() + math.sin(mid) * (r_in + r_out) / 2
            ty = c.y() - math.cos(mid) * (r_in + r_out) / 2
            p.setPen(QColor("#111") if (pot or on) else QColor(P["text"]))
            name = s["name"] if len(s["name"]) <= 16 else s["name"][:15] + "…"
            p.drawText(QRectF(tx - 70, ty - 24, 140, 48), Qt.AlignCenter | Qt.TextWordWrap,
                       f"{i + 1}\n{name}" if n > 1 else name)
        # Mitte
        p.setBrush(QColor("#111") if pot else QColor(13, 14, 17, 240))
        p.setPen(QPen(QColor("#FFE94D") if pot else QColor("#2C3038"), 3 if pot else 1.5))
        p.drawEllipse(c, r_in - 6, r_in - 6)
        p.setPen(QColor("#FFE94D") if pot else QColor(P["text"]))
        f.setPixelSize(12)
        p.setFont(f)
        from ..i18n import tr
        txt = self.items[self.sel]["name"] if self.sel >= 0 else tr("Richtung zeigen,\nloslassen = Sound")
        p.drawText(QRectF(c.x() - r_in + 10, c.y() - 30, 2 * r_in - 20, 60), Qt.AlignCenter | Qt.TextWordWrap, txt)
        p.end()
