from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from ..hotkeys import pretty
from ..library import AUDIO_EXT
from .widgets import ACCENT, MUTED, FlowLayout, HotkeyEdit, ToggleSwitch, card


class SoundTile(QFrame):
    clicked = Signal(str)
    menuRequested = Signal(str, object)

    def __init__(self, sound: dict):
        super().__init__()
        self.sound = sound
        self.progress = -1.0
        self.setFixedSize(184, 100)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{sound['name']}\nLinksklick: abspielen · Rechtsklick: Optionen")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.sound["id"])

    def contextMenuEvent(self, e):
        self.menuRequested.emit(self.sound["id"], e.globalPos())

    def set_progress(self, v: float):
        if abs(v - self.progress) > 0.005:
            self.progress = v
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        col = QColor(self.sound.get("color", ACCENT))
        hover = getattr(self, "_hover", False)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        top = QColor(col)
        top.setAlpha(95 if hover else 70)
        g.setColorAt(0, top)
        g.setColorAt(1, QColor("#1b1d26"))
        p.setPen(QPen(QColor(col) if hover else QColor("#2c2f3d"), 1.5))
        p.setBrush(QColor("#1b1d26"))
        p.drawRoundedRect(r, 14, 14)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, 14, 14)
        if self.progress >= 0:
            fill = QColor(col)
            fill.setAlpha(110)
            p.setBrush(fill)
            p.save()
            path = QPainterPath()
            path.addRoundedRect(r, 14, 14)
            p.setClipPath(path)
            p.drawRect(QRectF(r.left(), r.bottom() - 5, r.width() * min(1.0, self.progress), 5))
            p.restore()
            p.setPen(QPen(col, 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r, 14, 14)
        # Play-Kreis
        c = QRectF(r.right() - 36, r.top() + 10, 26, 26)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 40 if not hover else 70))
        p.drawEllipse(c)
        p.setBrush(QColor("white"))
        tri = QPainterPath()
        if self.progress >= 0:
            p.drawRect(QRectF(c.center().x() - 5, c.center().y() - 5, 10, 10))
        else:
            tri.moveTo(c.center().x() - 3.5, c.center().y() - 6)
            tri.lineTo(c.center().x() + 6.5, c.center().y())
            tri.lineTo(c.center().x() - 3.5, c.center().y() + 6)
            tri.closeSubpath()
            p.drawPath(tri)
        p.setPen(QColor("white"))
        f = QFont(self.font())
        f.setPointSizeF(10.5)
        f.setBold(True)
        p.setFont(f)
        p.drawText(r.adjusted(14, 12, -44, -30), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.sound["name"])
        hk = pretty(self.sound.get("hotkey", ""))
        f.setBold(False)
        f.setPointSizeF(8.5)
        p.setFont(f)
        if hk:
            fm = p.fontMetrics()
            w = fm.horizontalAdvance(hk) + 14
            pill = QRectF(r.left() + 12, r.bottom() - 28, w, 20)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 90))
            p.drawRoundedRect(pill, 6, 6)
            p.setPen(QColor("#d9d9e6"))
            p.drawText(pill, Qt.AlignCenter, hk)
        else:
            p.setPen(QColor(MUTED))
            p.drawText(r.adjusted(14, 0, -10, -11), Qt.AlignLeft | Qt.AlignBottom, "kein Hotkey")
        vol = float(self.sound.get("volume", 1.0))
        if abs(vol - 1.0) > 0.01:
            p.setPen(QColor(MUTED))
            p.drawText(r.adjusted(14, 0, -12, -11), Qt.AlignRight | Qt.AlignBottom, f"{int(vol * 100)}%")


