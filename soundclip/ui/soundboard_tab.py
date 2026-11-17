from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from ..hotkeys import pretty
from ..library import AUDIO_EXT
from . import theme
from .theme import P
from .widgets import ACCENT, MUTED, FlowLayout, HotkeyEdit, ToggleSwitch, card


class SoundTile(QFrame):
    clicked = Signal(str)
    menuRequested = Signal(str, object)

    def __init__(self, sound: dict):
        super().__init__()
        self.sound = sound
        self.progress = -1.0
        self.setFixedSize(196, 112) if theme.potato() else self.setFixedSize(184, 96)
        self.setCursor(Qt.PointingHandCursor)
        tip = f"{sound['name']}\nLinksklick: abspielen · Rechtsklick: Optionen"
        if sound.get("trigger"):
            tip += f"\nSprach-Trigger: „{sound['trigger']}“"
        self.setToolTip(tip)

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
        from ..i18n import tr
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor(self.sound.get("color", ACCENT))
        hover = getattr(self, "_hover", False)
        playing = self.progress >= 0
        pot = theme.potato()
        if pot:
            idx = sum(map(ord, str(self.sound["id"]))) % 8
            tilt = theme.POTATO_TILTS[idx] * (0.4 if hover else 1.0)
            w, h = self.width(), self.height()
            p.translate(w / 2, h / 2)
            p.rotate(tilt)
            p.translate(-w / 2, -h / 2)
            sh = 6
            r = QRectF(6, 6, w - 12 - sh, h - 12 - sh)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#111"))
            p.drawRect(r.translated(sh, sh))
            p.setBrush(QColor(theme.POTATO_TILES[idx % len(theme.POTATO_TILES)]) if not self.sound.get("color")
                       else col.lighter(135))
            p.setPen(QPen(QColor("#111"), 4.5 if playing else 3))
            p.drawRect(r)
        else:
            r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            p.setBrush(QColor(P["accent_soft"]) if playing else (QColor(P["panel_hover"]) if hover else QColor(P["panel"])))
            p.setPen(QPen(QColor(P["accent"]) if playing else QColor(P["border2"] if hover else P["border"]), 1.2))
            p.drawRoundedRect(r, 10, 10)
            # Farbmarke
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(r.left() + 12, r.bottom() - 21, 9, 9), 2.5, 2.5)
        if playing:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#111") if pot else QColor(P["accent"]))
            p.drawRect(QRectF(r.left() + 2, r.bottom() - (7 if pot else 4), (r.width() - 4) * min(1.0, self.progress),
                              5 if pot else 3))
        # Play-Knopf
        c = QRectF(r.right() - 38, r.top() + 10, 28, 28)
        p.setPen(QPen(QColor("#111"), 2) if pot else Qt.NoPen)
        p.setBrush(QColor("white") if pot else QColor(P["border2"] if not hover else P["accent"]))
        p.drawEllipse(c)
        p.setBrush(QColor("#111") if pot else (QColor(P["accent_text"]) if hover else QColor(P["text"])))
        p.setPen(Qt.NoPen)
        if playing:
            p.drawRect(QRectF(c.center().x() - 5, c.center().y() - 5, 10, 10))
        else:
            tri = QPainterPath()
            tri.moveTo(c.center().x() - 3.5, c.center().y() - 6)
            tri.lineTo(c.center().x() + 6.5, c.center().y())
            tri.lineTo(c.center().x() - 3.5, c.center().y() + 6)
            tri.closeSubpath()
            p.drawPath(tri)
        if pot:
            f = QFont("Bungee")
            f.setPointSizeF(9.5)
            name = self.sound["name"].upper()
            if self.sound.get("fav"):
                name = "★ " + name
        else:
            f = QFont(self.font())
            f.setPointSizeF(10.5)
            f.setBold(True)
            name = ("★ " if self.sound.get("fav") else "") + self.sound["name"]
        p.setFont(f)
        p.setPen(QColor(P["text"]))
        p.drawText(r.adjusted(12, 10, -44, -30), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, name)
        hk = pretty(self.sound.get("hotkey", ""))
        f = QFont("Comic Neue" if pot else self.font().family())
        f.setBold(pot)
        f.setPointSizeF(8.5)
        p.setFont(f)
        if hk:
            fm = p.fontMetrics()
            w = fm.horizontalAdvance(hk) + 12
            pill = QRectF(r.left() + (12 if pot else 28), r.bottom() - 26, w, 19)
            if pot:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#111"))
                p.drawRect(pill)
                p.setPen(QColor("#FFE94D"))
            else:
                p.setPen(QPen(QColor(P["border2"]), 1))
                p.setBrush(QColor(P["panel2"]))
                p.drawRoundedRect(pill, 4, 4)
                p.setPen(QColor(P["text"]))
            p.drawText(pill, Qt.AlignCenter, hk)
        else:
            p.setPen(QColor(P["muted"]))
            p.drawText(r.adjusted(12 if pot else 28, 0, -10, -9), Qt.AlignLeft | Qt.AlignBottom, tr("kein Hotkey"))
        vol = float(self.sound.get("volume", 1.0))
        extra = []
        if isinstance(self.sound.get("fx"), dict) and self.sound["fx"].get("preset"):
            extra.append("✨")
        if self.sound.get("trigger"):
            extra.append("🗣")
        if abs(vol - 1.0) > 0.01:
            extra.append(f"{int(vol * 100)}%")
        if extra:
            p.setPen(QColor(P["muted"]))
            p.drawText(r.adjusted(14, 0, -12, -9), Qt.AlignRight | Qt.AlignBottom, " ".join(extra))

