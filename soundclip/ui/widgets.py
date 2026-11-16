"""Wiederverwendbare Widgets + Theme."""
from __future__ import annotations

import numpy as np
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPoint, QRect, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QKeySequence, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QKeySequenceEdit, QLayout, QSizePolicy, QToolButton,
                               QWidget)

from ..hotkeys import combo_to_qt, qt_to_combo

from . import theme
from .theme import P

ACCENT = P["accent"]
ACCENT2 = P["accent_hover"]
RED = P["red"]
GREEN = P["green"]
BG = P["bg"]
SIDEBAR = P["sidebar"]
PANEL = P["panel"]
PANEL2 = P["panel2"]
BORDER = P["border"]
TEXT = P["text"]
MUTED = P["muted"]

ASSETS = (Path(__file__).resolve().parent / "assets").as_posix()


def build_style() -> str:
    """Stylesheet fuer das aktive Design (theme.MODE)."""
    c = dict(P)
    pot = theme.potato()
    bw = 3 if pot else 1                 # Rahmenbreite
    r = 0 if pot else 8                  # Ecken
    rc = 0 if pot else 12                # Ecken grosser Flaechen
    font = "'Comic Neue', 'Comic Sans MS'" if pot else "'Inter', 'Segoe UI Variable Text', 'Segoe UI'"
    head = "'Bungee', 'Comic Neue'" if pot else "'Inter', 'Segoe UI'"
    weight = 700 if pot else 400
    btn_hover = "#3DE8FF" if pot else c["panel_hover"]
    nav_checked = (f"background: {c['accent']}; color: #111; border: 3px solid #111;" if pot else
                   f"background: {c['panel_hover']}; color: {c['text']}; border-left: 2px solid {c['accent']};")
    nav_idle = ("background: #FFFFFF; border: 3px solid #111; color: #111;" if pot else
                f"background: transparent; border: none; border-left: 2px solid transparent; color: {c['muted']};")
    return f"""
* {{ font-family: {font}; font-size: 10pt; font-weight: {weight}; color: {c['text']}; }}
QMainWindow, QDialog {{ background: {c['bg']}; }}
QWidget#page {{ background: {c['bg']}; }}
QWidget#sidebar {{ background: {c['sidebar']}; border-right: {bw}px solid {c['border']}; }}
QPushButton#nav {{ text-align: left; padding: 10px 12px; border-radius: {r}px; {nav_idle}
    font-size: 10.5pt; font-weight: {700 if pot else 500}; }}
QPushButton#nav:hover {{ background: {btn_hover}; color: {c['text']}; }}
QPushButton#nav:checked {{ {nav_checked} font-weight: 700; }}
QFrame#card {{ background: {c['panel']}; border: {bw}px solid {c['border']}; border-radius: {rc}px; }}
QFrame#card:hover {{ border-color: {'#111' if pot else c['border2']}; }}
QFrame#card QLabel {{ background: transparent; }}
QFrame#section {{ background: {c['panel']}; border: {bw}px solid {c['border']}; border-radius: {rc}px; }}
QFrame#section QLabel, QFrame#row QLabel {{ background: transparent; }}
QFrame#row {{ background: transparent; border: none; border-top: {1 if not pot else 2}px solid {c['border']}; }}
QPushButton {{ background: {c['panel2']}; border: {bw}px solid {c['border2']}; border-radius: {r}px; padding: 7px 14px;
    font-weight: {700 if pot else 500}; }}
QPushButton:hover {{ background: {btn_hover}; border-color: {c['accent'] if not pot else '#111'}; }}
QPushButton:pressed {{ background: {c['sel']}; }}
QPushButton:checked {{ background: {c['accent'] if pot else c['panel_hover']}; border-color: {'#111' if pot else c['accent']}; }}
QPushButton:disabled {{ color: {c['muted']}; border-color: {c['border']}; background: {c['panel']}; }}
QPushButton#accent {{ background: {c['accent']}; border: {bw}px solid {'#111' if pot else c['accent']}; color: {c['accent_text']};
    font-weight: 700; }}
QPushButton#accent:hover {{ background: {c['accent_hover']}; }}
QPushButton#danger, QPushButton#rec {{ background: {c['danger_bg']}; border: {bw}px solid {c['danger_border']};
    color: {c['danger_text']}; font-weight: 700; }}
QPushButton#danger:hover, QPushButton#rec:hover {{ border-color: {c['red'] if not pot else '#111'}; }}
QPushButton#rec[recording="true"] {{ background: {c['red']}; border-color: {c['red'] if not pot else '#111'}; color: white; }}
QPushButton#round {{ border-radius: {0 if pot else 16}px; padding: 0; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; }}
QPushButton#addtile {{ border: {2 if not pot else 3}px dashed {c['border2'] if not pot else '#111'}; border-radius: {rc}px;
    background: transparent; color: {c['muted']}; font-weight: 700; }}
QPushButton#addtile:hover {{ border-color: {c['accent'] if not pot else '#111'}; color: {c['text']}; background: {btn_hover}; }}
QPushButton#seg {{ border-radius: {r}px; padding: 6px 12px; }}
QPushButton#seg:checked {{ background: {c['accent'] if pot else c['border2']}; color: {'#111' if pot else c['text']};
    border-color: {'#111' if pot else c['border2']}; font-weight: 700; }}
QPushButton#themecard {{ text-align: left; padding: 12px 14px; border-radius: {rc}px; }}
QPushButton#themecard:checked {{ border: {bw + (2 if pot else 0)}px solid {'#111' if pot else c['accent']};
    background: {c['accent'] if pot else c['accent_soft']}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit, QPlainTextEdit {{
    background: {c['panel2']}; border: {bw}px solid {c['border2']}; border-radius: {r}px; padding: 6px 10px;
    selection-background-color: {c['accent']}; selection-color: {c['accent_text']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QKeySequenceEdit:focus, QPlainTextEdit:focus {{ border-color: {c['accent'] if not pot else '#FF3D8B'}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{ image: url("{ASSETS}/chevron.svg"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {c['panel2']}; border: {bw}px solid {c['border2']}; border-radius: {r}px; padding: 4px;
    selection-background-color: {c['accent']}; selection-color: {c['accent_text']}; outline: none; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; width: 18px; background: transparent; }}
QSpinBox::up-arrow {{ image: url("{ASSETS}/up.svg"); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url("{ASSETS}/down.svg"); width: 10px; height: 10px; }}
QListWidget {{ background: {c['panel']}; border: {bw}px solid {c['border']}; border-radius: {rc}px; outline: none; padding: 4px; }}
QListWidget::item {{ padding: 9px 8px; border-radius: {r}px; margin: 1px 0; }}
QListWidget::item:hover {{ background: {c['panel_hover']}; }}
QListWidget::item:selected {{ background: {c['sel']}; color: {c['text']}; }}
QGroupBox {{ background: {c['panel']}; border: {bw}px solid {c['border']}; border-radius: {rc}px; margin-top: 16px;
    padding: 18px 14px 12px 14px; font-weight: 700; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {c['muted']}; }}
QGroupBox QLabel, QGroupBox QCheckBox, QGroupBox QRadioButton {{ background: transparent; }}
QCheckBox, QRadioButton {{ spacing: 9px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: {0 if pot else 5}px; border: 2px solid {c['border2'] if not pot else '#111'}; background: {c['panel2']}; }}
QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent'] if not pot else '#111'}; image: url("{ASSETS}/check.svg"); }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 9px; border: 2px solid {c['border2'] if not pot else '#111'}; background: {c['panel2']}; }}
QRadioButton::indicator:checked {{ width: 8px; height: 8px; border: 5px solid {c['accent']}; background: white; }}
QSlider::groove:horizontal {{ height: {8 if pot else 4}px; background: {c['groove']}; border-radius: {0 if pot else 2}px;
    border: {2 if pot else 0}px solid #111; }}
QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: {0 if pot else 2}px; border: {2 if pot else 0}px solid #111; }}
QSlider::handle:horizontal {{ background: {'#111' if pot else c['accent']}; width: {18 if pot else 14}px; height: 14px;
    margin: {-6 if pot else -5}px 0; border-radius: {0 if pot else 7}px; border: {2 if pot else 2}px solid {'#111' if pot else c['bg']}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border2'] if not pot else '#111'}; border-radius: {0 if pot else 4}px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border2'] if not pot else '#111'}; border-radius: {0 if pot else 4}px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QToolButton {{ background: {c['panel2']}; border: {bw}px solid {c['border2']}; border-radius: {r}px; padding: 4px 8px; }}
QToolButton:hover {{ border-color: {c['accent'] if not pot else '#111'}; background: {btn_hover}; }}
QLabel#muted {{ color: {c['muted']}; background: transparent; }}
QLabel#h1 {{ font-family: {head}; font-size: {22 if pot else 17}pt; font-weight: 700; background: transparent; }}
QLabel#h2 {{ font-family: {head}; font-size: {13 if pot else 11}pt; font-weight: 700; background: transparent; }}
QLabel#sub {{ color: {c['muted']}; font-size: 9.5pt; background: transparent; }}
QLabel#brand {{ font-family: {head}; font-size: {13 if pot else 13}pt; font-weight: 700; background: transparent; }}
QLabel#chip_ok {{ background: {'#B6FF3B' if pot else '#12201D'}; border: {bw}px solid {'#111' if pot else '#1F3A33'};
    border-radius: {r}px; padding: 7px 10px; color: {c['text']}; }}
QLabel#chip_bad {{ background: {'#FF8A1F' if pot else '#2A1517'}; border: {bw}px solid {'#111' if pot else '#5A2A2E'};
    border-radius: {r}px; padding: 7px 10px; color: {c['text']}; }}
QLabel#kbd {{ font-family: 'Cascadia Mono', Consolas, monospace; background: {c['panel2']}; border: 1px solid {c['border2']};
    border-radius: 4px; padding: 1px 6px; }}
QFrame#hintbox {{ background: {c['hint_bg']}; border: {bw}px solid {c['hint_border']}; border-radius: {r + 2}px; }}
QFrame#hintbox QLabel {{ background: transparent; color: {c['hint_text']}; }}
QLabel#intruder {{ background: {c['danger_bg']}; border: {bw}px solid {c['danger_border'] if not pot else '#111'};
    border-radius: {r + 2}px; padding: 8px 12px; color: {c['danger_text']}; }}
QSplitter::handle {{ background: transparent; }}
QMenu {{ background: {c['panel2']}; border: {bw}px solid {c['border2']}; border-radius: {r + 2}px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px; border-radius: {r}px; }}
QMenu::item:selected {{ background: {c['accent']}; color: {c['accent_text']}; }}
QMenu::separator {{ height: 1px; background: {c['border2']}; margin: 4px 8px; }}
QToolTip {{ background: {c['panel2']}; color: {c['text']}; border: 1px solid {c['border2']}; padding: 6px; border-radius: 6px; }}
QMessageBox, QInputDialog {{ background: {c['bg']}; }}
"""