class SoundDialog(QDialog):
    def __init__(self, sound: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sound bearbeiten")
        self.setMinimumWidth(420)
        lay = QFormLayout(self)
        self.name = QLineEdit(sound["name"])
        self.hotkey = HotkeyEdit(sound.get("hotkey", ""))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 200)
        self.vol.setValue(int(float(sound.get("volume", 1.0)) * 100))
        self.vol_lbl = QLabel()
        self.vol.valueChanged.connect(lambda v: self.vol_lbl.setText(f"{v}%"))
        self.vol_lbl.setText(f"{self.vol.value()}%")
        vrow = QHBoxLayout()
        vrow.addWidget(self.vol, 1)
        vrow.addWidget(self.vol_lbl)
        self.color = sound.get("color", ACCENT)
        self.color_btn = QPushButton("Farbe wählen")
        self.color_btn.setStyleSheet(f"background:{self.color}")
        self.color_btn.clicked.connect(self._pick)
        lay.addRow("Name", self.name)
        lay.addRow("Hotkey", self.hotkey)
        lay.addRow("Lautstärke", vrow)
        lay.addRow("Farbe", self.color_btn)
        hint = QLabel("Tipp: Hotkeys funktionieren global – auch im Spiel.")
        hint.setObjectName("muted")
        lay.addRow(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self, "Farbe")
        if c.isValid():
            self.color = c.name()
            self.color_btn.setStyleSheet(f"background:{self.color}")

    def values(self) -> dict:
        return {"name": self.name.text().strip() or "Sound", "hotkey": self.hotkey.combo(),
                "volume": self.vol.value() / 100.0, "color": self.color}


