from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QRadioButton, QScrollArea, QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from .widgets import GREEN, MUTED, RED, LevelMeter, ToggleSwitch, card

ICONS = {"mic": "🎙", "loopback": "🖥", "process": "🎮"}
KNOWN_ICONS = {"discord": "💬", "spotify": "🎵", "brave": "🌐", "chrome": "🌐", "firefox": "🌐", "msedge": "🌐",
               "opera": "🌐", "steam": "🎮", "teamspeak": "💬", "ts3client": "💬", "vlc": "🎬", "obs": "🎥",
               "whatsapp": "💬", "audacity": "🎧", "claude": "✳"}


def _icon(key: str, kind: str) -> str:
    if kind != "process":
        return ICONS.get(kind, "🎮")
    exe = key[4:].split("#")[0]
    for k, v in KNOWN_ICONS.items():
        if exe.startswith(k):
            return v
    return "🎮"


class SourceRow(QWidget):
    def __init__(self, key: str, info: dict, voice_apps=()):
        super().__init__()
        self.key = key
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.box = card()
        lay.addWidget(self.box)
        bl = QHBoxLayout(self.box)
        bl.setContentsMargins(16, 10, 12, 10)
        bl.setSpacing(14)
        ic = QLabel(_icon(key, info["kind"]))
        ic.setStyleSheet("font-size: 17pt; background: transparent;")
        ic.setFixedWidth(34)
        bl.addWidget(ic)
        txt = QVBoxLayout()
        txt.setSpacing(1)
        self.name = QLabel(info["label"])
        self.name.setStyleSheet("font-size: 10.5pt; font-weight: 600;")
        self.status = QLabel("–")
        self.status.setObjectName("sub")
        txt.addWidget(self.name)
        txt.addWidget(self.status)
        bl.addLayout(txt, 1)
        self.meter = LevelMeter()
        self.meter.setFixedWidth(170)
        bl.addWidget(self.meter)
        self.route = None
        self.route_gain = None
        exe = key[4:].split("#")[0] if key.startswith("app:") else ""
        if info["kind"] == "process" and exe.lower() not in voice_apps:
            col = QVBoxLayout()
            col.setSpacing(2)
            self.route = ToggleSwitch("→ Discord")
            self.route.setToolTip("Diese App zusätzlich ins virtuelle Mikro schicken – deine Freunde hören sie mit")
            self.route_gain = QSlider(Qt.Horizontal)
            self.route_gain.setRange(0, 150)
            self.route_gain.setFixedWidth(110)
            self.route_gain.setToolTip("Lautstärke für Discord")
            col.addWidget(self.route)
            col.addWidget(self.route_gain)
            bl.addLayout(col)
        self.clip = ToggleSwitch("Clippen")
        self.clip.setToolTip("Läuft im Hintergrund mit und landet in Clips")
        bl.addWidget(self.clip)
        self.rec = QCheckBox("Bei Aufnahme")
        self.rec.setToolTip("Wird vom Aufnahme-Hotkey mit aufgenommen (nichts angehakt = alle)")
        bl.addWidget(self.rec)
        self.rec_btn = QPushButton("●")
        self.rec_btn.setObjectName("round")
        self.rec_btn.setToolTip("Nur diese Quelle aufnehmen (nochmal klicken = stopp)")
        self.rec_btn.setCursor(Qt.PointingHandCursor)
        bl.addWidget(self.rec_btn)
        self.hide_btn = QToolButton()
        self.hide_btn.setText("✕")
        self.hide_btn.setToolTip("Diese App ausblenden (Einstellungen → Apps ignorieren)")
        self.hide_btn.setVisible(info["kind"] == "process")
        bl.addWidget(self.hide_btn)
        self._last = ("", "")


