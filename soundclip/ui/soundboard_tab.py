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
        else:
            f = QFont(self.font())
            f.setPointSizeF(10.5)
            f.setBold(True)
            name = self.sound["name"]
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
        if abs(vol - 1.0) > 0.01:
            p.setPen(QColor(P["muted"]))
            p.drawText(r.adjusted(14, 0, -12, -9), Qt.AlignRight | Qt.AlignBottom, f"{int(vol * 100)}%")

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
        share = QPushButton("Sound-Packs")
        share.setToolTip("Sounds als eine Datei an Freunde schicken oder ein Pack von Freunden laden")
        pm = QMenu(share)
        pm.addAction("Alle Sounds als Pack speichern…", lambda: self._export_pack(None))
        pm.addAction("Sound-Pack importieren…", self._import_pack_dialog)
        share.setMenu(pm)
        top.addWidget(share)
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
        a_pack = m.addAction("Als Sound-Pack teilen…")
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