class SoundDialog(QDialog):
    def __init__(self, sound: dict, parent=None, folders=(), preview=None):
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
        self.folder = QComboBox()
        self.folder.setEditable(True)
        self.folder.addItem("")
        for f in folders:
            self.folder.addItem(f)
        self.folder.setCurrentText(sound.get("folder", ""))
        self.folder.lineEdit().setPlaceholderText("kein Ordner")
        self.trigger = QLineEdit(sound.get("trigger", ""))
        self.trigger.setPlaceholderText("z. B. boom  (mehrere mit Komma)")
        lay.addRow("Name", self.name)
        lay.addRow("Hotkey", self.hotkey)
        lay.addRow("Lautstärke", vrow)
        lay.addRow("Farbe", self.color_btn)
        lay.addRow("Ordner", self.folder)
        lay.addRow("Sprach-Trigger", self.trigger)
        # Effekt nur fuer diesen Sound
        from ..effects import VOICE_PRESETS, voice_name
        from ..i18n import tr as _tr
        fx = sound.get("fx") if isinstance(sound.get("fx"), dict) else {}
        self.fx = QComboBox()
        self.fx.addItem("Kein Effekt", "")
        for k in VOICE_PRESETS:
            self.fx.addItem(f"{VOICE_PRESETS[k][0]} {_tr(voice_name(k))}", k)
        self.fx.setCurrentIndex(max(0, self.fx.findData(fx.get("preset", ""))))
        self.fx_amt = QSlider(Qt.Horizontal)
        self.fx_amt.setRange(0, 100)
        self.fx_amt.setValue(int(round(float(fx.get("amount", 0.5)) * 100)))
        self.fx_amt.setFixedWidth(120)
        self.fx_amt.setToolTip("Stärke des Effekts")
        frow = QHBoxLayout()
        frow.addWidget(self.fx, 1)
        frow.addWidget(self.fx_amt)
        if preview is not None:
            b_prev = QPushButton("▶")
            b_prev.setToolTip("Vorhören (nur du)")
            b_prev.setFixedWidth(40)
            b_prev.clicked.connect(lambda: preview(self._fx_value()))
            frow.addWidget(b_prev)
        self.fx.currentIndexChanged.connect(lambda _: self.fx_amt.setEnabled(bool(self.fx.currentData())))
        self.fx_amt.setEnabled(bool(self.fx.currentData()))
        lay.addRow("Effekt", frow)
        hint = QLabel("Tipp: Hotkeys funktionieren global – auch im Spiel.\n"
                      "Sprach-Trigger: Sagst du das Wort, spielt der Sound (in den Einstellungen einschalten).")
        hint.setObjectName("muted")
        lay.addRow(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        lay.addRow(bb)

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self, "Farbe")
        if c.isValid():
            self.color = c.name()
            self.color_btn.setStyleSheet(f"background:{self.color}")

    def values(self) -> dict:
        return {"name": self.name.text().strip() or "Sound", "hotkey": self.hotkey.combo(),
                "volume": self.vol.value() / 100.0, "color": self.color,
                "folder": self.folder.currentText().strip()[:40], "trigger": self.trigger.text().strip()[:80],
                "fx": self._fx_value()}

    def _fx_value(self):
        k = self.fx.currentData()
        return {"preset": k, "amount": self.fx_amt.value() / 100.0} if k else None


