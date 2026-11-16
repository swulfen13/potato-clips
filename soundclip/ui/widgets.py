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

ACCENT = "#7c5cff"
ACCENT2 = "#ff5c8a"
RED = "#ff4d6d"
GREEN = "#2ec4b6"
BG = "#0f1015"
SIDEBAR = "#14151c"
PANEL = "#181a22"
PANEL2 = "#20232d"
BORDER = "#272a36"
TEXT = "#ececf3"
MUTED = "#8b8fa3"

ASSETS = (Path(__file__).resolve().parent / "assets").as_posix()

STYLE = f"""
* {{ font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#page {{ background: {BG}; }}
QWidget#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QPushButton#nav {{ text-align: left; padding: 11px 14px; border: none; border-radius: 10px; background: transparent;
    color: {MUTED}; font-size: 10.5pt; font-weight: 600; }}
QPushButton#nav:hover {{ background: #1d1f29; color: {TEXT}; }}
QPushButton#nav:checked {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3a2f7a, stop:1 #2a2550);
    color: white; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame#card:hover {{ border-color: #363a4b; }}
QFrame#card QLabel {{ background: transparent; }}
QPushButton {{ background: {PANEL2}; border: 1px solid #2f3340; border-radius: 9px; padding: 8px 15px; font-weight: 500; }}
QPushButton:hover {{ background: #2a2e3c; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: #323648; }}
QPushButton:disabled {{ color: #5a5e6e; border-color: #23252e; background: #1a1c23; }}
QPushButton#accent {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8b6cff, stop:1 #6a4cf0);
    border: none; color: white; font-weight: 600; }}
QPushButton#accent:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #9a7fff, stop:1 #7a5cff); }}
QPushButton#danger {{ background: #2c1820; border-color: #5a2433; color: #ffc2cf; }}
QPushButton#danger:hover {{ border-color: {RED}; }}
QPushButton#rec {{ background: #2c1820; border-color: #5a2433; color: #ffc2cf; font-weight: 600; }}
QPushButton#rec:hover {{ border-color: {RED}; }}
QPushButton#rec[recording="true"] {{ background: {RED}; border-color: {RED}; color: white; }}
QPushButton#round {{ border-radius: 16px; padding: 0; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit, QPlainTextEdit {{
    background: {PANEL2}; border: 1px solid #2f3340; border-radius: 8px; padding: 6px 10px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QKeySequenceEdit:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{ image: url("{ASSETS}/chevron.svg"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {PANEL2}; border: 1px solid #2f3340; border-radius: 8px; padding: 4px;
    selection-background-color: {ACCENT}; outline: none; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; width: 18px; background: transparent; }}
QSpinBox::up-arrow {{ image: url("{ASSETS}/up.svg"); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url("{ASSETS}/down.svg"); width: 10px; height: 10px; }}
QListWidget {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; outline: none; padding: 4px; }}
QListWidget::item {{ padding: 9px 8px; border-radius: 8px; margin: 1px 0; }}
QListWidget::item:hover {{ background: #1f2129; }}
QListWidget::item:selected {{ background: #2e2858; color: white; }}
QGroupBox {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 14px; margin-top: 16px;
    padding: 18px 14px 12px 14px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {MUTED}; }}
QGroupBox QLabel, QGroupBox QCheckBox, QGroupBox QRadioButton {{ font-weight: 400; background: transparent; }}
QCheckBox, QRadioButton {{ spacing: 9px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 2px solid #4a4f63; background: {PANEL2}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url("{ASSETS}/check.svg"); }}
QCheckBox::indicator:disabled {{ border-color: #2f3340; background: #1a1c22; }}
QCheckBox::indicator:checked:disabled {{ background: #3f3577; border-color: #3f3577; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 9px; border: 2px solid #4a4f63; background: {PANEL2}; }}
QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QRadioButton::indicator:checked {{ width: 8px; height: 8px; border: 5px solid {ACCENT}; background: white; }}
QSlider::groove:horizontal {{ height: 5px; background: #2b2f3c; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6a4cf0, stop:1 #9a7fff);
    border-radius: 2px; }}
QSlider::handle:horizontal {{ background: white; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
    border: 3px solid {ACCENT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #333748; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #454a5e; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #333748; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QToolButton {{ background: {PANEL2}; border: 1px solid #2f3340; border-radius: 7px; padding: 4px 8px; }}
QToolButton:hover {{ border-color: {ACCENT}; }}
QLabel#muted {{ color: {MUTED}; background: transparent; }}
QLabel#h1 {{ font-size: 17pt; font-weight: 700; background: transparent; }}
QLabel#h2 {{ font-size: 11pt; font-weight: 600; background: transparent; }}
QLabel#sub {{ color: {MUTED}; font-size: 9.5pt; background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QMenu {{ background: {PANEL2}; border: 1px solid #2f3340; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; }}
QMenu::separator {{ height: 1px; background: #2f3340; margin: 4px 8px; }}
QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid #2f3340; padding: 6px; border-radius: 6px; }}
QMessageBox, QInputDialog {{ background: {BG}; }}
"""


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
        track = QRectF(1, y, 40, h)
        off = QColor("#2f3342")
        on = QColor(ACCENT)
        if not self.isEnabled():
            off, on = QColor("#23252e"), QColor("#3f3577")
        c = QColor(int(off.red() + (on.red() - off.red()) * self._pos),
                   int(off.green() + (on.green() - off.green()) * self._pos),
                   int(off.blue() + (on.blue() - off.blue()) * self._pos))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(track, h / 2, h / 2)
        r = h - 6
        x = track.left() + 3 + (track.width() - r - 6) * self._pos
        p.setBrush(QColor("white") if self.isEnabled() else QColor("#8b8fa3"))
        p.drawEllipse(QRectF(x, y + 3, r, r))
        if self.text():
            p.setPen(QColor(TEXT) if self.isEnabled() else QColor(MUTED))
            p.drawText(QRectF(52, 0, self.width() - 52, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())


def card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("card")
    return f


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
        self.setFixedHeight(10)

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
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2a2d38"))
        p.drawRoundedRect(r, 4, 4)
        if self.level > 0.01:
            w = r.width() * self.level
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            g.setColorAt(0, QColor(GREEN))
            g.setColorAt(0.75, QColor("#ffd166"))
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
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(PANEL))
        p.drawRoundedRect(QRectF(r), 10, 10)
        if not len(self.peaks) or not self.duration:
            p.setPen(QColor(MUTED))
            p.drawText(r, Qt.AlignCenter, "Kein Audio ausgewählt")
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
            p.setPen(QColor(ACCENT) if inside else QColor("#3a3d4c"))
            p.drawLine(int(x), int(mid - v * h), int(x), int(mid + v * h))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
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
            p.setPen(QPen(QColor("white"), 1.5))
            p.drawLine(int(x), 0, int(x), r.height())
        p.setPen(QColor(MUTED))
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.drawText(QRect(12, r.height() - 18, 200, 16), Qt.AlignLeft, f"{self.start:.2f}s")
        p.drawText(QRect(r.width() - 212, r.height() - 18, 200, 16), Qt.AlignRight, f"{self.end:.2f}s")
        p.drawText(QRect(0, r.height() - 18, r.width(), 16), Qt.AlignCenter,
                   f"Auswahl: {max(0, self.end - self.start):.2f}s von {self.duration:.1f}s")

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