class SourcesTab(QWidget):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("page")
        self.rows: dict[str, SourceRow] = {}
        self._struct = None
        cfg = ctl.cfg

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(12)
        h = QLabel("Quellen & Aufnahme")
        h.setObjectName("h1")
        root.addWidget(h)
        sub = QLabel("Alles, was hier läuft, wird im Hintergrund mitgeschnitten. Beim Bearbeiten eines Clips "
                     "wählst du aus, welche Quellen zu hören sein sollen.")
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        root.addWidget(sub)

        opts = card()
        ol = QHBoxLayout(opts)
        ol.setContentsMargins(18, 14, 18, 14)
        ol.setSpacing(18)
        self.rb_all = QRadioButton("Alles mitschneiden")
        self.rb_sel = QRadioButton("Nur ausgewählte")
        grp = QButtonGroup(self)
        grp.addButton(self.rb_all)
        grp.addButton(self.rb_sel)
        (self.rb_all if cfg["capture_mode"] == "all" else self.rb_sel).setChecked(True)
        self.rb_all.toggled.connect(self._mode)
        ol.addWidget(self.rb_all)
        ol.addWidget(self.rb_sel)
        self.cb_system = ToggleSwitch("Gesamter Systemsound als Extra-Spur")
        self.cb_system.setChecked(cfg["capture_system"])
        self.cb_system.toggled.connect(lambda v: (cfg.__setitem__("capture_system", v), ctl.sources.poke()))
        ol.addWidget(self.cb_system)
        ol.addStretch(1)
        lbl = QLabel("Clip-Länge")
        lbl.setObjectName("muted")
        ol.addWidget(lbl)
        self.spin = QSpinBox()
        self.spin.setRange(5, 300)
        self.spin.setSuffix(" s")
        self.spin.setValue(int(cfg["buffer_seconds"]))
        self.spin.setFixedWidth(90)
        self.spin.editingFinished.connect(self._buffer)
        ol.addWidget(self.spin)
        root.addWidget(opts)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.inner.setObjectName("page")
        self.list_layout = QVBoxLayout(self.inner)
        self.list_layout.setContentsMargins(0, 0, 6, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.inner)
        root.addWidget(self.scroll, 1)

        bottom = card()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(16, 12, 16, 12)
        self.rec_btn = QPushButton()
        self.rec_btn.setObjectName("rec")
        self.rec_btn.setCursor(Qt.PointingHandCursor)
        self.rec_btn.clicked.connect(lambda: ctl.toggle_recording())
        self.rec_lbl = QLabel()
        self.rec_lbl.setObjectName("muted")
        clip = QPushButton("✂  Clip speichern")
        clip.setObjectName("accent")
        clip.setCursor(Qt.PointingHandCursor)
        clip.clicked.connect(lambda: ctl.clip_now())
        bl.addWidget(self.rec_btn)
        bl.addWidget(self.rec_lbl, 1)
        bl.addWidget(clip)
        root.addWidget(bottom)

        self._rec_state = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(80)

    # ------------------------------------------------------------------
    def _mode(self):
        self.ctl.cfg["capture_mode"] = "all" if self.rb_all.isChecked() else "selected"
        self.ctl.sources.poke()
        self._struct = None

    def _buffer(self):
        v = self.spin.value()
        if v == self.ctl.cfg["buffer_seconds"]:
            return
        if self.ctl.sources.recording:
            self.spin.setValue(self.ctl.cfg["buffer_seconds"])
            self.ctl.toast.emit("Während einer Aufnahme kann die Clip-Länge nicht geändert werden", "warn")
            return
        self.ctl.cfg["buffer_seconds"] = v
        self.ctl.sources.rebuild()
        self.ctl.toast.emit(f"Clip-Länge: {v} Sekunden (Puffer startet neu)", "info")

    def _sel_toggle(self, key, on):
        sel = set(self.ctl.cfg["selected_sources"])
        sel.add(key) if on else sel.discard(key)
        self.ctl.cfg["selected_sources"] = sorted(sel)
        self.ctl.sources.poke()

    def _rec_toggle(self, key, on):
        sel = set(self.ctl.cfg["record_sources"])
        sel.add(key) if on else sel.discard(key)
        self.ctl.cfg["record_sources"] = sorted(sel)

    def _route_toggle(self, key, on, row):
        routes = dict(self.ctl.cfg["route_sources"] or {})
        if on:
            routes[key] = row.route_gain.value() / 100 or 0.6
            if not self.ctl.mixer.is_open("virtual"):
                self.ctl.toast.emit("Kein virtuelles Mikro verbunden – Einstellungen → Discord / Freunde", "warn")
            else:
                self.ctl.toast.emit(f"→ Discord: {row.name.text()} wird jetzt an deine Freunde geschickt", "ok")
        else:
            routes.pop(key, None)
        self.ctl.cfg["route_sources"] = routes
        row.route_gain.setEnabled(on)
        self.ctl.mixer.prune_routes()
        self.ctl.sources.poke()

    def _route_gain(self, key, v):
        routes = dict(self.ctl.cfg["route_sources"] or {})
        if key in routes:
            routes[key] = v / 100
            self.ctl.cfg["route_sources"] = routes

    def _rec_one(self, key):
        if self.ctl.sources.recording:
            self.ctl.stop_recording()
        else:
            self.ctl.start_recording([key])

    def _hide(self, key, label):
        exe = key[4:].split("#")[0]
        if QMessageBox.question(self, "Ausblenden", f"„{label}“ ausblenden und nicht mehr mitschneiden?\n\n"
                                "Rückgängig: Einstellungen → Apps ignorieren.") != QMessageBox.Yes:
            return
        ign = list(self.ctl.cfg["ignore_apps"])
        if exe not in ign:
            ign.append(exe)
        self.ctl.cfg["ignore_apps"] = ign
        self.ctl.sources.poke()
        self.ctl.settingsChanged.emit()

    def _rebuild(self):
        avail = dict(self.ctl.sources.available)
        mode_all = self.ctl.cfg["capture_mode"] == "all"
        sel = set(self.ctl.cfg["selected_sources"])
        recsel = set(self.ctl.cfg["record_sources"])
        for r in self.rows.values():
            r.setParent(None)
            r.deleteLater()
        self.rows = {}
        for key, info in avail.items():
            row = SourceRow(key, info, self.ctl.voice_apps())
            row.clip.setChecked(mode_all or key in sel)
            row.clip.setEnabled(not mode_all)
            row.clip.toggled.connect(lambda v, k=key: self._sel_toggle(k, v))
            row.rec.setChecked(key in recsel)
            row.rec.toggled.connect(lambda v, k=key: self._rec_toggle(k, v))
            row.rec_btn.clicked.connect(lambda _=False, k=key: self._rec_one(k))
            row.hide_btn.clicked.connect(lambda _=False, k=key, l=info["label"]: self._hide(k, l))
            if row.route is not None:
                routes = self.ctl.cfg["route_sources"] or {}
                row.route.setChecked(key in routes)
                row.route_gain.setValue(int(float(routes.get(key, 0.6)) * 100))
                row.route_gain.setEnabled(key in routes)
                row.route.toggled.connect(lambda v, k=key, r=row: self._route_toggle(k, v, r))
                row.route_gain.valueChanged.connect(lambda v, k=key: self._route_gain(k, v))
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)
            self.rows[key] = row
        self._struct = (tuple(avail.keys()), mode_all)

    def _tick(self):
        if not self.isVisible():
            return
        src = self.ctl.sources
        if not src.helper_ok:
            self.rec_lbl.setText("⚠ bin\\audiocap.exe fehlt – bitte setup.bat ausführen")
            return
        if (tuple(src.available.keys()), self.ctl.cfg["capture_mode"] == "all") != self._struct:
            self._rebuild()
        snap = {k: (status, err, lvl, last, rec) for k, label, status, err, lvl, last, rec in src.snapshot()}
        now = time.time()
        for key, row in self.rows.items():
            s = snap.get(key)
            rec = False
            if s is None:
                txt, col = "aus – „Clippen“ einschalten, um mitzuschneiden", MUTED
                row.meter.push(0.0)
            else:
                status, err, lvl, last, rec = s
                if rec:
                    txt, col = "● nimmt auf", RED
                elif status == "läuft":
                    txt, col = ("♪ spielt gerade Ton" if now - last < 1.5 else "läuft – wartet auf Ton"), GREEN
                elif status == "Fehler":
                    txt, col = "Fehler" + (f": {err}" if err else ""), RED
                else:
                    txt, col = status, MUTED
                row.meter.push(lvl)
            if row._last != (txt, col):
                row.status.setText(txt)
                row.status.setStyleSheet(f"color:{col}; background: transparent;")
                row._last = (txt, col)
            want = f"background:{RED}; border-color:{RED}; color:white;" if rec else ""
            if row.rec_btn.styleSheet() != want:
                row.rec_btn.setStyleSheet(want)
        recording = src.recording is not None
        if recording != self._rec_state:
            self._rec_state = recording
            self.rec_btn.setText("■  Aufnahme stoppen" if recording else "●  Aufnahme starten")
            self.rec_btn.setProperty("recording", "true" if recording else "false")
            self.rec_btn.style().unpolish(self.rec_btn)
            self.rec_btn.style().polish(self.rec_btn)
        if recording:
            t = int(src.recording_seconds())
            self.rec_lbl.setText(f"Aufnahme läuft: {t // 60}:{t % 60:02d}")
        else:
            hk = self.ctl.hotkey_text("record")
            ck = self.ctl.hotkey_text("clip")
            self.rec_lbl.setText(f"Hotkeys: Aufnahme {hk or '–'}  ·  Clip {ck or '–'}")