STYLE = build_style()


class ToggleSwitch(QCheckBox):
    """Moderner An/Aus-Schalter (verhaelt sich wie eine QCheckBox)."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._pos = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self._animate)
        self.setCursor(Qt.PointingHandCursor)

    def setChecked(self, on):  # ohne Animation
        if bool(on) == self.isChecked() and self._anim.state() != QVariantAnimation.Stopped:
            return
        super().setChecked(on)
        self._anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def _set_pos(self, v):
        self._pos = float(v)
        self.update()

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def sizeHint(self):
        fm = self.fontMetrics()
        w = 42 + (10 + fm.horizontalAdvance(self.text()) if self.text() else 0)
        return QSize(w, max(24, fm.height() + 4))

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = 22
        y = (self.height() - h) / 2
        track = QRectF(1.5, y, 40, h)
        pot = theme.potato()
        off = QColor(P["toggle_off"])
        on = QColor(P["accent"] if not pot else "#B6FF3B")
        if not self.isEnabled():
            off, on = QColor(P["panel"]), QColor(P["border2"])
        c = QColor(int(off.red() + (on.red() - off.red()) * self._pos),
                   int(off.green() + (on.green() - off.green()) * self._pos),
                   int(off.blue() + (on.blue() - off.blue()) * self._pos))
        p.setBrush(c)
        r = h - 6
        x = track.left() + 3 + (track.width() - r - 6) * self._pos
        if pot:
            p.setPen(QPen(QColor("#111"), 2.5))
            p.drawRect(track)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#111"))
            p.drawRect(QRectF(x, y + 3, r, r))
        else:
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(track, h / 2, h / 2)
            p.setBrush(QColor(P["accent_text"]) if self._pos > 0.5 else QColor("#E8EAED"))
            if not self.isEnabled():
                p.setBrush(QColor(P["muted"]))
            p.drawEllipse(QRectF(x, y + 3, r, r))
        if self.text():
            p.setPen(QColor(TEXT) if self.isEnabled() else QColor(MUTED))
            p.drawText(QRectF(52, 0, self.width() - 52, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())


def hard_shadow(w, dist: int = 6):
    """Potato-Modus: harter schwarzer Schatten (wie gedruckt)."""
    if not theme.potato():
        return w
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(0)
    eff.setOffset(dist, dist)
    eff.setColor(QColor("#111111"))
    w.setGraphicsEffect(eff)
    return w


def card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("card")
    hard_shadow(f)
    return f


def brand_pixmap(size: int) -> QPixmap:
    """Logo im Design: Profi = Kartoffel auf Gold, Potato = Kartoffel mit Glubschaugen."""
    if not theme.potato():
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        s = float(size)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(P["accent"]))
        p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.25, s * 0.25)
        path = QPainterPath()
        path.addEllipse(QRectF(s * 0.24, s * 0.28, s * 0.54, s * 0.44))
        p.save()
        p.translate(s / 2, s / 2)
        p.rotate(-25)
        p.translate(-s / 2, -s / 2)
        p.setBrush(QColor(P["accent_text"]))
        p.drawPath(path)
        p.setBrush(QColor(P["accent"]))
        for ex, ey, rr in ((0.42, 0.45, 0.035), (0.58, 0.52, 0.035), (0.48, 0.6, 0.028)):
            p.drawEllipse(QRectF(s * (ex - rr), s * (ey - rr), s * rr * 2, s * rr * 2))
        p.restore()
        p.end()
        return pm
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    k = size / 64.0
    p.scale(k, k)
    body = QPainterPath()
    body.moveTo(10, 36)
    body.cubicTo(10, 22, 19, 10, 33, 10)
    body.cubicTo(46, 10, 54, 19, 54, 30)
    body.cubicTo(54, 45, 44, 56, 29, 56)
    body.cubicTo(17, 56, 10, 48, 10, 36)
    p.setPen(QPen(QColor("#111"), 3))
    p.setBrush(QColor("#D9A15B"))
    p.drawPath(body)
    p.setPen(QPen(QColor("#111"), 2.5))
    p.setBrush(QColor("white"))
    p.drawEllipse(QRectF(19, 23, 14, 14))
    p.drawEllipse(QRectF(37, 23, 10, 10))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#111"))
    p.drawEllipse(QRectF(25, 29, 6, 6))
    p.drawEllipse(QRectF(39, 25, 4, 4))
    p.setPen(QPen(QColor("#111"), 3, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    mouth = QPainterPath()
    mouth.moveTo(27, 44)
    mouth.cubicTo(31, 48, 37, 48, 41, 43)
    p.drawPath(mouth)
    p.end()
    return pm


def save_icon_file(path) -> None:
    """Mehrgroessen-ICO (fuer Verknuepfungen und den Helfer)."""
    try:
        from PIL import Image
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        import io
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        _potato_pixmap(256).save(buf, "PNG")
        img = Image.open(io.BytesIO(bytes(ba))).convert("RGBA")
        img.save(str(path), format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                                                  (256, 256)])
    except Exception:
        try:
            _potato_pixmap(256).save(str(path), "ICO")
        except Exception:
            pass


def _potato_pixmap(size: int) -> QPixmap:
    """Kartoffel mit Schallwellen auf violettem Grund – das Potato-Clips-Logo."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = float(size)
    bg = QLinearGradient(0, 0, s, s)
    bg.setColorAt(0, QColor("#8f74ff"))
    bg.setColorAt(1, QColor("#ff5c8a"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(bg))
    p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.24, s * 0.24)
    # Kartoffel: ovale, leicht unregelmaessige Knolle, schraeg gelegt (glatte Catmull-Rom-Kurve)
    import math
    cx, cy = s * 0.42, s * 0.53
    rx, ry, rot = s * 0.30, s * 0.21, math.radians(-28)
    wobble = [1.00, 1.04, 0.97, 1.03, 0.95, 1.02, 0.98, 1.05, 0.96, 1.01, 0.99, 1.03]
    pts = []
    for i, w in enumerate(wobble):
        a_ = 2 * math.pi * i / len(wobble)
        x, y = rx * w * math.cos(a_), ry * w * math.sin(a_)
        pts.append((cx + x * math.cos(rot) - y * math.sin(rot), cy + x * math.sin(rot) + y * math.cos(rot)))
    path = QPainterPath()
    n = len(pts)
    path.moveTo(*pts[0])
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        path.cubicTo(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])
    path.closeSubpath()
    g = QRadialGradient(cx - s * 0.08, cy - s * 0.1, s * 0.38)
    g.setColorAt(0, QColor("#f0c27a"))
    g.setColorAt(0.6, QColor("#d39a52"))
    g.setColorAt(1, QColor("#9c6a33"))
    p.setBrush(QBrush(g))
    p.setPen(QPen(QColor("#6e4520"), max(1.0, s * 0.025)))
    p.drawPath(path)
    # "Augen" der Kartoffel
    if size >= 24:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(110, 69, 32, 200))
        for ex, ey, r in ((-0.14, 0.02, 0.024), (0.04, -0.07, 0.022), (0.13, -0.13, 0.018), (-0.02, 0.09, 0.018)):
            p.drawEllipse(QRectF(cx + ex * s - r * s, cy + ey * s - r * s, 2 * r * s, 2 * r * s))
    # Schallwellen rechts
    pen = QPen(QColor("white"), max(1.4, s * 0.06), Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    for i, rr in enumerate((0.16, 0.27)):
        r = rr * s
        rect = QRectF(s * 0.66 - r, s * 0.47 - r, 2 * r, 2 * r)
        p.drawArc(rect, -40 * 16, 80 * 16)
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_potato_pixmap(size))
    return icon


class LevelMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0
        self.setMinimumSize(80, 10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(16 if theme.potato() else 10)

    def push(self, peak: float):
        # dB-Skala, damit leise Stimmen sichtbar sind
        db = 20 * np.log10(max(peak, 1e-5))
        v = float(np.clip((db + 60) / 60, 0, 1))
        self.level = max(v, self.level * 0.82)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if theme.potato():
            n = 14
            gap = 3.0
            bw = (r.width() - gap * (n - 1)) / n
            lit = int(round(self.level * n))
            for i in range(n):
                cell = QRectF(r.left() + i * (bw + gap), r.top(), bw, r.height())
                col = "#B6FF3B" if i < n * 0.6 else ("#FF8A1F" if i < n * 0.85 else "#FF3D8B")
                p.setPen(QPen(QColor("#111"), 1.5))
                p.setBrush(QColor(col) if i < lit else QColor("white"))
                p.drawRect(cell)
            return
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(P["meter_bg"]))
        p.drawRoundedRect(r, 4, 4)
        if self.level > 0.01:
            w = r.width() * self.level
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            g.setColorAt(0, QColor(GREEN))
            g.setColorAt(0.75, QColor(P["warn"]))
            g.setColorAt(1, QColor(RED))
            p.setBrush(QBrush(g))
            p.drawRoundedRect(QRectF(r.left(), r.top(), w, r.height()), 4, 4)