class TrimDialog(QDialog):
    """Anfang und Ende eines Sounds festlegen (die Datei bleibt unverändert)."""

    def __init__(self, ctl, sound: dict, parent=None):
        super().__init__(parent)
        from .widgets import WaveformView
        from ..config import SR
        self.ctl = ctl
        self.sound = sound
        self.setWindowTitle("Sound zuschneiden")
        self.setMinimumWidth(640)
        self.data = ctl.sounds.audio_raw(sound)
        self.dur = len(self.data) / SR
        lay = QVBoxLayout(self)
        info = QLabel("Grünen/roten Marker ziehen (Linksklick setzt den Anfang, Rechtsklick das Ende).")
        info.setObjectName("muted")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.wave = WaveformView()
        self.wave.setMinimumHeight(150)
        self.wave.set_audio(self.data, self.dur)
        t = sound.get("trim") or [0.0, self.dur]
        self.wave.set_range(float(t[0]), min(float(t[1]), self.dur))
        self.wave.rangeChanged.connect(lambda *_: self._label())
        lay.addWidget(self.wave)
        self.lbl = QLabel()
        lay.addWidget(self.lbl)
        row = QHBoxLayout()
        b_play = QPushButton("▶ Vorhören")
        b_play.clicked.connect(self._preview)
        b_stop = QPushButton("■")
        b_stop.clicked.connect(lambda: ctl.mixer.stop("__preview__"))
        b_auto = QPushButton("Stille abschneiden")
        b_auto.clicked.connect(self._auto)
        b_reset = QPushButton("Ganze Datei")
        b_reset.clicked.connect(lambda: (self.wave.set_range(0.0, self.dur), self._label()))
        for b in (b_play, b_stop, b_auto, b_reset):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        lay.addWidget(bb)
        self._label()

    def _label(self):
        a, b = self.wave.start, self.wave.end
        self.lbl.setText(f"{a:.2f} s – {b:.2f} s  ({b - a:.2f} s)")

    def _auto(self):
        from ..loudness import silence_bounds
        bnd = silence_bounds(self.data)
        if bnd:
            self.wave.set_range(*bnd)
        self._label()

    def _preview(self):
        from ..config import SR
        a, b = int(self.wave.start * SR), int(self.wave.end * SR)
        self.ctl.play_data(self.data[a:b], self.sound["name"])

    def trim(self):
        a, b = self.wave.start, self.wave.end
        if a < 0.01 and b > self.dur - 0.01:
            return None
        return [a, b]