class SoundboardTab(QWidget):
    openInEditor = Signal(str)  # sound id

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("page")
        self.setAcceptDrops(True)
        self.tiles: dict[str, SoundTile] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(12)
        top = QHBoxLayout()
        title = QLabel("Soundboard")
        title.setObjectName("h1")
        top.addWidget(title)
        top.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Suchen…")
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search)
        add = QPushButton("+ Sounds hinzufügen")
        add.setObjectName("accent")
        add.clicked.connect(self._add)
        top.addWidget(add)
        stop = QPushButton("■ Alle stoppen")
        stop.clicked.connect(ctl.stop_all)
        top.addWidget(stop)
        root.addLayout(top)

        opts = card()
        row = QHBoxLayout(opts)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(22)
        self.cb_me = ToggleSwitch("Ich höre die Sounds")
        self.cb_friends = ToggleSwitch("Freunde hören die Sounds")
        self.cb_me.setChecked(ctl.cfg["play_to_monitor"])
        self.cb_friends.setChecked(ctl.cfg["play_to_virtual"])
        self.cb_me.toggled.connect(lambda v: ctl.cfg.__setitem__("play_to_monitor", v))
        self.cb_friends.toggled.connect(lambda v: ctl.cfg.__setitem__("play_to_virtual", v))
        row.addWidget(self.cb_me)
        row.addWidget(self.cb_friends)
        row.addStretch(1)
        vol_lbl = QLabel("Gesamt-Lautstärke")
        vol_lbl.setObjectName("muted")
        row.addWidget(vol_lbl)
        self.master = QSlider(Qt.Horizontal)
        self.master.setRange(0, 100)
        self.master.setFixedWidth(160)
        self.master.setValue(int(ctl.cfg["master_volume"] * 100))
        self.master.valueChanged.connect(lambda v: ctl.cfg.__setitem__("master_volume", v / 100))
        row.addWidget(self.master)
        root.addWidget(opts)

        self.status = QLabel()
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.inner.setObjectName("page")
        self.flow = FlowLayout(self.inner, 12)
        self.scroll.setWidget(self.inner)
        root.addWidget(self.scroll, 1)

        self.empty = QLabel("Noch keine Sounds.\n\nZieh Audiodateien (WAV, MP3, OGG, FLAC) hier rein,\n"
                            "klick auf „+ Sounds hinzufügen“ oder speichere einen Clip als Sound.")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("muted")
        root.addWidget(self.empty)

        ctl.soundsChanged.connect(self.refresh)
        ctl.settingsChanged.connect(self._sync)
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)

    def _sync(self):
        for cb, key in ((self.cb_me, "play_to_monitor"), (self.cb_friends, "play_to_virtual")):
            cb.blockSignals(True)
            cb.setChecked(self.ctl.cfg[key])
            cb.blockSignals(False)
        self.master.blockSignals(True)
        self.master.setValue(int(self.ctl.cfg["master_volume"] * 100))
        self.master.blockSignals(False)

    def refresh(self):
        while self.flow.count():
            it = self.flow.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        self.tiles = {}
        for s in self.ctl.sounds.sounds:
            t = SoundTile(s)
            t.clicked.connect(self.ctl.play_sound)
            t.menuRequested.connect(self._menu)
            self.flow.addWidget(t)
            self.tiles[s["id"]] = t
        self.empty.setVisible(not self.tiles)
        self.scroll.setVisible(bool(self.tiles))
        self._filter(self.search.text())

    def _filter(self, text):
        text = text.lower().strip()
        for sid, t in self.tiles.items():
            t.setVisible(not text or text in t.sound["name"].lower())
        self.inner.updateGeometry()

    def _tick(self):
        prog = {}
        for v in self.ctl.mixer.playing():
            if v.sound_id in self.tiles:
                prog[v.sound_id] = v.progress()
        for sid, t in self.tiles.items():
            t.set_progress(prog.get(sid, -1.0))
        m = self.ctl.mixer
        parts = []
        parts.append("🎧 " + (m.devices["monitor"] if m.is_open("monitor") else f"Fehler: {m.errors['monitor']}"))
        if m.is_open("virtual"):
            parts.append("🎙 Freunde über: " + m.devices["virtual"])
        else:
            parts.append("🎙 Kein virtuelles Mikro – deine Freunde hören die Sounds nicht (siehe Einstellungen)")
        txt = "   ·   ".join(parts)
        if txt != self.status.text():
            self.status.setText(txt)

    def _add(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Sounds hinzufügen", os.path.expanduser("~"),
                                                "Audio (*.wav *.mp3 *.ogg *.flac *.aiff *.aif *.opus)")
        self._import(files)

    def _import(self, files):
        bad = []
        n = 0
        for f in files:
            try:
                if self.ctl.sounds.add_file(f):
                    n += 1
                else:
                    bad.append(os.path.basename(f))
            except Exception as e:
                bad.append(f"{os.path.basename(f)} ({e})")
        if n:
            self.ctl.soundsChanged.emit()
            self.ctl.toast.emit(f"{n} Sound(s) hinzugefügt", "ok")
        if bad:
            QMessageBox.warning(self, "Nicht importiert", "Diese Dateien konnten nicht gelesen werden:\n\n" +
                                "\n".join(bad))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]
        files = [f for f in files if os.path.splitext(f)[1].lower() in AUDIO_EXT]
        self._import(files)

    def _menu(self, sid, pos):
        s = self.ctl.sounds.get(sid)
        if not s:
            return
        m = QMenu(self)
        a_play = m.addAction("▶ Abspielen")
        a_prev = m.addAction("🎧 Nur für mich vorhören")
        m.addSeparator()
        a_edit = m.addAction("✎ Name, Hotkey, Lautstärke, Farbe…")
        a_fx = m.addAction("✂ Im Clip-Editor bearbeiten (Schneiden/Effekte)")
        m.addSeparator()
        a_left = m.addAction("← Nach vorne")
        a_right = m.addAction("→ Nach hinten")
        a_show = m.addAction("Im Explorer zeigen")
        m.addSeparator()
        a_del = m.addAction("🗑 Löschen")
        act = m.exec(pos)
        if act == a_play:
            self.ctl.play_sound(sid)
        elif act == a_prev:
            self.ctl.play_data(self.ctl.sounds.audio(s), s["name"])
        elif act == a_edit:
            dlg = SoundDialog(s, self)
            if dlg.exec():
                self.ctl.sounds.update(sid, **dlg.values())
                self.ctl.apply_hotkeys()
                self.refresh()
        elif act == a_fx:
            self.openInEditor.emit(sid)
        elif act in (a_left, a_right):
            self.ctl.sounds.move(sid, -1 if act == a_left else 1)
            self.refresh()
        elif act == a_show:
            subprocess.Popen(["explorer", "/select,", str(self.ctl.sounds.path(s))])
        elif act == a_del:
            if QMessageBox.question(self, "Löschen", f"„{s['name']}“ wirklich löschen?") == QMessageBox.Yes:
                self.ctl.mixer.stop(sid)
                self.ctl.sounds.remove(sid)
                self.ctl.apply_hotkeys()
                self.refresh()