class WaveformView(QWidget):
    """Wellenform mit verschiebbaren Start-/End-Markern."""
    rangeChanged = Signal(float, float)
    seekRequested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.peaks = np.zeros(0)
        self.duration = 0.0
        self.start = 0.0
        self.end = 0.0
        self.playhead = -1.0
        self._drag = None
        self.setMinimumHeight(130)
        self.setMouseTracking(True)

    def set_audio(self, data: np.ndarray, duration: float):
        self.duration = max(duration, 0.0)
        if data is None or not len(data):
            self.peaks = np.zeros(0)
        else:
            mono = np.abs(data).max(axis=1)
            bins = 1200
            n = len(mono)
            if n < bins:
                self.peaks = mono
            else:
                cut = n - n % bins
                self.peaks = mono[:cut].reshape(bins, -1).max(axis=1)
        self.update()

    def set_range(self, start: float, end: float):
        self.start, self.end = start, end
        self.update()

    def _x(self, t):
        return 8 + (self.width() - 16) * (t / self.duration if self.duration else 0)

    def _t(self, x):
        if not self.duration:
            return 0.0
        return float(np.clip((x - 8) / max(1, self.width() - 16) * self.duration, 0, self.duration))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        from ..i18n import tr
        if theme.potato():
            p.setPen(QPen(QColor("#111"), 3))
            p.setBrush(QColor("white"))
            p.drawRect(QRectF(r).adjusted(1.5, 1.5, -1.5, -1.5))
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(PANEL))
            p.drawRoundedRect(QRectF(r), 10, 10)
        if not len(self.peaks) or not self.duration:
            p.setPen(QColor(MUTED))
            p.drawText(r, Qt.AlignCenter, tr("Kein Audio ausgewählt"))
            return
        mid = r.height() / 2
        h = r.height() / 2 - 12
        n = len(self.peaks)
        mx = max(float(self.peaks.max()), 1e-4)
        w = r.width() - 16
        sx, ex = self._x(self.start), self._x(self.end)
        # Bereich ausserhalb abdunkeln
        p.setBrush(QColor(0, 0, 0, 0))
        for i in range(0, int(w)):
            k = int(i / w * n)
            v = self.peaks[min(k, n - 1)] / mx
            x = 8 + i
            inside = sx <= x <= ex
            p.setPen(QColor(ACCENT) if inside else QColor(P["wave_off"]))
            p.drawLine(int(x), int(mid - v * h), int(x), int(mid + v * h))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 40 if theme.potato() else 90))
        p.drawRect(QRectF(8, 0, max(0, sx - 8), r.height()))
        p.drawRect(QRectF(ex, 0, max(0, r.width() - 8 - ex), r.height()))
        for x, col in ((sx, GREEN), (ex, RED)):
            p.setPen(QPen(QColor(col), 2))
            p.drawLine(int(x), 4, int(x), r.height() - 4)
            p.setBrush(QColor(col))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x - 5, 2, 10, 14), 3, 3)
        if self.playhead >= 0:
            x = self._x(self.start + self.playhead)
            p.setPen(QPen(QColor(P["text"]), 1.5))
            p.drawLine(int(x), 0, int(x), r.height())
        p.setPen(QColor(MUTED))
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.drawText(QRect(12, r.height() - 18, 200, 16), Qt.AlignLeft, f"{self.start:.2f}s")
        p.drawText(QRect(r.width() - 212, r.height() - 18, 200, 16), Qt.AlignRight, f"{self.end:.2f}s")
        p.drawText(QRect(0, r.height() - 18, r.width(), 16), Qt.AlignCenter,
                   tr("Auswahl: {a}s von {b}s").format(a=f"{max(0, self.end - self.start):.2f}",
                                                       b=f"{self.duration:.1f}"))

    def mousePressEvent(self, e):
        if not self.duration:
            return
        x = e.position().x()
        sx, ex = self._x(self.start), self._x(self.end)
        if abs(x - sx) < 10:
            self._drag = "s"
        elif abs(x - ex) < 10:
            self._drag = "e"
        elif e.button() == Qt.RightButton:
            self._drag = "e"
            self._move(x)
        else:
            self._drag = "s"
            self._move(x)

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag:
            self._move(x)
        else:
            sx, ex = self._x(self.start), self._x(self.end)
            near = abs(x - sx) < 10 or abs(x - ex) < 10
            self.setCursor(Qt.SizeHorCursor if near else Qt.ArrowCursor)

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = None
            self.rangeChanged.emit(self.start, self.end)

    def _move(self, x):
        t = self._t(x)
        if self._drag == "s":
            self.start = min(t, self.end - 0.02)
        else:
            self.end = max(t, self.start + 0.02)
        self.update()