class SoundboardTab(QWidget):
    openInEditor = Signal(str)  # sound id

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("page")
        self.setAcceptDrops(True)
        self.tiles: dict[str, SoundTile] = {}
        self.cur_folder = ""          # "" = alle, "*fav" = Favoriten, sonst Ordnername

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
        share = QPushButton("Sound-Packs")
        share.setToolTip("Sounds als eine Datei an Freunde schicken oder ein Pack von Freunden laden")
        pm = QMenu(share)
        pm.addAction("Alle Sounds als Pack speichern…", lambda: self._export_pack(None))
        pm.addAction("Sound-Pack importieren…", self._import_pack_dialog)
        share.setMenu(pm)
        top.addWidget(share)
        rnd = QPushButton("🎲 Zufall")
        rnd.setToolTip("Spielt einen zufälligen Sound aus der aktuellen Auswahl")
        rnd.clicked.connect(lambda: ctl.play_random(self.cur_folder))
        top.addWidget(rnd)
        stop = QPushButton("■ Alle stoppen")
        stop.clicked.connect(ctl.stop_all)
        if theme.potato():
            stop.setObjectName("danger")
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

        # ---- Text vorlesen lassen
        tts = card()
        tl = QHBoxLayout(tts)
        tl.setContentsMargins(18, 10, 18, 10)
        tl.setSpacing(10)
        tlab = QLabel("🗣  Vorlesen")
        tlab.setStyleSheet("font-weight: 700; background: transparent;")
        tl.addWidget(tlab)
        self.tts_text = QLineEdit()
        self.tts_text.setPlaceholderText("Text eingeben – wird in Discord vorgelesen")
        self.tts_text.returnPressed.connect(lambda: self._speak(False))
        tl.addWidget(self.tts_text, 1)
        self.tts_voice = QComboBox()
        self.tts_voice.setMinimumWidth(170)
        self.tts_voice.addItem("Windows-Stimme", "")
        self.tts_voice.currentIndexChanged.connect(
            lambda _: ctl.cfg.__setitem__("tts_voice", self.tts_voice.currentData() or ""))
        tl.addWidget(self.tts_voice)
        self.tts_fx = ToggleSwitch("mit Stimmeffekt")
        self.tts_fx.setChecked(ctl.cfg["tts_effect"])
        self.tts_fx.toggled.connect(lambda v: ctl.cfg.__setitem__("tts_effect", v))
        tl.addWidget(self.tts_fx)
        b_say = QPushButton("Vorlesen")
        b_say.setObjectName("accent")
        b_say.clicked.connect(lambda: self._speak(False))
        tl.addWidget(b_say)
        b_save = QPushButton("Als Sound speichern")
        b_save.clicked.connect(lambda: self._speak(True))
        tl.addWidget(b_save)
        root.addWidget(tts)
        QTimer.singleShot(1500, self._load_voices)

        self.folder_bar = QWidget()
        self.folder_flow = FlowLayout(self.folder_bar, 8)
        self.folder_flow.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.folder_bar)

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

    # ---- Ordner
    def _folders(self) -> list[str]:
        return self.ctl.sounds.folders(self.ctl.cfg["sound_folders"] or [])

    def _build_folder_bar(self):
        while self.folder_flow.count():
            it = self.folder_flow.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        sounds = self.ctl.sounds.sounds
        folders = self._folders()
        if self.cur_folder not in ("", "*fav") and self.cur_folder not in folders:
            self.cur_folder = ""
        items = [("", f"Alle ({len(sounds)})"), ("*fav", f"★ Favoriten ({sum(1 for s in sounds if s.get('fav'))})")]
        items += [(f, f"{f} ({sum(1 for s in sounds if s.get('folder', '') == f)})") for f in folders]
        for key, text in items:
            b = QPushButton(text.replace("&", "&&"))
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(key == self.cur_folder)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._set_folder(k))
            if key not in ("", "*fav"):
                b.setContextMenuPolicy(Qt.CustomContextMenu)
                b.customContextMenuRequested.connect(lambda pos, k=key, w=b: self._folder_menu(k, w.mapToGlobal(pos)))
                b.setToolTip("Rechtsklick: umbenennen oder löschen")
            self.folder_flow.addWidget(b)
        add = QPushButton("+ Ordner")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self._new_folder)
        self.folder_flow.addWidget(add)

    def _set_folder(self, key):
        self.cur_folder = key
        self._build_folder_bar()
        self._filter(self.search.text())

    def _new_folder(self, sid=None):
        name, ok = QInputDialog.getText(self, "Neuer Ordner", "Name des Ordners:")
        name = name.strip()[:40]
        if not ok or not name:
            return None
        fl = list(self.ctl.cfg["sound_folders"] or [])
        if name not in fl:
            fl.append(name)
            self.ctl.cfg["sound_folders"] = fl
        if sid:
            self.ctl.sounds.update(sid, folder=name)
        self.refresh()
        return name

    def _folder_menu(self, key, pos):
        m = QMenu(self)
        a_ren = m.addAction("Umbenennen…")
        a_del = m.addAction("Ordner auflösen (Sounds bleiben)")
        act = m.exec(pos)
        fl = list(self.ctl.cfg["sound_folders"] or [])
        if act == a_ren:
            new, ok = QInputDialog.getText(self, "Ordner umbenennen", "Neuer Name:", text=key)
            new = new.strip()[:40]
            if ok and new and new != key:
                self.ctl.sounds.rename_folder(key, new)
                self.ctl.cfg["sound_folders"] = [new if f == key else f for f in fl]
                if self.cur_folder == key:
                    self.cur_folder = new
                self.refresh()
        elif act == a_del:
            self.ctl.sounds.rename_folder(key, "")
            self.ctl.cfg["sound_folders"] = [f for f in fl if f != key]
            if self.cur_folder == key:
                self.cur_folder = ""
            self.refresh()

    def refresh(self):
        while self.flow.count():
            it = self.flow.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        self.tiles = {}
        self._build_folder_bar()
        for s in sorted(self.ctl.sounds.sounds, key=lambda x: not x.get("fav")):
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
        cur = self.cur_folder
        for sid, t in self.tiles.items():
            s = t.sound
            in_folder = not cur or (cur == "*fav" and s.get("fav")) or s.get("folder", "") == cur
            hit = not text or text in s["name"].lower() or text in s.get("folder", "").lower() \
                or text in str(s.get("trigger", "")).lower()
            t.setVisible(bool(in_folder and hit))
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
        from ..i18n import tr
        if m.is_open("monitor") and "CABLE" in str(m.devices["monitor"]).upper():
            parts.append("🎧 ⚠ " + tr("Du hörst deine Sounds nicht selbst – „Ich höre über“ steht auf dem Kabel "
                                      "(Einstellungen → Audio-Geräte)"))
        else:
            parts.append("🎧 " + (m.devices["monitor"] if m.is_open("monitor")
                                 else tr("Fehler:") + " " + str(m.errors["monitor"])))
        if m.is_open("virtual"):
            parts.append("🎙 " + tr("Freunde über:") + " " + m.devices["virtual"])
        else:
            parts.append("🎙 " + tr("Kein virtuelles Mikro – deine Freunde hören die Sounds nicht (siehe Einstellungen)"))
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
                folder = self.cur_folder if self.cur_folder not in ("", "*fav") else ""
                if self.ctl.sounds.add_file(f, auto_trim=bool(self.ctl.cfg["auto_trim"]), folder=folder):
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
        from ..packs import PACK_EXT
        for f in files:
            if f.lower().endswith(PACK_EXT):
                self._import_pack(f)
        files = [f for f in files if os.path.splitext(f)[1].lower() in AUDIO_EXT]
        if files:
            self._import(files)

    # ---- Sound-Packs
    def _export_pack(self, ids):
        from ..capture import safe_name
        from ..config import EXPORT_DIR
        from ..packs import PACK_EXT, export_pack
        ids = ids or [s["id"] for s in self.ctl.sounds.sounds]
        if not ids:
            self.ctl.toast.emit("Noch keine Sounds zum Teilen", "warn")
            return
        name = "Potato Sounds" if len(ids) > 1 else (self.ctl.sounds.get(ids[0]) or {}).get("name", "Sound")
        path, _ = QFileDialog.getSaveFileName(self, "Sound-Pack speichern", str(EXPORT_DIR / (safe_name(name) + PACK_EXT)),
                                              "Potato Clips Sound-Pack (*.potatopack)")
        if not path:
            return
        if not path.lower().endswith(PACK_EXT):
            path += PACK_EXT
        try:
            n = export_pack(self.ctl.sounds, ids, path)
            self.ctl.toast.emit(f"Sound-Pack mit {n} Sound(s) gespeichert – einfach an Freunde schicken", "ok")
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _import_pack_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Sound-Pack importieren", os.path.expanduser("~"),
                                              "Potato Clips Sound-Pack (*.potatopack)")
        if path:
            self._import_pack(path)

    def _import_pack(self, path):
        from ..packs import import_pack
        try:
            n = import_pack(self.ctl.sounds, path)
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"{os.path.basename(path)}: {e}")
            return
        self.ctl.soundsChanged.emit()
        self.ctl.toast.emit(f"{n} Sound(s) aus dem Pack hinzugefügt", "ok")

    # ---- Vorlesen
    def _load_voices(self):
        import threading

        def work():
            from .. import tts
            try:
                vs = tts.voices()
            except Exception:
                vs = []
            self._voices_found = vs
        self._voices_found = None
        threading.Thread(target=work, daemon=True).start()
        self._voice_poll = QTimer(self)
        self._voice_poll.timeout.connect(self._poll_voices)
        self._voice_poll.start(300)

    def _poll_voices(self):
        if self._voices_found is None:
            return
        self._voice_poll.stop()
        self._fill_voices(self._voices_found)

    def _fill_voices(self, vs):
        from .. import i18n
        want = self.ctl.cfg["tts_voice"]
        lang = "de" if i18n.LANG == "de" else "en"
        self.tts_voice.blockSignals(True)
        self.tts_voice.clear()
        vs = sorted(vs, key=lambda v: (not str(v.get("culture", "")).lower().startswith(lang), str(v.get("name", ""))))
        for v in vs:
            nm = str(v.get("name", ""))
            short = nm.replace("Microsoft ", "").replace(" Desktop", "")
            self.tts_voice.addItem(f"{short} ({v.get('culture', '')})", nm)
        if not vs:
            self.tts_voice.addItem("Windows-Stimme", "")
        i = self.tts_voice.findData(want)
        self.tts_voice.setCurrentIndex(i if i >= 0 else 0)
        self.tts_voice.blockSignals(False)

    def _speak(self, save: bool):
        text = self.tts_text.text().strip()
        if not text:
            self.tts_text.setFocus()
            return
        import threading
        voice = self.tts_voice.currentData() or ""
        use_fx = self.tts_fx.isChecked()
        ctl = self.ctl
        self._spoken_result = None

        def work():
            from .. import tts
            from ..mixer import load_audio
            try:
                path = tts.synth(text, voice)
                data = load_audio(path)
                try:
                    os.remove(path)
                except Exception:
                    pass
                if use_fx and ctl.cfg["voice_enabled"] and ctl.cfg["voice_preset"]:
                    from ..effects import VOICE_PRESETS, apply_chain
                    pre = VOICE_PRESETS.get(ctl.cfg["voice_preset"])
                    if pre:
                        scale = 0.4 + 1.2 * ctl.voice_amount()
                        chain = [{"type": k, "amount": min(1.0, a * scale)} for k, a in pre[1]]
                        data = apply_chain(data, chain)
                self._spoken_result = (text, data, save)
                ctl.stats.add("tts")
            except Exception as e:
                ctl.toast.emit(f"Vorlesen fehlgeschlagen: {e}", "warn")
                self._spoken_result = False
        threading.Thread(target=work, daemon=True).start()
        self.ctl.toast.emit("🗣 Wird vorgelesen …", "info")
        self._speak_poll = QTimer(self)
        self._speak_poll.timeout.connect(self._poll_spoken)
        self._speak_poll.start(100)

    def _poll_spoken(self):
        res = self._spoken_result
        if res is None:
            return
        self._speak_poll.stop()
        if not res:
            return
        text, data, save = res
        if save:
            s = self.ctl.sounds.add_array(text[:40], data)
            self.ctl.soundsChanged.emit()
            self.ctl.toast.emit(f"„{s['name']}“ ist jetzt im Soundboard – Rechtsklick drauf für Hotkey", "ok")
        else:
            self.ctl.mixer.play(data, sound_id="__tts__", name=text[:40])

    def _preview_fx(self, sid, fx):
        s = self.ctl.sounds.get(sid)
        if not s:
            return
        tmp = dict(s, fx=fx)
        try:
            data, gain = self.ctl.sounds.playable(tmp, bool(self.ctl.cfg["normalize_sounds"]))
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
            return
        self.ctl.mixer.stop("__preview__")
        self.ctl.mixer.play(data, gain=gain, sound_id="__preview__", name=s["name"], preview=True)

    def _copy_link(self, sid):
        from PySide6.QtWidgets import QApplication
        r = self.ctl.remote
        if not r.running:
            self.ctl.cfg["api_enabled"] = True
            r.sync()
            self.ctl.settingsChanged.emit()
        if not r.running:
            QMessageBox.warning(self, "Fehler", "Die Steuerung über Links konnte nicht gestartet werden.")
            return
        QApplication.clipboard().setText(r.local_url(f"/api/play/{sid}"))
        self.ctl.toast.emit("🔗 Link kopiert – im Stream Deck bei „Website“ einfügen und „Im Hintergrund“ anhaken",
                            "ok")

    def _menu(self, sid, pos):
        s = self.ctl.sounds.get(sid)
        if not s:
            return
        m = QMenu(self)
        a_play = m.addAction("▶ Abspielen")
        a_prev = m.addAction("🎧 Nur für mich vorhören")
        m.addSeparator()
        a_fav = m.addAction("☆ Kein Favorit mehr" if s.get("fav") else "★ Als Favorit")
        a_edit = m.addAction("✎ Name, Hotkey, Ordner, Sprach-Trigger…")
        fm = m.addMenu("📁 In Ordner")
        f_acts = {}
        for f in self._folders():
            a = fm.addAction(("✓ " if s.get("folder", "") == f else "") + f)
            f_acts[a] = f
        if s.get("folder"):
            f_acts[fm.addAction("Aus dem Ordner nehmen")] = ""
        fm.addSeparator()
        a_newf = fm.addAction("+ Neuer Ordner…")
        a_trim = m.addAction("✂ Zuschneiden…")
        a_fx = m.addAction("Im Clip-Editor bearbeiten (Effekte)")
        a_link = m.addAction("🔗 Link für Stream Deck kopieren")
        m.addSeparator()
        a_left = m.addAction("← Nach vorne")
        a_right = m.addAction("→ Nach hinten")
        a_show = m.addAction("Im Explorer zeigen")
        a_pack = m.addAction("Als Sound-Pack teilen…")
        m.addSeparator()
        a_del = m.addAction("🗑 Löschen")
        act = m.exec(pos)
        if act == a_play:
            self.ctl.play_sound(sid)
        elif act == a_prev:
            self.ctl.play_data(self.ctl.sounds.audio(s), s["name"])
        elif act == a_fav:
            self.ctl.sounds.update(sid, fav=not s.get("fav"))
            self.refresh()
        elif act in f_acts:
            self.ctl.sounds.update(sid, folder=f_acts[act])
            self.refresh()
        elif act == a_newf:
            self._new_folder(sid)
        elif act == a_trim:
            try:
                dlg = TrimDialog(self.ctl, s, self)
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))
                return
            if dlg.exec():
                self.ctl.sounds.set_trim(sid, dlg.trim())
                self.refresh()
            self.ctl.mixer.stop("__preview__")
        elif act == a_link:
            self._copy_link(sid)
        elif act == a_edit:
            dlg = SoundDialog(s, self, self._folders(), preview=lambda fx, sid=sid: self._preview_fx(sid, fx))
            if dlg.exec():
                vals = dlg.values()
                self.ctl.sounds.update(sid, **vals)
                if vals["folder"] and vals["folder"] not in (self.ctl.cfg["sound_folders"] or []):
                    self.ctl.cfg["sound_folders"] = list(self.ctl.cfg["sound_folders"] or []) + [vals["folder"]]
                self.ctl.apply_hotkeys()
                self.refresh()
                if vals["trigger"] and not self.ctl.cfg["triggers_enabled"]:
                    self.ctl.toast.emit("Sprach-Trigger gespeichert – in den Einstellungen unter „Sprach-Trigger“ einschalten",
                                        "info")
        elif act == a_fx:
            self.openInEditor.emit(sid)
        elif act in (a_left, a_right):
            self.ctl.sounds.move(sid, -1 if act == a_left else 1)
            self.refresh()
        elif act == a_pack:
            self._export_pack([sid])
        elif act == a_show:
            subprocess.Popen(["explorer", "/select,", str(self.ctl.sounds.path(s))])
        elif act == a_del:
            if QMessageBox.question(self, "Löschen", f"„{s['name']}“ wirklich löschen?") == QMessageBox.Yes:
                self.ctl.mixer.stop(sid)
                self.ctl.sounds.remove(sid)
                self.ctl.apply_hotkeys()
                self.refresh()
