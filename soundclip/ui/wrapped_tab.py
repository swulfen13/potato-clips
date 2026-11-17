"""Potato Wrapped: deine Statistik als Bild zum Teilen."""
from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from . import theme
from ..i18n import tr

W, H = 1080, 1920


def render_wrapped(s: dict, pot: bool) -> QImage:
    from ..effects import voice_name
    from ..stats import title_for
    img = QImage(W, H, QImage.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    if pot:
        bg, card, text, muted, acc, acc2 = (QColor("#FFE94D"), QColor("#FFFFFF"), QColor("#111"), QColor("#333"),
                                            QColor("#FF3D8B"), QColor("#3DE8FF"))
        p.fillRect(0, 0, W, H, bg)
        hfont, bfont = "Bungee", "Comic Neue"
    else:
        bg, card, text, muted, acc, acc2 = (QColor("#0D0E11"), QColor("#16181D"), QColor("#E9EAEE"), QColor("#8B909C"),
                                            QColor("#F2A93B"), QColor("#FFD08A"))
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0, QColor("#1A1C22"))
        g.setColorAt(1, QColor("#0B0C0F"))
        p.fillRect(0, 0, W, H, g)
        hfont, bfont = "Inter", "Inter"

    def font(size, bold=True, head=False):
        f = QFont(hfont if head else bfont)
        f.setPixelSize(size)
        f.setBold(bold)
        return f

    def box(r: QRectF, fill=None):
        if pot:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#111"))
            p.drawRect(r.translated(10, 10))
            p.setPen(QPen(QColor("#111"), 5))
            p.setBrush(fill or card)
            p.drawRect(r)
        else:
            p.setPen(QPen(QColor("#262A32"), 2))
            p.setBrush(fill or card)
            p.drawRoundedRect(r, 28, 28)

    m = 70
    # Kopf
    p.setPen(acc if not pot else text)
    p.setFont(font(44, head=True))
    p.drawText(QRectF(m, 70, W - 2 * m, 60), Qt.AlignLeft | Qt.AlignVCenter, "POTATO WRAPPED")
    p.setPen(muted)
    p.setFont(font(30, bold=False))
    try:
        since = _dt.date.fromisoformat(s["since"]).strftime("%d.%m.%Y")
    except Exception:
        since = s.get("since", "")
    p.drawText(QRectF(m, 130, W - 2 * m, 44), Qt.AlignLeft | Qt.AlignVCenter, tr("seit ") + since)
    # Titel
    title, sub = title_for(s)
    r = QRectF(m, 210, W - 2 * m, 300)
    box(r, acc if pot else None)
    p.setPen(text if pot else acc)
    p.setFont(font(36, bold=False))
    p.drawText(r.adjusted(40, 30, -40, 0), Qt.AlignLeft | Qt.AlignTop, tr("Du bist ein:"))
    p.setPen(text)
    p.setFont(font(76 if len(tr(title)) < 18 else 60, head=True))
    p.drawText(r.adjusted(40, 80, -40, -80), Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, tr(title))
    p.setFont(font(32, bold=False))
    p.setPen(text if pot else muted)
    p.drawText(r.adjusted(40, 0, -40, -30), Qt.AlignLeft | Qt.AlignBottom, tr(sub))
    # Grosse Zahl
    y = 560
    p.setPen(acc if not pot else QColor("#111"))
    p.setFont(font(170, head=True))
    p.drawText(QRectF(m, y, W - 2 * m, 190), Qt.AlignLeft | Qt.AlignVCenter, f"{s['plays']:,}".replace(",", "."))
    p.setPen(text)
    p.setFont(font(40))
    p.drawText(QRectF(m, y + 180, W - 2 * m, 56), Qt.AlignLeft | Qt.AlignVCenter, tr("Sounds abgespielt"))
    # Top 5
    y = 820
    r = QRectF(m, y, W - 2 * m, 470)
    box(r)
    p.setPen(muted if not pot else text)
    p.setFont(font(30))
    p.drawText(r.adjusted(40, 26, -40, 0), Qt.AlignLeft | Qt.AlignTop, tr("Deine Top-Sounds"))
    top = s["top"] or [(tr("noch keine"), 0)]
    mx = max((c for _, c in top), default=1) or 1
    for i, (name, cnt) in enumerate(top[:5]):
        yy = y + 86 + i * 72
        p.setPen(acc if not pot else QColor("#111"))
        p.setFont(font(34, head=True))
        p.drawText(QRectF(m + 40, yy, 60, 60), Qt.AlignLeft | Qt.AlignVCenter, f"{i + 1}")
        bar_w = (W - 2 * m - 320) * (cnt / mx if mx else 0)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(acc.red(), acc.green(), acc.blue(), 70 if not pot else 255))
        if cnt:
            p.drawRect(QRectF(m + 110, yy + 8, max(8, bar_w), 44)) if pot else \
                p.drawRoundedRect(QRectF(m + 110, yy + 8, max(8, bar_w), 44), 10, 10)
        p.setPen(text)
        p.setFont(font(32))
        nm = name if len(name) <= 24 else name[:23] + "…"
        p.drawText(QRectF(m + 128, yy, W - 2 * m - 330, 60), Qt.AlignLeft | Qt.AlignVCenter, nm)
        p.setPen(muted if not pot else text)
        p.drawText(QRectF(W - m - 200, yy, 160, 60), Qt.AlignRight | Qt.AlignVCenter, f"{cnt}×" if cnt else "")
    # Kacheln
    tiles = [
        (tr("Clips"), str(s["clips"] + s["autoclips"]),
         tr("davon {n} automatisch").format(n=s["autoclips"]) if s["autoclips"] else tr("gespeichert")),
        (tr("Aufnahmen"), str(s["recordings"]), tr("{n} Minuten").format(n=s["rec_minutes"])),
        (tr("Lieblings-Stimme"), tr(voice_name(s["voice_top"])) if s["voice_top"] else "–",
         tr("{n} Minuten verstellt").format(n=s["voice_minutes"])),
        (tr("Sprachbefehle"), str(s["voice_cmds"] + s["triggers"]), tr("mit Potato geredet")),
        (tr("Vorgelesen"), str(s["tts"]), tr("Texte")),
        (tr("Sound-Rad & Handy"), str(s["wheel"] + s["remote"]), tr("ohne Tastatur gespielt")),
    ]
    tw, th, gap = (W - 2 * m - 30) / 2, 150, 30
    for i, (lab, val, sub) in enumerate(tiles):
        cx = m + (i % 2) * (tw + gap)
        cy = 1316 + (i // 2) * (th + 20)
        rr = QRectF(cx, cy, tw, th)
        box(rr, acc2 if (pot and i % 3 == 0) else None)
        p.setPen(muted if not pot else text)
        p.setFont(font(26))
        p.drawText(rr.adjusted(28, 18, -20, 0), Qt.AlignLeft | Qt.AlignTop, lab)
        p.setPen(text)
        p.setFont(font(50 if len(val) < 12 else 32, head=True))
        p.drawText(rr.adjusted(28, 48, -20, -40), Qt.AlignLeft | Qt.AlignVCenter, val)
        p.setPen(muted if not pot else text)
        p.setFont(font(24, bold=False))
        p.drawText(rr.adjusted(28, 0, -20, -16), Qt.AlignLeft | Qt.AlignBottom, sub)
    # Fuss
    p.setPen(muted if not pot else text)
    p.setFont(font(28))
    p.drawText(QRectF(0, H - 100, W, 50), Qt.AlignCenter, "🥔 Potato Clips")
    p.end()
    return img


class WrappedTab(QWidget):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("page")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 20)
        head = QHBoxLayout()
        h = QLabel("Potato Wrapped")
        h.setObjectName("h1")
        head.addWidget(h)
        head.addStretch(1)
        b_share = QPushButton("📸 Bild speichern && kopieren")
        b_share.setObjectName("accent")
        b_share.clicked.connect(self._share)
        b_reset = QPushButton("Zurücksetzen")
        b_reset.clicked.connect(self._reset)
        head.addWidget(b_share)
        head.addWidget(b_reset)
        root.addLayout(head)
        sub = QLabel("Deine Statistik – alles bleibt auf deinem PC. Teil das Bild in Discord oder als Story.")
        sub.setObjectName("muted")
        root.addWidget(sub)
        self.view = QLabel()
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        root.addWidget(self.view, 1)
        self._img = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)

    def image(self) -> QImage:
        return render_wrapped(self.ctl.stats.summary(self.ctl.sounds), theme.potato())

    def refresh(self):
        self._img = self.image()
        self._fit()

    def _fit(self):
        if self._img is None:
            return
        pm = QPixmap.fromImage(self._img).scaled(self.view.size() * self.devicePixelRatioF(), Qt.KeepAspectRatio,
                                                 Qt.SmoothTransformation)
        pm.setDevicePixelRatio(self.devicePixelRatioF())
        self.view.setPixmap(pm)

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()
        self.timer.start(10000)

    def hideEvent(self, e):
        super().hideEvent(e)
        self.timer.stop()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def _share(self):
        from PySide6.QtWidgets import QApplication
        from ..config import EXPORT_DIR
        img = self.image()
        path = EXPORT_DIR / f"Potato_Wrapped_{_dt.datetime.now().strftime('%Y%m%d_%H%M')}.png"
        img.save(str(path))
        QApplication.clipboard().setImage(img)
        self.ctl.toast.emit("📸 Wrapped kopiert – in Discord mit Strg+V einfügen", "ok")

    def _reset(self):
        r = QMessageBox.question(self, tr("Zurücksetzen"), tr("Statistik wirklich auf null setzen?"))
        if r == QMessageBox.Yes:
            self.ctl.stats.reset()
            self.refresh()