class HotkeyEdit(QWidget):
    """Feld zum Aufnehmen eines Tastenkuerzels (speichert im keyboard-Format, z. B. 'ctrl+alt+1')."""
    changed = Signal(str)

    def __init__(self, combo: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.edit = QKeySequenceEdit()
        try:
            self.edit.setMaximumSequenceLength(1)
        except Exception:
            pass
        self.edit.setToolTip("Hier klicken und Tastenkombination drücken")
        from PySide6.QtWidgets import QLineEdit
        le = self.edit.findChild(QLineEdit)
        if le is not None:
            le.setPlaceholderText("Klicken und Tasten drücken…")
        self.clear_btn = QToolButton()
        self.clear_btn.setText("✕")
        self.clear_btn.setToolTip("Hotkey entfernen")
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.clear_btn)
        self.set_combo(combo)
        self.edit.editingFinished.connect(self._emit)
        self.clear_btn.clicked.connect(lambda: (self.edit.clear(), self._emit()))

    def set_combo(self, combo: str):
        self.edit.blockSignals(True)
        self.edit.setKeySequence(QKeySequence(combo_to_qt(combo)))
        self.edit.blockSignals(False)

    def combo(self) -> str:
        return qt_to_combo(self.edit.keySequence().toString(QKeySequence.PortableText))

    def _emit(self):
        self.changed.emit(self.combo())


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing=10):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._layout(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s + QSize(2, 2)

    def _layout(self, rect, test):
        x, y, line_h = rect.x(), rect.y(), 0
        sp = self._spacing
        for it in self._items:
            hint = it.sizeHint()
            nx = x + hint.width() + sp
            if nx - sp > rect.right() and line_h > 0:
                x = rect.x()
                y += line_h + sp
                nx = x + hint.width() + sp
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()
