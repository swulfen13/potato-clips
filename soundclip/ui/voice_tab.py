"""Seite 'Stimme': Live-Stimmverzerrer (Potato Mic, Roboter, Daemon ...)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QScrollArea, QSlider, QVBoxLayout, QWidget)

from ..effects import EFFECTS, VOICE_PRESETS, voice_name
from ..hotkeys import pretty
from .widgets import ACCENT, MUTED, RED, FlowLayout, HotkeyEdit, LevelMeter, ToggleSwitch, card

DESCRIPTIONS = {
    "potato": "Billiges Kartoffel-Mikro",
    "overdrive": "Viel zu laut eingestellt",
    "earrape": "Maximal übersteuert",
    "pitch_up": "Hohe Quietschstimme",
    "pitch_down": "Tief und brummig",
    "demon": "Tief, dreckig, mit Hall",
    "giant": "Riesig und dröhnend",
    "robot": "Metallisch wie ein Bot",
    "alien": "Außerirdisch schwebend",
    "ghost": "Hallig und unheimlich",
    "telephone": "Alter Telefonhörer",
    "radio": "Walkie-Talkie mit Rauschen",
    "megaphone": "Durch eine Flüstertüte",
    "phone": "Aus dem Handy-Lautsprecher",
    "stadium": "Ansage im Stadion",
    "underwater": "Blubbernd unter Wasser",
    "lofi": "Leiernde Kassette",
    "bitcrush": "Retro-Game-Konsole",
    "reverb": "In einer riesigen Kirche",
    "echo": "Rufen in den Bergen",
    "chorus": "Wie mehrere Leute",
    "vibrato": "Zitternde Stimme",
}


class PresetTile(QFrame):
    clicked = Signal(str)
    menuRequested = Signal(str, object)

    def __init__(self, key: str):
        super().__init__()
        self.key = key
        self.emoji = VOICE_PRESETS[key][0]
        self.name = voice_name(key)
        self.desc = DESCRIPTIONS.get(key, "")
        self.hotkey = ""
        self.active = False
        self.hover = False
        self.amount = 0.5
        self.setFixedSize(176, 118)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{self.name}\nKlick: einschalten / ausschalten · Rechtsklick: Hotkey")

    def set_state(self, active: bool, hotkey: str):
        if (active, hotkey) != (self.active, self.hotkey):
            self.active, self.hotkey = active, hotkey
            self.update()

    def set_amount(self, a: float):
        if abs(a - self.amount) > 0.001:
            self.amount = a
            self.update()

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.key)

    def contextMenuEvent(self, e):
        self.menuRequested.emit(self.key, e.globalPos())

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.active:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor("#7c5cff"))
            g.setColorAt(1, QColor("#c2477a"))
            p.setBrush(g)
            p.setPen(QPen(QColor("#b9a8ff"), 2))
        else:
            p.setBrush(QColor("#1d1f29") if self.hover else QColor("#181a22"))
            p.setPen(QPen(QColor(ACCENT) if self.hover else QColor("#272a36"), 1.5))
        p.drawRoundedRect(r, 14, 14)
        f = QFont(self.font())
        f.setPointSizeF(22)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(QRectF(r.left() + 12, r.top() + 6, 50, 44), Qt.AlignLeft | Qt.AlignVCenter, self.emoji)
        f.setPointSizeF(10.5)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(r.left() + 14, r.top() + 52, r.width() - 24, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   self.name)
        f.setBold(False)
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.setPen(QColor("#e6e0ff") if self.active else QColor(MUTED))
        p.drawText(QRectF(r.left() + 14, r.top() + 74, r.width() - 24, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(self.desc, Qt.ElideRight, int(r.width() - 24)))
        if self.hotkey:
            fm = p.fontMetrics()
            txt = pretty(self.hotkey)
            w = fm.horizontalAdvance(txt) + 14
            pill = QRectF(r.right() - w - 10, r.top() + 12, w, 20)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 100))
            p.drawRoundedRect(pill, 6, 6)
            p.setPen(QColor("#e6e6f0"))
            p.drawText(pill, Qt.AlignCenter, txt)
        # Staerke-Balken unten
        bar = QRectF(r.left() + 14, r.bottom() - 13, r.width() - 64, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 50) if self.active else QColor("#2b2f3c"))
        p.drawRoundedRect(bar, 2, 2)
        p.setBrush(QColor("white") if self.active else QColor(ACCENT))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * self.amount, bar.height()), 2, 2)
        f.setPointSizeF(8)
        p.setFont(f)
        p.setPen(QColor("white") if self.active else QColor(MUTED))
        p.drawText(QRectF(r.right() - 46, r.bottom() - 20, 38, 16), Qt.AlignRight | Qt.AlignVCenter,
                   f"{int(round(self.amount * 100))} %")


class HotkeyDialog(QDialog):
    def __init__(self, title: str, combo: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hotkey festlegen")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lab = QLabel(f"Hotkey für <b>{title}</b>:")
        lay.addWidget(lab)
        self.edit = HotkeyEdit(combo)
        lay.addWidget(self.edit)
        hint = QLabel("Einmal drücken = Effekt an, nochmal drücken = aus.")
        hint.setObjectName("muted")
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class VoiceTab(QWidget):
    openSettings = Signal()

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("page")
        cfg = ctl.cfg
        self.tiles: dict[str, PresetTile] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(12)
        h = QLabel("Stimme live verändern")
        h.setObjectName("h1")
        root.addWidget(h)
        sub = QLabel("Dein Mikrofon wird in Echtzeit verändert – deine Freunde in Discord hören es sofort. "
                     "Klick auf einen Effekt zum Einschalten, nochmal klicken zum Ausschalten.")
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # ---- Steuerung
        ctrl = card()
        cl = QVBoxLayout(ctrl)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(18)
        self.enable = ToggleSwitch("Stimmeffekt an")
        self.enable.setStyleSheet("font-size: 11pt; font-weight: 600;")
        self.enable.setChecked(cfg["voice_enabled"])
        self.enable.toggled.connect(lambda v: ctl.set_voice(enabled=v))
        row.addWidget(self.enable)
        self.current = QLabel()
        self.current.setStyleSheet("font-size: 12pt; font-weight: 700; background: transparent;")
        row.addWidget(self.current)
        row.addStretch(1)
        lbl = QLabel("Stärke:")
        lbl.setObjectName("muted")
        row.addWidget(lbl)
        self.amount = QSlider(Qt.Horizontal)
        self.amount.setRange(0, 100)
        self.amount.setFixedWidth(260)
        self.amount.setValue(int(ctl.voice_amount() * 100))
        self.amount.setToolTip("Wie stark der aktuelle Effekt ist – wird pro Effekt gemerkt")
        self.amount_lbl = QLabel(f"{self.amount.value()} %")
        self.amount_lbl.setFixedWidth(48)
        self.amount_lbl.setStyleSheet("font-weight: 700; background: transparent;")
        self._amount_timer = QTimer(self)
        self._amount_timer.setSingleShot(True)
        self._amount_timer.timeout.connect(self._apply_amount)
        self.amount.valueChanged.connect(self._amount_changed)
        weak = QLabel("schwach")
        weak.setObjectName("sub")
        strong = QLabel("stark")
        strong.setObjectName("sub")
        row.addWidget(weak)
        row.addWidget(self.amount)
        row.addWidget(strong)
        row.addWidget(self.amount_lbl)
        cl.addLayout(row)

        meters = QHBoxLayout()
        meters.setSpacing(12)
        a = QLabel("🎙 Mikro")
        a.setObjectName("muted")
        a.setFixedWidth(70)
        self.m_in = LevelMeter()
        b = QLabel("🎭 Mit Effekt")
        b.setObjectName("muted")
        b.setFixedWidth(90)
        self.m_out = LevelMeter()
        meters.addWidget(a)
        meters.addWidget(self.m_in, 1)
        meters.addSpacing(16)
        meters.addWidget(b)
        meters.addWidget(self.m_out, 1)
        cl.addLayout(meters)

        row2 = QHBoxLayout()
        row2.setSpacing(18)
        self.pass_sw = ToggleSwitch("An Discord schicken")
        self.pass_sw.setChecked(cfg["mic_passthrough"])
        self.pass_sw.toggled.connect(self._passthrough)
        row2.addWidget(self.pass_sw)
        self.clean = ToggleSwitch("🧹 Mikro sauber")
        self.clean.setToolTip("KI-Rauschfilter: entfernt Lüfter, Tastatur und Rauschen aus deiner Stimme")
        self.clean.setChecked(cfg["clean_mic"])
        self.clean.toggled.connect(self._clean)
        row2.addWidget(self.clean)
        self.mon = ToggleSwitch("Mich selbst hören (Kopfhörer!)")
        self.mon.setChecked(cfg["voice_monitor"])
        self.mon.toggled.connect(self._monitor)
        row2.addWidget(self.mon)
        lbl2 = QLabel("Lautstärke")
        lbl2.setObjectName("muted")
        row2.addWidget(lbl2)
        self.mon_gain = QSlider(Qt.Horizontal)
        self.mon_gain.setRange(0, 150)
        self.mon_gain.setFixedWidth(140)
        self.mon_gain.setValue(int(cfg["voice_monitor_gain"] * 100))
        self.mon_gain.valueChanged.connect(lambda v: cfg.__setitem__("voice_monitor_gain", v / 100))
        self.mon_gain.sliderReleased.connect(lambda: self.ctl.mixer.apply_voice_path())
        row2.addWidget(self.mon_gain)
        row2.addStretch(1)
        cl.addLayout(row2)

        self.warn = QLabel()
        self.warn.setWordWrap(True)
        self.warn.setTextFormat(Qt.RichText)
        self.warn_btn = QPushButton("Einstellungen öffnen")
        self.warn_btn.clicked.connect(self.openSettings.emit)
        wr = QHBoxLayout()
        wr.addWidget(self.warn, 1)
        wr.addWidget(self.warn_btn)
        cl.addLayout(wr)
        root.addWidget(ctrl)

        # ---- Effekt-Kacheln
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setObjectName("page")
        self.flow = FlowLayout(inner, 12)
        for key in VOICE_PRESETS:
            t = PresetTile(key)
            t.clicked.connect(self._tile_clicked)
            t.menuRequested.connect(self._tile_menu)
            self.flow.addWidget(t)
            self.tiles[key] = t
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        hk_card = card()
        outer_hl = QHBoxLayout(hk_card)
        outer_hl.setContentsMargins(16, 10, 16, 10)
        outer_hl.setSpacing(16)
        t = QLabel("⌨  Hotkeys")
        t.setStyleSheet("font-weight: 700; background: transparent;")
        outer_hl.addWidget(t)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.hk_edits = {}
        for i, (action, text) in enumerate((("voice_toggle", "Effekt an/aus"), ("voice_next", "Nächster Effekt"),
                                            ("voice_up", "Stärker (+10 %)"), ("voice_down", "Schwächer (−10 %)"))):
            l = QLabel(text)
            l.setObjectName("muted")
            e = HotkeyEdit(cfg["hotkeys"].get(action, ""))
            e.setMinimumWidth(210)
            e.changed.connect(lambda combo, a=action: ctl.set_action_hotkey(a, combo))
            r, c = divmod(i, 2)
            grid.addWidget(l, r, c * 2)
            grid.addWidget(e, r, c * 2 + 1)
            self.hk_edits[action] = e
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        outer_hl.addLayout(grid, 1)
        root.addWidget(hk_card)
        self.hk_lbl = QLabel()
        self.hk_lbl.setObjectName("sub")
        root.addWidget(self.hk_lbl)

        ctl.voiceChanged.connect(self._sync)
        ctl.settingsChanged.connect(self._sync)
        self._sync()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(60)

    # ------------------------------------------------------------------
    def _amount_changed(self, v):
        self.amount_lbl.setText(f"{v} %")
        self._amount_timer.start(60)       # live, aber nicht bei jedem Pixel neu bauen

    def _apply_amount(self):
        self.ctl.set_voice(amount=self.amount.value() / 100, quiet=True)

    def _tile_clicked(self, key):
        cfg = self.ctl.cfg
        if cfg["voice_enabled"] and cfg["voice_preset"] == key:
            self.ctl.set_voice(enabled=False)
        else:
            self.ctl.set_voice(key, True)

    def _tile_menu(self, key, pos):
        m = QMenu(self)
        a_on = m.addAction("Einschalten")
        a_hk = m.addAction("⌨ Hotkey festlegen…")
        a_clear = m.addAction("Hotkey entfernen")
        act = m.exec(pos)
        if act == a_on:
            self.ctl.set_voice(key, True)
        elif act in (a_hk, a_clear):
            hk = dict(self.ctl.cfg["voice_hotkeys"] or {})
            if act == a_hk:
                dlg = HotkeyDialog(voice_name(key), hk.get(key, ""), self)
                if not dlg.exec():
                    return
                combo = dlg.edit.combo()
            else:
                combo = ""
            if combo:
                hk[key] = combo
            else:
                hk.pop(key, None)
            self.ctl.cfg["voice_hotkeys"] = hk
            self.ctl.apply_hotkeys()
            self._sync()

    def _passthrough(self, v):
        self.ctl.cfg["mic_passthrough"] = v
        self.ctl.mixer.live.clear()
        self.ctl.mixer.apply_voice_path()
        self.ctl.sources.poke()
        self.ctl.settingsChanged.emit()

    def _clean(self, v):
        self.ctl.cfg["clean_mic"] = v
        self.ctl.mixer.apply_clean()
        self.ctl.settingsChanged.emit()

    def _monitor(self, v):
        self.ctl.cfg["voice_monitor"] = v
        self.ctl.mixer.live_mon.clear()
        self.ctl.mixer.apply_voice_path()
        self.ctl.sources.poke()
        if v:
            self.ctl.toast.emit("Mithören an – bitte Kopfhörer nutzen, sonst gibt es Rückkopplung", "info")

    def _sync(self):
        cfg = self.ctl.cfg
        for w, val in ((self.enable, cfg["voice_enabled"]), (self.pass_sw, cfg["mic_passthrough"]),
                       (self.mon, cfg["voice_monitor"]), (self.clean, cfg["clean_mic"])):
            if w.isChecked() != bool(val):
                w.blockSignals(True)
                w.setChecked(bool(val))
                w.blockSignals(False)
        hks = cfg["voice_hotkeys"] or {}
        for key, t in self.tiles.items():
            t.set_state(cfg["voice_enabled"] and cfg["voice_preset"] == key, hks.get(key, ""))
        pre = cfg["voice_preset"]
        name = f"{VOICE_PRESETS[pre][0]}  {voice_name(pre)}" if pre in VOICE_PRESETS else ""
        self.current.setText(name if cfg["voice_enabled"] else "–  aus")
        self.current.setStyleSheet("font-size: 12pt; font-weight: 700; background: transparent; color: %s;"
                                   % ("white" if cfg["voice_enabled"] else MUTED))
        self.hk_lbl.setText("Tipp: Rechtsklick auf einen Effekt = eigener Hotkey nur für diesen Effekt. "
                            "„Stärker/Schwächer“ ändert den gerade aktiven Effekt in 10-%-Schritten.")
        for action, e in self.hk_edits.items():
            want = cfg["hotkeys"].get(action, "")
            if e.combo() != want:
                e.set_combo(want)
        val = int(round(self.ctl.voice_amount() * 100))
        if self.amount.value() != val and not self.amount.isSliderDown():
            self.amount.blockSignals(True)
            self.amount.setValue(val)
            self.amount.blockSignals(False)
            self.amount_lbl.setText(f"{val} %")
        amts = cfg["voice_amounts"] or {}
        for key, t in self.tiles.items():
            t.set_amount(float(amts.get(key, 0.5)))

    def _tick(self):
        if not self.isVisible():
            return
        import time as _time
        a, b = self.ctl.mixer.take_voice_levels()
        now = _time.time()
        if not hasattr(self, "_shown_at") or now - getattr(self, "_last_tick", 0) > 1:
            self._shown_at = now
            self._last_sound = now
        self._last_tick = now
        if a > 0.0003:
            self._last_sound = now
        self.m_in.push(a)
        self.m_out.push(b)
        cfg = self.ctl.cfg
        m = self.ctl.mixer
        if not cfg["mic_passthrough"] and not cfg["voice_monitor"]:
            txt = (f"<span style='color:{RED}'>●</span> Deine Stimme geht gerade nirgendwo hin – "
                   "schalte <b>„An Discord schicken“</b> ein.")
            btn = False
        elif cfg["mic_passthrough"] and not m.is_open("virtual"):
            txt = (f"<span style='color:{RED}'>●</span> Kein virtuelles Mikro verbunden – in den Einstellungen "
                   "<b>CABLE Input</b> wählen.")
            btn = True
        elif cfg["mic_passthrough"]:
            txt = ("<span style='color:#2ec4b6'>●</span> Bereit – in Discord muss das Eingabegerät "
                   "<b>CABLE Output</b> sein.")
            btn = False
            self._n = getattr(self, "_n", 0) + 1
            if self._n % 15 == 0 or not hasattr(self, "_intr"):
                from .settings_tab import intruder_text
                self._intr = intruder_text(self.ctl)
            if self._intr:
                txt = self._intr
                btn = False
        else:
            txt = "Nur Mithören aktiv – Discord bekommt nichts."
            btn = False
        if (cfg["mic_passthrough"] or cfg["voice_monitor"]) and now - self._last_sound > 4:
            txt = (f"<span style='color:{RED}'>●</span> Dein Mikrofon liefert gerade nur Stille – ist es stummgeschaltet? "
                   "(Windows-Einstellungen → Sound → Eingabe, oder Mute-Taste am Mikro/Webcam)")
            btn = True
        if self.warn.text() != txt:
            self.warn.setText(txt)
        self.warn_btn.setVisible(btn)
