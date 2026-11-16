from __future__ import annotations

import subprocess

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from ..config import DATA_DIR
from ..controller import ACTION_NAMES
from ..mixer import find_cable_device, list_output_devices
from .. import autostart
from ..capture import LevelProbe, run_helper_list
from ..mixer import find_cable_capture
from ..i18n import tr as tr_text
from .theme import P
from .widgets import GREEN, RED, HotkeyEdit, LevelMeter, ToggleSwitch, hard_shadow


def _theme_preview(key: str) -> QPixmap:
    """Kleines Vorschaubild fuer die Design-Auswahl."""
    pm = QPixmap(240, 132)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if key == "pro":
        p.setPen(QPen(QColor("#23262D"), 2))
        p.setBrush(QColor("#0D0E11"))
        p.drawRoundedRect(QRectF(1, 1, 238, 130), 10, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#111317"))
        p.drawRoundedRect(QRectF(10, 10, 60, 112), 6, 6)
        p.setBrush(QColor("#2C3038"))
        p.drawRoundedRect(QRectF(82, 14, 80, 10), 3, 3)
        p.setBrush(QColor("#16181D"))
        p.setPen(QPen(QColor("#F2A93B"), 2))
        p.drawRoundedRect(QRectF(82, 34, 146, 34), 6, 6)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(82, 78, 146, 34), 6, 6)
        p.setBrush(QColor("#F2A93B"))
        p.drawRoundedRect(QRectF(92, 56, 70, 4), 2, 2)
    else:
        p.setPen(QPen(QColor("#111"), 4))
        p.setBrush(QColor("#FFE94D"))
        p.drawRect(QRectF(2, 2, 236, 128))
        for i, (col, ang) in enumerate((("#FF3D8B", -6), ("#3DE8FF", 5), ("#B6FF3B", -3))):
            p.save()
            p.translate(48 + i * 72, 66)
            p.rotate(ang)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#111"))
            p.drawRect(QRectF(-26, -30, 56, 64))
            p.setPen(QPen(QColor("#111"), 3))
            p.setBrush(QColor(col))
            p.drawRect(QRectF(-30, -34, 56, 64))
            p.restore()
    p.end()
    return pm


def intruder_text(ctl) -> str:
    """Warntext, wenn andere Apps ins virtuelle Kabel spielen (die hoeren dann alle in Discord)."""
    others = ctl.sources.apps_on_device(ctl.mixer.device_id("virtual"))
    if not others:
        return ""
    names = ", ".join(others)
    txt = (f"⚠ <b>{names}</b> spielt gerade ebenfalls ins virtuelle Kabel – das hören deine Freunde in Discord mit. "
           "Stell in dieser App das Ausgabegerät auf deinen Kopfhörer/Lautsprecher um.")
    if any(n.lower().startswith("discord") for n in others):
        txt += ("<br><b>Discord:</b> Das <i>Ausgabegerät</i> in Discord muss dein Kopfhörer sein, nur das "
                "<i>Eingabegerät</i> ist CABLE Output – sonst hören deine Freunde sich selbst als Echo.")
    return txt


