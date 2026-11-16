"""Seite 'Stimme': Live-Stimmverzerrer (Potato Mic, Roboter, Daemon ...)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QScrollArea, QSlider, QVBoxLayout, QWidget)

from ..effects import EFFECTS, VOICE_PRESETS, voice_name
from ..hotkeys import pretty
from . import theme
from .theme import P
from .widgets import ACCENT, MUTED, RED, FlowLayout, HotkeyEdit, LevelMeter, ToggleSwitch, card


def _lang() -> str:
    from .. import i18n
    return i18n.LANG

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
        self.desc = DESCRIPTIONS.get(key, "Eigener Effekt" if key.startswith("custom_") else "")
        self.hotkey = ""
        self.active = False
        self.hover = False
        self.amount = 0.5
        self.setFixedSize(184, 124) if theme.potato() else self.setFixedSize(176, 112)
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
        from ..i18n import tr
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        name, desc = tr(self.name), tr(self.desc)
        if theme.potato():
            self._paint_potato(p, name, desc)
            return
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.active:
            p.setBrush(QColor(P["accent_soft"]))
            p.setPen(QPen(QColor(P["accent"]), 1.5))
        else:
            p.setBrush(QColor(P["panel_hover"]) if self.hover else QColor(P["panel"]))
            p.setPen(QPen(QColor(P["border2"]) if self.hover else QColor(P["border"]), 1))
        p.drawRoundedRect(r, 10, 10)
        f = QFont(self.font())
        f.setPointSizeF(10.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(P["text"]))
        p.drawText(QRectF(r.left() + 14, r.top() + 12, r.width() - 28, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(name, Qt.ElideRight, int(r.width() - 28)))
        f.setBold(False)
        f.setPointSizeF(8.8)
        p.setFont(f)
        p.setPen(QColor(P["muted"]))
        p.drawText(QRectF(r.left() + 14, r.top() + 38, r.width() - 28, 34), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                   desc)
        if self.hotkey:
            fm = p.fontMetrics()
            txt = pretty(self.hotkey)
            w = fm.horizontalAdvance(txt) + 12
            pill = QRectF(r.right() - w - 10, r.bottom() - 34, w, 18)
            p.setPen(QPen(QColor(P["border2"]), 1))
            p.setBrush(QColor(P["panel2"]))
            p.drawRoundedRect(pill, 4, 4)
            p.setPen(QColor(P["text"]))
            p.drawText(pill, Qt.AlignCenter, txt)
        bar = QRectF(r.left() + 14, r.bottom() - 12, r.width() - 64, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(P["border"]))
        p.drawRoundedRect(bar, 1.5, 1.5)
        p.setBrush(QColor(P["accent"]) if self.active else QColor(P["wave_off"]))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * self.amount, bar.height()), 1.5, 1.5)
        f.setPointSizeF(8)
        p.setFont(f)
        p.setPen(QColor(P["text"]) if self.active else QColor(P["muted"]))
        p.drawText(QRectF(r.right() - 46, r.bottom() - 20, 36, 16), Qt.AlignRight | Qt.AlignVCenter,
                   f"{int(round(self.amount * 100))} %")

    def _paint_potato(self, p, name, desc):
        idx = list(VOICE_PRESETS).index(self.key) if self.key in VOICE_PRESETS else 0
        col = QColor(theme.POTATO_TILES[idx % len(theme.POTATO_TILES)])
        tilt = theme.POTATO_TILTS[idx % len(theme.POTATO_TILTS)] * (0.4 if self.hover else 1.0)
        w, h = self.width(), self.height()
        p.translate(w / 2, h / 2)
        p.rotate(tilt)
        p.translate(-w / 2, -h / 2)
        sh = 7 if self.active else 5
        r = QRectF(6, 6, w - 12 - sh, h - 12 - sh)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#111"))
        p.drawRect(r.translated(sh, sh))
        p.setBrush(col)
        p.setPen(QPen(QColor("#111"), 4.5 if self.active else 3))
        p.drawRect(r)
        f = QFont(self.font())
        f.setPointSizeF(17)
        p.setFont(f)
        p.drawText(QRectF(r.left() + 10, r.top() + 4, 40, 34), Qt.AlignLeft | Qt.AlignVCenter, self.emoji)
        f = QFont("Bungee")
        f.setPointSizeF(10)
        p.setFont(f)
        p.setPen(QColor("#111"))
        p.drawText(QRectF(r.left() + 10, r.top() + 38, r.width() - 20, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(name.upper(), Qt.ElideRight, int(r.width() - 20)))
        f = QFont("Comic Neue")
        f.setBold(True)
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.drawText(QRectF(r.left() + 10, r.top() + 58, r.width() - 20, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(desc, Qt.ElideRight, int(r.width() - 20)))
        txt = f"{int(round(self.amount * 100))} % " + ("bad" if _lang() == "en" else "schlimm")
        fm = p.fontMetrics()
        pill = QRectF(r.left() + 10, r.bottom() - 24, fm.horizontalAdvance(txt) + 12, 18)
        p.setPen(QPen(QColor("#111"), 2))
        p.setBrush(QColor("white"))
        p.drawRect(pill)
        p.drawText(pill, Qt.AlignCenter, txt)
        if self.hotkey:
            hk = pretty(self.hotkey)
            wk = fm.horizontalAdvance(hk) + 12
            pk = QRectF(r.right() - wk - 8, r.top() + 8, wk, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#111"))
            p.drawRect(pk)
            p.setPen(QColor("#FFE94D"))
            p.drawText(pk, Qt.AlignCenter, hk)



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


class CustomVoiceDialog(QDialog):
    """Eigenen Stimmeffekt aus bis zu 4 Live-Effekten mixen."""

    def __init__(self, data: dict | None, parent=None):
        super().__init__(parent)
        from ..effects import LIVE_KEYS, label
        self.setWindowTitle("Eigener Effekt")
        self.setMinimumWidth(520)
        data = data or {"name": "", "emoji": "★", "chain": [["potato", 0.5]]}
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        top = QHBoxLayout()
        from PySide6.QtWidgets import QLineEdit
        self.emoji = QLineEdit(data.get("emoji", "★"))
        self.emoji.setMaxLength(2)
        self.emoji.setFixedWidth(52)
        self.emoji.setAlignment(Qt.AlignCenter)
        self.name = QLineEdit(data.get("name", ""))
        self.name.setPlaceholderText("Name, z. B. Roboter im Keller")
        top.addWidget(self.emoji)
        top.addWidget(self.name, 1)
        lay.addLayout(top)
        hint = QLabel("Wähle bis zu 4 Effekte, sie werden der Reihe nach auf deine Stimme gelegt.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.rows = []
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        from PySide6.QtWidgets import QComboBox
        chain = list(data.get("chain", []))[:4]
        for i in range(4):
            cb = QComboBox()
            cb.addItem("—", "")
            for k in LIVE_KEYS:
                cb.addItem(label(k), k)
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, 100)
            if i < len(chain):
                cb.setCurrentIndex(max(0, cb.findData(chain[i][0])))
                sl.setValue(int(float(chain[i][1]) * 100))
            else:
                sl.setValue(50)
            grid.addWidget(QLabel(f"{i + 1}."), i, 0)
            grid.addWidget(cb, i, 1)
            grid.addWidget(sl, i, 2)
            self.rows.append((cb, sl))
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        lay.addLayout(grid)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self) -> dict:
        chain = [[cb.currentData(), sl.value() / 100] for cb, sl in self.rows if cb.currentData()]
        name = self.name.text().strip() or "Eigener Effekt"
        return {"name": name[:40], "emoji": self.emoji.text().strip() or "★", "chain": chain}


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
        self._build_tiles()
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
                                            ("voice_up", "Stärker (+10 %)"), ("voice_down", "Schwächer (−10 %)"),
                                            ("voice_hold", "Nur solange gedrückt"))):
            l = QLabel(text)
            l.setObjectName("muted")
            e = HotkeyEdit(cfg["hotkeys"].get(action, ""))
            e.setMinimumWidth(170)
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

    # ---- Kacheln (inkl. eigener Effekte)
    def _build_tiles(self):
        while self.flow.count():
            it = self.flow.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        self.tiles = {}
        for key in VOICE_PRESETS:
            t = PresetTile(key)
            t.clicked.connect(self._tile_clicked)
            t.menuRequested.connect(self._tile_menu)
            self.flow.addWidget(t)
            self.tiles[key] = t
        add = QPushButton("+  Eigener Effekt")
        add.setObjectName("addtile")
        add.setToolTip("Mehrere Effekte zu deinem eigenen Stimmeffekt mixen")
        add.setFixedSize(184, 124) if theme.potato() else add.setFixedSize(176, 112)
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(lambda: self._edit_custom(None))
        self.flow.addWidget(add)
        if hasattr(self, "hk_lbl"):
            self._sync()

    def _edit_custom(self, key):
        from ..effects import load_customs
        customs = dict(self.ctl.cfg["custom_voices"] or {})
        dlg = CustomVoiceDialog(customs.get(key), self)
        if not dlg.exec():
            return
        data = dlg.values()
        if not data["chain"]:
            self.ctl.toast.emit("Mindestens einen Effekt auswählen", "warn")
            return
        if key is None:
            import uuid
            key = "custom_" + uuid.uuid4().hex[:6]
        customs[key] = data
        self.ctl.cfg["custom_voices"] = customs
        load_customs(customs)
        self._build_tiles()
        self.ctl.set_voice(key, True)

    def _delete_custom(self, key):
        from ..effects import load_customs
        customs = dict(self.ctl.cfg["custom_voices"] or {})
        customs.pop(key, None)
        self.ctl.cfg["custom_voices"] = customs
        if self.ctl.cfg["voice_preset"] == key:
            self.ctl.set_voice("potato", False, quiet=True)
        load_customs(customs)
        self._build_tiles()

    def _tile_menu(self, key, pos):
        m = QMenu(self)
        a_on = m.addAction("Einschalten")
        a_hk = m.addAction("⌨ Hotkey festlegen…")
        a_clear = m.addAction("Hotkey entfernen")
        a_edit = a_del = None
        if key.startswith("custom_"):
            m.addSeparator()
            a_edit = m.addAction("✎ Eigenen Effekt bearbeiten…")
            a_del = m.addAction("🗑 Eigenen Effekt löschen")
        act = m.exec(pos)
        if act is not None and act == a_edit:
            self._edit_custom(key)
            return
        if act is not None and act == a_del:
            self._delete_custom(key)
            return
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
                                   % (P["text"] if cfg["voice_enabled"] else MUTED))
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
            txt = ("<span style='color:" + P["green"] + "'>●</span> Bereit – in Discord muss das Eingabegerät "
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
