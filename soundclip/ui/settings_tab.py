from __future__ import annotations

import subprocess

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from ..config import DATA_DIR
from ..controller import ACTION_NAMES
from ..mixer import find_cable_device, list_output_devices
from .. import autostart
from ..capture import LevelProbe, run_helper_list
from ..mixer import find_cable_capture
from .widgets import GREEN, RED, HotkeyEdit, LevelMeter, ToggleSwitch


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
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("page")
        cfg = ctl.cfg
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget()
        inner.setObjectName("page")
        scroll.setWidget(inner)
        root = QVBoxLayout(inner)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(10)
        h = QLabel("Einstellungen")
        h.setObjectName("h1")
        root.addWidget(h)

        # ---------------- Discord / Freunde
        g = QGroupBox("🎮  Discord / Freunde – Sounds und Stimme ins Spiel/Discord schicken")
        v = QVBoxLayout(g)
        v.setSpacing(10)
        f = QFormLayout()
        f.setHorizontalSpacing(16)
        self.virtual = QComboBox()
        f.addRow("Ausgabe für Freunde", self.virtual)
        v.addLayout(f)
        self.virt_status = QLabel()
        self.virt_status.setWordWrap(True)
        self.virt_status.setTextFormat(Qt.RichText)
        v.addWidget(self.virt_status)
        vol_row = QHBoxLayout()
        self.vol_warn = QLabel()
        self.vol_warn.setWordWrap(True)
        self.vol_warn.setTextFormat(Qt.RichText)
        self.vol_btn = QPushButton("Auf 100 % stellen")
        self.vol_btn.clicked.connect(self._fix_volumes)
        vol_row.addWidget(self.vol_warn, 1)
        vol_row.addWidget(self.vol_btn)
        v.addLayout(vol_row)
        self.vol_warn.hide()
        self.vol_btn.hide()
        self._low_devices = []
        hint_box = QFrame()
        hint_box.setObjectName("hintbox")
        hint_box.setStyleSheet("QFrame#hintbox { background:#221d3d; border:1px solid #3a2f7a; border-radius:10px; }"
                               "QFrame#hintbox QLabel { background: transparent; }")
        hl = QVBoxLayout(hint_box)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(4)
        self.hint_top = QLabel()
        self.hint_dev = QLabel()
        self.hint_dev.setStyleSheet("font-size: 12pt; font-weight: 700; color: white; background: transparent;")
        self.hint_dev.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.hint_bottom = QLabel()
        self.hint_bottom.setStyleSheet("color:#b9b4e0; background: transparent;")
        for w in (self.hint_top, self.hint_dev, self.hint_bottom):
            w.setWordWrap(True)
            w.setTextFormat(Qt.RichText)
            hl.addWidget(w)
        v.addWidget(hint_box)
        self.pass_cb = ToggleSwitch("Meine Stimme mitschicken (Mikrofon → Discord, inkl. Stimmeffekt)")
        self.pass_cb.setChecked(cfg["mic_passthrough"])
        self.pass_cb.toggled.connect(self._passthrough)
        v.addWidget(self.pass_cb)
        clean_row = QHBoxLayout()
        clean_row.setSpacing(16)
        self.clean_sw = ToggleSwitch("🧹 Mikro sauber machen (KI-Rauschfilter)")
        self.clean_sw.setToolTip("Entfernt Lüfter, Tastatur, Rauschen und Brummen aus deiner Stimme – nur die Stimme, "
                                 "nicht die Sounds. Läuft lokal (RNNoise).")
        self.clean_sw.setChecked(cfg["clean_mic"])
        self.clean_sw.toggled.connect(self._clean)
        clean_row.addWidget(self.clean_sw)
        self.gate_sw = ToggleSwitch("Stille zwischen Sätzen")
        self.gate_sw.setToolTip("Wenn du nicht sprichst, wird das Mikro fast stumm (gegen Tastatur-Klackern)")
        self.gate_sw.setChecked(cfg["clean_gate"])
        self.gate_sw.toggled.connect(self._clean)
        clean_row.addWidget(self.gate_sw)
        clean_row.addStretch(1)
        v.addLayout(clean_row)
        f2 = QFormLayout()
        f2.setHorizontalSpacing(16)
        self.clean_strength = QSlider(Qt.Horizontal)
        self.clean_strength.setRange(0, 100)
        self.clean_strength.setValue(int(cfg["clean_strength"] * 100))
        self.clean_strength.sliderReleased.connect(self._clean)
        f2.addRow("Stärke Rauschfilter", self.clean_strength)
        self.pass_gain = QSlider(Qt.Horizontal)
        self.pass_gain.setRange(0, 200)
        self.pass_gain.setValue(int(cfg["mic_passthrough_gain"] * 100))
        self.pass_gain.valueChanged.connect(lambda val: cfg.__setitem__("mic_passthrough_gain", val / 100))
        self.pass_gain.sliderReleased.connect(lambda: ctl.mixer.apply_voice_path())
        f2.addRow("Lautstärke Stimme", self.pass_gain)
        meter_row = QHBoxLayout()
        self.cable_meter = LevelMeter()
        meter_row.addWidget(self.cable_meter, 1)
        self.test_btn = QPushButton("🔊  Test-Sound an Discord")
        self.test_btn.setToolTip("Spielt einen kurzen Ton NUR ins virtuelle Mikro – der Balken links muss ausschlagen")
        self.test_btn.clicked.connect(self._test_sound)
        meter_row.addWidget(self.test_btn)
        f2.addRow("Das hört Discord gerade", meter_row)
        v.addLayout(f2)
        self.intruder = QLabel()
        self.intruder.setWordWrap(True)
        self.intruder.setTextFormat(Qt.RichText)
        self.intruder.setStyleSheet("background:#3a1d26; border:1px solid #ff4d6d; border-radius:10px; "
                                    "padding:8px 12px; color:#ffd6de;")
        self.intruder.hide()
        v.addWidget(self.intruder)
        tips = QLabel("Tipps für Discord: Rauschunterdrückung (Krisp) und Echo-Unterdrückung ausschalten, sonst "
                      "werden Sounds weggefiltert. Mit Push-to-Talk kommen Sounds nur durch, solange die PTT-Taste "
                      "gedrückt ist – besser „Sprachaktivierung“ nutzen.")
        tips.setWordWrap(True)
        tips.setObjectName("muted")
        v.addWidget(tips)
        root.addWidget(g)

        # ---------------- Geraete
        g = QGroupBox("Audio-Geräte")
        f = QFormLayout(g)
        f.setHorizontalSpacing(16)
        self.mic = QComboBox()
        self.monitor = QComboBox()
        f.addRow("Mikrofon", self.mic)
        f.addRow("Ich höre über", self.monitor)
        b = QPushButton("Geräte neu laden")
        b.clicked.connect(self._fill_devices)
        f.addRow("", b)
        root.addWidget(g)

        # ---------------- Wiedergabe
        g = QGroupBox("Soundboard")
        f = QFormLayout(g)
        self.retrig = QComboBox()
        for k, t in (("restart", "Sound startet von vorne"), ("stop", "Sound stoppt (an/aus)"),
                     ("overlap", "Sound wird nochmal drübergelegt")):
            self.retrig.addItem(t, k)
        self.retrig.setCurrentIndex(max(0, self.retrig.findData(cfg["retrigger"])))
        self.retrig.currentIndexChanged.connect(lambda _: cfg.__setitem__("retrigger", self.retrig.currentData()))
        f.addRow("Wenn ein Sound nochmal gedrückt wird", self.retrig)
        root.addWidget(g)

        # ---------------- Hotkeys
        g = QGroupBox("Globale Hotkeys (funktionieren auch im Spiel)")
        f = QFormLayout(g)
        self.hk_edits = {}
        for action, label in ACTION_NAMES.items():
            e = HotkeyEdit(cfg["hotkeys"].get(action, ""))
            e.changed.connect(lambda combo, a=action: self._hotkey(a, combo))
            self.hk_edits[action] = e
            f.addRow(label, e)
        hint = QLabel("Sound-Hotkeys legst du im Soundboard fest (Rechtsklick auf einen Sound). "
                      "Hinweis: Läuft ein Spiel als Administrator, Potato Clips auch als Administrator starten.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        f.addRow(hint)
        root.addWidget(g)

        # ---------------- Overlay & Verhalten
        g = QGroupBox("Start, Overlay & Verhalten")
        f = QFormLayout(g)
        self.ov = ToggleSwitch("Mini-Overlay anzeigen (immer im Vordergrund, klick-durchlässig)")
        self.ov.setChecked(cfg["overlay_enabled"])
        self.ov.toggled.connect(self._overlay)
        f.addRow(self.ov)
        self.corner = QComboBox()
        for k, t in (("top-right", "Oben rechts"), ("top-left", "Oben links"), ("bottom-right", "Unten rechts"),
                     ("bottom-left", "Unten links")):
            self.corner.addItem(t, k)
        self.corner.setCurrentIndex(max(0, self.corner.findData(cfg["overlay_corner"])))
        self.corner.currentIndexChanged.connect(self._corner)
        f.addRow("Position", self.corner)
        self.auto = ToggleSwitch("Mit Windows starten (minimiert im Tray)")
        self.auto.setChecked(autostart.is_enabled())
        self.auto.toggled.connect(self._autostart)
        f.addRow(self.auto)
        self.tray = ToggleSwitch("Fenster schließen = im Hintergrund (Tray) weiterlaufen")
        self.tray.setChecked(cfg["minimize_to_tray"])
        self.tray.toggled.connect(lambda v: cfg.__setitem__("minimize_to_tray", v))
        f.addRow(self.tray)
        self.ignore = QLineEdit(", ".join(cfg["ignore_apps"]))
        self.ignore.setPlaceholderText("z. B. spotify.exe, chrome.exe")
        self.ignore.editingFinished.connect(self._ignore)
        f.addRow("Apps ignorieren", self.ignore)
        b = QPushButton("Datenordner öffnen")
        b.clicked.connect(lambda: subprocess.Popen(["explorer", str(DATA_DIR)]))
        f.addRow("", b)
        root.addWidget(g)
        root.addStretch(1)

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
        if self.ctl.cfg["virtual_device"] == "":
            self.virt_status.setText("<span style='color:#8b8fa3'>Aus – Sounds hörst nur du.</span>")
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
            self.ctl.toast.emit("Autostart " + ("eingeschaltet" if on else "ausgeschaltet"), "ok")
        except Exception as e:
            self.auto.blockSignals(True)
            self.auto.setChecked(autostart.is_enabled())
            self.auto.blockSignals(False)
            self.ctl.toast.emit(f"Autostart fehlgeschlagen: {e}", "warn")

    def _sync(self):
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