class SettingsTab(QWidget):
    CATEGORIES = [("allgemein", "Allgemein"), ("discord", "Discord & Freunde"), ("mikrofon", "Mikrofon"),
                  ("geraete", "Audio-Geräte"), ("clips", "Clips & Aufnahme"), ("soundboard", "Soundboard"),
                  ("hotkeys", "Hotkeys"), ("ueber", "Über Potato Clips")]

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("page")
        cfg = ctl.cfg
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 0)
        outer.setSpacing(14)
        head = QVBoxLayout()
        head.setSpacing(2)
        h = QLabel("Einstellungen")
        h.setObjectName("h1")
        sub = QLabel("Alles wird sofort gespeichert.")
        sub.setObjectName("sub")
        head.addWidget(h)
        head.addWidget(sub)
        outer.addLayout(head)
        body = QHBoxLayout()
        body.setSpacing(22)
        outer.addLayout(body, 1)

        # ---------------- Kategorien links
        nav = QVBoxLayout()
        nav.setSpacing(4)
        self.cat_buttons = {}
        for key, title in self.CATEGORIES:
            b = QPushButton(title.replace("&", "&&"))
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._goto(k))
            nav.addWidget(b)
            self.cat_buttons[key] = b
        nav.addStretch(1)
        navw = QWidget()
        navw.setLayout(nav)
        navw.setFixedWidth(184)
        body.addWidget(navw)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body.addWidget(self.scroll, 1)
        inner = QWidget()
        inner.setObjectName("page")
        self.scroll.setWidget(inner)
        self.root = QVBoxLayout(inner)
        self.root.setContentsMargins(0, 0, 14, 28)
        self.root.setSpacing(18)
        self.sections = {}
        self.scroll.verticalScrollBar().valueChanged.connect(self._sync_nav)

        # ================= Allgemein
        sec = self._section("allgemein", "Allgemein")
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(20, 14, 20, 16)
        bl.setSpacing(10)
        t = QLabel("Aussehen")
        t.setStyleSheet("font-weight: 700; background: transparent;")
        bl.addWidget(t)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.theme_btns = {}
        for key, title, desc in (("pro", "Profi", "Ruhig, dunkel, aufgeräumt"),
                                 ("potato", "Potato-Modus", "Laut, bunt, albern")):
            b = QPushButton(f"{title}\n{desc}")
            b.setObjectName("themecard")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(QIcon(_theme_preview(key)))
            b.setIconSize(QSize(96, 53))
            b.setMinimumHeight(80)
            b.setChecked(cfg.get("ui_theme", "pro") == key)
            b.clicked.connect(lambda _=False, k=key: self._set_theme(k))
            cards.addWidget(b, 1)
            self.theme_btns[key] = b
        bl.addLayout(cards)
        sec.addWidget(box)
        self.lang = QComboBox()
        for k, t in (("auto", "Automatisch (Windows)"), ("de", "Deutsch"), ("en", "English")):
            self.lang.addItem(t, k)
        self.lang.setCurrentIndex(max(0, self.lang.findData(cfg.get("language", "auto"))))
        self.lang.currentIndexChanged.connect(self._set_lang)
        self.lang.setMinimumWidth(200)
        self._row(sec, "Sprache", "Language", self.lang)
        self.auto = ToggleSwitch()
        self.auto.setChecked(autostart.is_enabled())
        self.auto.toggled.connect(self._autostart)
        self._row(sec, "Mit Windows starten", "Startet unsichtbar im Hintergrund", self.auto)
        self.tray = ToggleSwitch()
        self.tray.setChecked(cfg["minimize_to_tray"])
        self.tray.toggled.connect(lambda v: cfg.__setitem__("minimize_to_tray", v))
        self._row(sec, "Beim Schließen im Hintergrund weiterlaufen",
                  "Clips und Hotkeys funktionieren weiter, Symbol unten rechts", self.tray)
        self.ov = ToggleSwitch()
        self.ov.setChecked(cfg["overlay_enabled"])
        self.ov.toggled.connect(self._overlay)
        self.corner = QComboBox()
        for k, t in (("top-right", "Oben rechts"), ("top-left", "Oben links"), ("bottom-right", "Unten rechts"),
                     ("bottom-left", "Unten links")):
            self.corner.addItem(t, k)
        self.corner.setCurrentIndex(max(0, self.corner.findData(cfg["overlay_corner"])))
        self.corner.currentIndexChanged.connect(self._corner)
        self._row(sec, "Overlay im Spiel", "Zeigt Aufnahme, laufende Sounds und Meldungen", [self.corner, self.ov])

        # ================= Discord & Freunde
        sec = self._section("discord", "Discord & Freunde")
        chips = QWidget()
        cl = QHBoxLayout(chips)
        cl.setContentsMargins(20, 14, 20, 14)
        cl.setSpacing(10)
        self.chip_cable, self.chip_vol, self.chip_intr = QLabel(), QLabel(), QLabel()
        for c in (self.chip_cable, self.chip_vol, self.chip_intr):
            c.setObjectName("chip_ok")
            cl.addWidget(c, 1)
        self.cable_btn = QPushButton("VB-Cable installieren")
        self.cable_btn.clicked.connect(lambda: __import__("webbrowser").open("https://vb-audio.com/Cable/"))
        self.cable_btn.hide()
        cl.addWidget(self.cable_btn)
        sec.addWidget(chips)
        self.virtual = QComboBox()
        self.virtual.setMinimumWidth(240)
        self.virtual.setMaximumWidth(340)
        self._row(sec, "Virtuelles Mikrofon", "In Discord als Eingabe „CABLE Output“ wählen", self.virtual)
        info = QWidget()
        il = QVBoxLayout(info)
        il.setContentsMargins(20, 0, 20, 12)
        il.setSpacing(8)
        self.virt_status = QLabel()
        self.virt_status.setWordWrap(True)
        self.virt_status.setTextFormat(Qt.RichText)
        il.addWidget(self.virt_status)
        vol_row = QHBoxLayout()
        self.vol_warn = QLabel()
        self.vol_warn.setWordWrap(True)
        self.vol_warn.setTextFormat(Qt.RichText)
        self.vol_btn = QPushButton("Auf 100 % stellen")
        self.vol_btn.clicked.connect(self._fix_volumes)
        vol_row.addWidget(self.vol_warn, 1)
        vol_row.addWidget(self.vol_btn)
        il.addLayout(vol_row)
        self.vol_warn.hide()
        self.vol_btn.hide()
        self._low_devices = []
        hint_box = QFrame()
        hint_box.setObjectName("hintbox")
        hl = QVBoxLayout(hint_box)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(4)
        self.hint_top = QLabel()
        self.hint_dev = QLabel()
        self.hint_dev.setStyleSheet("font-size: 12pt; font-weight: 700; background: transparent;")
        self.hint_dev.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.hint_bottom = QLabel()
        for w in (self.hint_top, self.hint_dev, self.hint_bottom):
            w.setWordWrap(True)
            w.setTextFormat(Qt.RichText)
            hl.addWidget(w)
        il.addWidget(hint_box)
        self.intruder = QLabel()
        self.intruder.setObjectName("intruder")
        self.intruder.setWordWrap(True)
        self.intruder.setTextFormat(Qt.RichText)
        self.intruder.hide()
        il.addWidget(self.intruder)
        sec.addWidget(info)
        self.pass_cb = ToggleSwitch()
        self.pass_cb.setChecked(cfg["mic_passthrough"])
        self.pass_cb.toggled.connect(self._passthrough)
        self._row(sec, "Meine Stimme mitschicken", "Mikrofon geht mit Effekt an Discord", self.pass_cb)
        self.pass_gain = QSlider(Qt.Horizontal)
        self.pass_gain.setRange(0, 200)
        self.pass_gain.setValue(int(cfg["mic_passthrough_gain"] * 100))
        self.pass_gain.setFixedWidth(200)
        self.pass_gain_lbl = QLabel(f"{self.pass_gain.value()} %")
        self.pass_gain_lbl.setFixedWidth(46)
        self.pass_gain.valueChanged.connect(lambda val: (cfg.__setitem__("mic_passthrough_gain", val / 100),
                                                         self.pass_gain_lbl.setText(f"{val} %")))
        self.pass_gain.sliderReleased.connect(lambda: ctl.mixer.apply_voice_path())
        self._row(sec, "Lautstärke der Stimme", None, [self.pass_gain, self.pass_gain_lbl])
        self.cable_meter = LevelMeter()
        self.cable_meter.setFixedWidth(180)
        self.test_btn = QPushButton("🔊  Test-Sound senden")
        self.test_btn.setToolTip("Spielt einen kurzen Ton NUR ins virtuelle Mikro – der Balken links muss ausschlagen")
        self.test_btn.clicked.connect(self._test_sound)
        self._row(sec, "Das hört Discord gerade", None, [self.cable_meter, self.test_btn])
        tips = QLabel("In Discord unter Sprache & Video: Rauschunterdrückung auf „Keine“, Echoentfernung aus, "
                      "Eingabeempfindlichkeit von Hand einstellen.")
        tips.setWordWrap(True)
        tips.setObjectName("muted")
        tw = QFrame()
        tw.setObjectName("row")
        tl = QVBoxLayout(tw)
        tl.setContentsMargins(20, 12, 20, 14)
        tl.addWidget(tips)
        sec.addWidget(tw)

        # ================= Mikrofon
        sec = self._section("mikrofon", "Mikrofon")
        self.mic = QComboBox()
        self.mic.setMinimumWidth(240)
        self.mic.setMaximumWidth(340)
        self._row(sec, "Mikrofon-Gerät", None, self.mic)
        self.clean_sw = ToggleSwitch()
        self.clean_sw.setChecked(cfg["clean_mic"])
        self.clean_sw.toggled.connect(self._clean)
        self._row(sec, "KI-Rauschfilter", "Entfernt Tastatur, Lüfter und Klicken", self.clean_sw)
        self.clean_strength = QSlider(Qt.Horizontal)
        self.clean_strength.setRange(0, 100)
        self.clean_strength.setValue(int(cfg["clean_strength"] * 100))
        self.clean_strength.setFixedWidth(200)
        self.clean_lbl = QLabel(f"{self.clean_strength.value()} %")
        self.clean_lbl.setFixedWidth(46)
        self.clean_strength.valueChanged.connect(lambda v: self.clean_lbl.setText(f"{v} %"))
        self.clean_strength.sliderReleased.connect(self._clean)
        self._row(sec, "Stärke des Filters", None, [self.clean_strength, self.clean_lbl])
        self.gate_sw = ToggleSwitch()
        self.gate_sw.setChecked(cfg["clean_gate"])
        self.gate_sw.toggled.connect(self._clean)
        self._row(sec, "Stille zwischen Sätzen", "Dämpft Geräusche, wenn du nicht sprichst", self.gate_sw)

        # ================= Audio-Geraete
        sec = self._section("geraete", "Audio-Geräte")
        self.monitor = QComboBox()
        self.monitor.setMinimumWidth(240)
        self.monitor.setMaximumWidth(340)
        b = QPushButton("Neu laden")
        b.clicked.connect(self._fill_devices)
        self._row(sec, "Ich höre über", "Folgt automatisch, wenn du in Windows wechselst", [self.monitor, b])

        # ================= Clips & Aufnahme
        sec = self._section("clips", "Clips & Aufnahme")
        segw = QWidget()
        sl = QHBoxLayout(segw)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(4)
        self.len_btns = {}
        for v, t in ((15, "15 s"), (30, "30 s"), (60, "1 min"), (120, "2 min"), (300, "5 min")):
            b = QPushButton(t)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setChecked(int(cfg["buffer_seconds"]) == v)
            b.clicked.connect(lambda _=False, val=v: self._buffer(val))
            sl.addWidget(b)
            self.len_btns[v] = b
        self._row(sec, "Clip-Länge", "So viel wird beim Clippen rückwirkend gespeichert", segw)
        self.ignore = QLineEdit(", ".join(cfg["ignore_apps"]))
        self.ignore.setPlaceholderText("z. B. spotify.exe, chrome.exe")
        self.ignore.setMinimumWidth(240)
        self.ignore.editingFinished.connect(self._ignore)
        self._row(sec, "Apps nie aufnehmen", "Diese Apps tauchen nirgends auf", self.ignore)
        self.autocopy = ToggleSwitch()
        self.autocopy.setChecked(cfg["clip_autocopy"])
        self.autocopy.toggled.connect(lambda v: cfg.__setitem__("clip_autocopy", v))
        self._row(sec, "Neue Clips sofort kopieren",
                  "Nach dem Clippen liegt der Clip als MP3 in der Zwischenablage – in Discord Strg+V", self.autocopy)
        b = QPushButton("Ordner öffnen")
        b.clicked.connect(lambda: subprocess.Popen(["explorer", str(DATA_DIR)]))
        self._row(sec, "Speicherort", str(DATA_DIR), b)

        # ================= Soundboard
        sec = self._section("soundboard", "Soundboard")
        self.retrig = QComboBox()
        for k, t in (("restart", "Sound startet von vorne"), ("stop", "Sound stoppt (an/aus)"),
                     ("overlap", "Sound wird nochmal drübergelegt")):
            self.retrig.addItem(t, k)
        self.retrig.setCurrentIndex(max(0, self.retrig.findData(cfg["retrigger"])))
        self.retrig.currentIndexChanged.connect(lambda _: cfg.__setitem__("retrigger", self.retrig.currentData()))
        self.retrig.setMinimumWidth(220)
        self._row(sec, "Wenn ein Sound nochmal gedrückt wird", None, self.retrig)
        self.duck = ToggleSwitch()
        self.duck.setChecked(cfg["duck_enabled"])
        self.duck.toggled.connect(lambda v: cfg.__setitem__("duck_enabled", v))
        self._row(sec, "Andere Apps leiser, wenn ein Sound läuft",
                  "Spiel und Musik werden kurz leiser, damit du den Sound gut hörst", self.duck)
        self.duck_level = QSlider(Qt.Horizontal)
        self.duck_level.setRange(0, 80)
        self.duck_level.setValue(int(float(cfg["duck_level"]) * 100))
        self.duck_level.setFixedWidth(200)
        self.duck_lbl = QLabel(f"{self.duck_level.value()} %")
        self.duck_lbl.setFixedWidth(46)
        self.duck_level.valueChanged.connect(lambda v: (cfg.__setitem__("duck_level", v / 100),
                                                        self.duck_lbl.setText(f"{v} %")))
        self._row(sec, "So laut bleiben die anderen Apps", None, [self.duck_level, self.duck_lbl])
        self.duck_dc = ToggleSwitch()
        self.duck_dc.setChecked(cfg["duck_discord"])
        self.duck_dc.toggled.connect(lambda v: cfg.__setitem__("duck_discord", v))
        self._row(sec, "Auch Discord leiser machen", "Aus = deine Freunde bleiben immer gleich laut", self.duck_dc)
        self.soundboard_section = sec

        # ================= Hotkeys
        sec = self._section("hotkeys", "Hotkeys")
        gw = QWidget()
        g = QGridLayout(gw)
        g.setContentsMargins(20, 12, 20, 12)
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(8)
        self.hk_edits = {}
        for i, (action, label) in enumerate(ACTION_NAMES.items()):
            e = HotkeyEdit(cfg["hotkeys"].get(action, ""))
            e.setMinimumWidth(150)
            e.changed.connect(lambda combo, a=action: self._hotkey(a, combo))
            self.hk_edits[action] = e
            lab = QLabel(label)
            g.addWidget(lab, i, 0)
            g.addWidget(e, i, 1)
        sec.addWidget(gw)
        hint = QLabel("Sound-Hotkeys legst du im Soundboard fest (Rechtsklick auf einen Sound).\n"
                      "Läuft ein Spiel als Administrator, Potato Clips auch als Administrator starten.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        hw = QFrame()
        hw.setObjectName("row")
        hwl = QVBoxLayout(hw)
        hwl.setContentsMargins(20, 12, 20, 14)
        hwl.addWidget(hint)
        sec.addWidget(hw)

        # ================= Ueber
        sec = self._section("ueber", "Über Potato Clips")
        from .. import __version__
        self.update_btn = QPushButton("Nach Updates suchen")
        self.update_btn.clicked.connect(self._check_updates)
        gh = QPushButton("GitHub")
        gh.clicked.connect(lambda: __import__("webbrowser").open("https://github.com/swulfen13/potato-clips"))
        self._row(sec, "Potato Clips", tr_text(f"Version {__version__} · Open Source (MIT) · alles bleibt auf deinem PC"),
                  [self.update_btn, gh])
        self.upd_auto = ToggleSwitch()
        self.upd_auto.setChecked(cfg["update_check"])
        self.upd_auto.toggled.connect(lambda v: cfg.__setitem__("update_check", v))
        self._row(sec, "Automatisch nach Updates schauen", "Einmal am Tag, nur eine kurze Anfrage an GitHub",
                  self.upd_auto)
        wiz = QPushButton("Einrichtung starten")
        wiz.clicked.connect(self._run_wizard)
        self._row(sec, "Einrichtungs-Assistent", "VB-Cable, Discord und Mikro Schritt für Schritt", wiz)
        self.about_section = sec
        self.root.addStretch(1)

        self._probe = None
        self._probe_timer = QTimer(self)
        self._probe_timer.timeout.connect(self._probe_tick)
        self._fill_devices()
        self.mic.currentIndexChanged.connect(self._mic)
        self.monitor.currentIndexChanged.connect(self._outputs)
        self.virtual.currentIndexChanged.connect(self._outputs)
        ctl.settingsChanged.connect(self._sync)
        ctl.overlayToggled.connect(lambda v: (self.ov.blockSignals(True), self.ov.setChecked(v),
                                              self.ov.blockSignals(False)))
        self.cat_buttons["allgemein"].setChecked(True)

    # ---- Aufbau-Helfer
    def _section(self, key, title):
        f = QFrame()
        f.setObjectName("section")
        hard_shadow(f)
        v = QVBoxLayout(f)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        h = QLabel(title)
        h.setObjectName("h2")
        h.setContentsMargins(20, 14, 20, 12)
        v.addWidget(h)
        self.root.addWidget(f)
        self.sections[key] = f
        return v

    def _row(self, sec, label, desc=None, controls=None):
        row = QFrame()
        row.setObjectName("row")
        h = QHBoxLayout(row)
        h.setContentsMargins(20, 12, 20, 12)
        h.setSpacing(12)
        txt = QVBoxLayout()
        txt.setSpacing(1)
        lab = QLabel(label)
        lab.setStyleSheet("font-weight: 600; background: transparent;")
        txt.addWidget(lab)
        if desc:
            d = QLabel(desc)
            d.setObjectName("sub")
            d.setWordWrap(True)
            txt.addWidget(d)
        h.addLayout(txt, 1)
        if controls is not None:
            for c in (controls if isinstance(controls, list) else [controls]):
                h.addWidget(c, 0, Qt.AlignVCenter)
        sec.addWidget(row)
        return row

    def _goto(self, key):
        w = self.sections.get(key)
        if w is not None:
            self.cat_buttons[key].setChecked(True)
            self._jumping = True
            self.scroll.verticalScrollBar().setValue(w.y())
            QTimer.singleShot(200, lambda: setattr(self, "_jumping", False))

    def _sync_nav(self, value):
        if getattr(self, "_jumping", False):
            return
        cur = None
        for key, w in self.sections.items():
            if w.y() <= value + 40:
                cur = key
        if self.scroll.verticalScrollBar().value() >= self.scroll.verticalScrollBar().maximum() - 4:
            cur = list(self.sections)[-1]
        if cur and not self.cat_buttons[cur].isChecked():
            self.cat_buttons[cur].setChecked(True)

    # ---- Aussehen / Sprache
    def _set_theme(self, key):
        if self.ctl.cfg.get("ui_theme", "pro") == key:
            return
        self.ctl.cfg["ui_theme"] = key
        self._ask_restart()

    def _set_lang(self, _i):
        val = self.lang.currentData()
        if self.ctl.cfg.get("language", "auto") == val:
            return
        self.ctl.cfg["language"] = val
        self._ask_restart()

    def _ask_restart(self):
        r = QMessageBox.question(self, "Neustart nötig",
                                 "Potato Clips startet kurz neu, damit das neue Aussehen bzw. die neue Sprache "
                                 "überall greift. Jetzt neu starten?")
        if r == QMessageBox.Yes:
            from .restart import restart_app
            restart_app()

    def _buffer(self, v):
        if v == self.ctl.cfg["buffer_seconds"]:
            return
        if self.ctl.sources.recording:
            self.len_btns.get(int(self.ctl.cfg["buffer_seconds"]), self.len_btns[30]).setChecked(True)
            self.ctl.toast.emit("Während einer Aufnahme kann die Clip-Länge nicht geändert werden", "warn")
            return
        self.ctl.cfg["buffer_seconds"] = v
        self.ctl.sources.rebuild()
        self.ctl.settingsChanged.emit()
        self.ctl.toast.emit(f"Clip-Länge: {v} Sekunden (Puffer startet neu)", "info")

    def _check_updates(self):
        self.ctl.toast.emit("Suche nach Updates …", "info")
        self.ctl.check_updates(auto=False)

    def _run_wizard(self):
        from .wizard import SetupWizard
        SetupWizard(self.ctl, self.window()).exec()

    # ------------------------------------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        if self.mic.count() <= 1:
            self._fill_devices()
        self._update_virtual_info()
        self._start_probe()
        self._probe_timer.start(60)

    def hideEvent(self, e):
        super().hideEvent(e)
        self._probe_timer.stop()
        self._stop_probe()

    # ---- Discord-Bereich
    def _cable_capture(self):
        m = self.ctl.mixer
        name = m.devices.get("virtual", "") if m.is_open("virtual") else m.virtual_device_name()
        try:
            caps = self.ctl.sources.devices.get("capture") or run_helper_list().get("capture", [])
        except Exception:
            caps = []
        return name, find_cable_capture(caps, name)

    def _update_virtual_info(self):
        m = self.ctl.mixer
        name, cap = self._cable_capture()
        if not self.chip_intr.text():
            self._set_chip(self.chip_intr, True, "Keine fremden Apps im Kabel", "Andere Apps im Kabel")
        self._set_chip(self.chip_cable, bool(find_cable_device(self.ctl.sources.devices.get("render") or None)),
                       "VB-Cable gefunden", "Kein VB-Cable gefunden")
        self.cable_btn.setVisible(self.chip_cable.objectName() == "chip_bad")
        if self.ctl.cfg["virtual_device"] == "":
            self.virt_status.setText(f"<span style='color:{P['muted']}'>" + tr_text("Aus – Sounds hörst nur du.") + "</span>")
            self._hint("Wähle oben <b>CABLE Input</b>, damit deine Freunde die Sounds hören.", "", "")
            return
        if m.is_open("virtual"):
            self.virt_status.setText(f"<span style='color:{GREEN}'>● Verbunden:</span> Sounds gehen an <b>{name}</b>")
        else:
            err = m.errors.get("virtual") or "nicht verbunden"
            self.virt_status.setText(f"<span style='color:{RED}'>● Fehler:</span> {err}. "
                                     "Wähle <b>CABLE Input (VB-Audio Virtual Cable)</b>.")
        self._check_volumes(cap)
        if cap:
            self._hint("In <b>Discord → Einstellungen → Sprache &amp; Video → Eingabegerät</b> auswählen:",
                       f"🎙  {cap['name']}",
                       "Ausgabegerät in Discord bleibt dein Kopfhörer/Lautsprecher – <b>nicht</b> das Kabel.")
        else:
            self._hint("In Discord als Eingabegerät das <b>Output</b>-Ende des gewählten Kabels wählen:", "CABLE Output",
                       "")

    def _check_volumes(self, cap):
        """Windows-Lautstaerke des Kabels pruefen (zu leise / stumm -> Freunde hoeren kaum etwas)."""
        devs = self.ctl.sources.devices
        low = []
        vid = self.ctl.mixer.device_id("virtual")
        for d in devs.get("render", []):
            if d["id"] == vid:
                low.append(d)
        if cap:
            for d in devs.get("capture", []):
                if d["id"] == cap["id"]:
                    low.append(d)
        low = [d for d in low if d.get("muted") or 0 <= float(d.get("volume", 1)) < 0.9]
        self._low_devices = low
        if low:
            parts = [f"<b>{d['name']}</b> ({'stumm' if d.get('muted') else str(int(float(d['volume']) * 100)) + ' %'})"
                     for d in low]
            self.vol_warn.setText(f"<span style='color:{RED}'>⚠</span> In Windows zu leise eingestellt: "
                                  + ", ".join(parts) + " – deine Freunde hören dich dann kaum.")
        self.vol_warn.setVisible(bool(low))
        self.vol_btn.setVisible(bool(low))
        self._set_chip(self.chip_vol, not low, "Lautstärke auf 100 %", "Lautstärke zu niedrig")

    def _fix_volumes(self):
        from ..capture import CREATE_NO_WINDOW
        from ..config import HELPER
        for d in self._low_devices:
            try:
                subprocess.run([str(HELPER), "setvolume", d["id"], "1.0"], timeout=5, creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass
        self.ctl.sources.poke()
        self.ctl.toast.emit("Lautstärke des virtuellen Kabels auf 100 % gestellt", "ok")
        self.vol_warn.hide()
        self.vol_btn.hide()
        QTimer.singleShot(4000, self._update_virtual_info)

    def _set_chip(self, lbl, ok, good, bad):
        name = "chip_ok" if ok else "chip_bad"
        lbl.setText(("✓  " if ok else "✕  ") + tr_text(good if ok else bad))
        if lbl.objectName() != name:
            lbl.setObjectName(name)
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    def _hint(self, top, dev, bottom):
        self.hint_top.setText(top)
        self.hint_dev.setText(dev)
        self.hint_dev.setVisible(bool(dev))
        self.hint_bottom.setText(bottom)
        self.hint_bottom.setVisible(bool(bottom))

    def _start_probe(self):
        self._stop_probe()
        _, cap = self._cable_capture()
        if cap:
            try:
                self._probe = LevelProbe(cap["id"])
            except Exception:
                self._probe = None

    def _stop_probe(self):
        if self._probe is not None:
            self._probe.stop()
            self._probe = None

    def _probe_tick(self):
        p = self._probe
        self.cable_meter.push(p.take() if p is not None and p.alive else 0.0)
        self._ticks = getattr(self, "_ticks", 0) + 1
        if self._ticks % 15 == 0:
            txt = intruder_text(self.ctl)
            if txt != self.intruder.text():
                self.intruder.setText(txt)
            self.intruder.setVisible(bool(txt))
            self._set_chip(self.chip_intr, not txt, "Keine fremden Apps im Kabel", "Andere Apps im Kabel")

    def _test_sound(self):
        if not self.ctl.mixer.is_open("virtual"):
            self.ctl.toast.emit("Virtuelles Mikro nicht verbunden – oben CABLE Input wählen", "warn")
            return
        t = np.arange(int(0.9 * 48000)) / 48000
        env = np.minimum(1, t * 40) * np.exp(-t * 3)
        tone = 0.35 * env * (np.sin(2 * np.pi * 660 * t) + 0.5 * np.sin(2 * np.pi * 990 * t))
        data = np.repeat(tone[:, None], 2, axis=1).astype(np.float32)
        self.ctl.mixer.play(data, sound_id="__test__", name="Test", targets=["virtual"])
        self.ctl.toast.emit("Test-Sound an Discord gesendet", "info")

    def _fill_devices(self):
        cfg = self.ctl.cfg
        for cb in (self.mic, self.monitor, self.virtual):
            cb.blockSignals(True)
            cb.clear()
        self.mic.addItem("Windows-Standard", "default")
        for d in self.ctl.sources.devices.get("capture", []):
            self.mic.addItem(d["name"], d["id"])
        self.mic.setCurrentIndex(max(0, self.mic.findData(cfg["mic_device"])))

        outs = list_output_devices()
        self.monitor.addItem("Windows-Standard (folgt automatisch)", "")
        for n in outs:
            self.monitor.addItem(n, n)
        self.monitor.setCurrentIndex(max(0, self.monitor.findData(cfg["monitor_device"])))

        cable = find_cable_device()
        self.virtual.addItem("Automatisch" + (f" – {cable}" if cable else " (kein virtuelles Kabel gefunden)"), "auto")
        self.virtual.addItem("Aus (nur ich höre die Sounds)", "")
        for n in outs:
            self.virtual.addItem(n + ("   ← empfohlen" if n == cable else ""), n)
        self.virtual.setCurrentIndex(max(0, self.virtual.findData(cfg["virtual_device"])))
        for cb in (self.mic, self.monitor, self.virtual):
            cb.blockSignals(False)

    def _mic(self):
        self.ctl.cfg["mic_device"] = self.mic.currentData()
        self.ctl.mixer.apply_voice_path()
        if not self.ctl.sources.rebuild():
            self.ctl.toast.emit("Mikro wird nach der laufenden Aufnahme gewechselt", "warn")
            self.ctl.sources.poke()

    def _outputs(self):
        self.ctl.cfg.update(monitor_device=self.monitor.currentData(), virtual_device=self.virtual.currentData())
        self.ctl.mixer.reopen()
        m = self.ctl.mixer
        for t, name in (("monitor", "Kopfhörer-Ausgabe"), ("virtual", "Virtuelles Mikro")):
            if m.errors[t] and not (t == "virtual" and self.ctl.cfg["virtual_device"] == ""):
                self.ctl.toast.emit(f"{name}: {m.errors[t]}", "warn")
        QTimer.singleShot(700, self._after_output_change)

    def _after_output_change(self):
        self._update_virtual_info()
        if self.isVisible():
            self._start_probe()

    def _passthrough(self, v):
        self.ctl.cfg["mic_passthrough"] = v
        self.ctl.mixer.live.clear()
        self.ctl.mixer.apply_voice_path()
        self.ctl.sources.poke()
        self.ctl.settingsChanged.emit()
        if v and not self.ctl.mixer.is_open("virtual"):
            self.ctl.toast.emit("Kein virtuelles Mikro aktiv – bitte oben auswählen", "warn")

    def _hotkey(self, action, combo):
        self.ctl.set_action_hotkey(action, combo)

    def _overlay(self, v):
        self.ctl.cfg["overlay_enabled"] = v
        self.ctl.overlayToggled.emit(v)

    def _corner(self):
        self.ctl.cfg["overlay_corner"] = self.corner.currentData()
        self.ctl.overlayToggled.emit(self.ctl.cfg["overlay_enabled"])

    def _ignore(self):
        items = [x.strip().lower() for x in self.ignore.text().split(",") if x.strip()]
        items = [x if x.endswith(".exe") else x + ".exe" for x in items]
        self.ctl.cfg["ignore_apps"] = items
        self.ignore.setText(", ".join(items))
        self.ctl.sources.poke()

    def _clean(self, *_):
        self.ctl.cfg.update(clean_mic=self.clean_sw.isChecked(), clean_gate=self.gate_sw.isChecked(),
                            clean_strength=self.clean_strength.value() / 100)
        self.ctl.mixer.apply_clean()
        self.ctl.settingsChanged.emit()
        if self.clean_sw.isChecked() and self.ctl.mixer.cleaner is None:
            self.ctl.toast.emit("KI-Rauschfilter nicht gefunden (bin\\rnnoise.dll fehlt)", "warn")

    def _autostart(self, on):
        try:
            autostart.enable() if on else autostart.disable()
            self.ctl.toast.emit("Autostart eingeschaltet" if on else "Autostart ausgeschaltet", "ok")
        except Exception as e:
            self.auto.blockSignals(True)
            self.auto.setChecked(autostart.is_enabled())
            self.auto.blockSignals(False)
            self.ctl.toast.emit(f"Autostart fehlgeschlagen: {e}", "warn")

    def _sync(self):
        b = self.len_btns.get(int(self.ctl.cfg["buffer_seconds"]))
        if b is not None and not b.isChecked():
            b.setChecked(True)
        self.ignore.setText(", ".join(self.ctl.cfg["ignore_apps"]))
        for w, key in ((self.clean_sw, "clean_mic"), (self.gate_sw, "clean_gate")):
            if w.isChecked() != bool(self.ctl.cfg[key]):
                w.blockSignals(True)
                w.setChecked(bool(self.ctl.cfg[key]))
                w.blockSignals(False)
        for action, e in self.hk_edits.items():
            want = self.ctl.cfg["hotkeys"].get(action, "")
            if e.combo() != want:
                e.set_combo(want)
        self.pass_cb.blockSignals(True)
        self.pass_cb.setChecked(self.ctl.cfg["mic_passthrough"])
        self.pass_cb.blockSignals(False)
