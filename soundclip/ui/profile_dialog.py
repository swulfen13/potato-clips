"""Profil pro Spiel bearbeiten."""
from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMenu, QPushButton, QWidget)

from ..i18n import tr


class ProfileDialog(QDialog):
    def __init__(self, ctl, prof: dict, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.prof = dict(prof)
        self.setWindowTitle(tr("Profil bearbeiten"))
        self.setMinimumWidth(460)
        lay = QFormLayout(self)
        self.name = QLineEdit(self.prof.get("name", ""))
        self.name.setMaxLength(40)
        lay.addRow(tr("Name"), self.name)
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        self.apps = QLineEdit(", ".join(self.prof.get("apps", [])))
        self.apps.setPlaceholderText("z. B. fortniteclient-win64-shipping.exe")
        pick = QPushButton(tr("Laufende App …"))
        self.pick_menu = QMenu(pick)
        self.pick_menu.aboutToShow.connect(self._fill_pick)
        pick.setMenu(self.pick_menu)
        rl.addWidget(self.apps, 1)
        rl.addWidget(pick)
        lay.addRow(tr("Spiel / App"), row)
        hint = QLabel(tr("Tipp: Spiel starten, dann über „Laufende App …“ auswählen."))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addRow("", hint)
        folders = ctl.sounds.folders(ctl.cfg["sound_folders"] or [])
        self.folder = QComboBox()
        self.folder.addItem(tr("Alle Sounds"), "")
        self.folder.addItem("⭐ " + tr("Nur Favoriten"), "*fav")
        for f in folders:
            self.folder.addItem(tr("Ordner: ") + f, f)
        self._select(self.folder, self.prof.get("folder", ""))
        lay.addRow(tr("Sound-Hotkeys"), self.folder)
        self.wheel = QComboBox()
        self.wheel.addItem(tr("Wie in den Einstellungen"), "")
        self.wheel.addItem(tr("Favoriten (und die ersten Sounds)"), "fav")
        for f in folders:
            self.wheel.addItem(tr("Ordner: ") + f, f)
        self._select(self.wheel, self.prof.get("wheel_source", ""))
        lay.addRow(tr("Sound-Rad zeigt"), self.wheel)
        from ..effects import VOICE_PRESETS, voice_name
        self.voice = QComboBox()
        self.voice.addItem(tr("Nicht ändern"), "")
        self.voice.addItem(tr("Stimmeffekt aus"), "off")
        for k in VOICE_PRESETS:
            self.voice.addItem(f"{VOICE_PRESETS[k][0]} {tr(voice_name(k))}", k)
        self._select(self.voice, self.prof.get("voice", ""))
        lay.addRow(tr("Stimme"), self.voice)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)

    @staticmethod
    def _select(combo, value):
        i = combo.findData(value)
        combo.setCurrentIndex(i if i >= 0 else 0)

    def _fill_pick(self):
        from ..profiles import norm_exe, running_exes
        m = self.pick_menu
        m.clear()
        labels = self.ctl.app_labels()
        seen = set()
        for key, label in sorted(labels.items(), key=lambda kv: kv[1].lower()):
            exe = norm_exe(key.split("#")[0]) if key.startswith("app:") else ""
            if exe and exe not in seen and exe != "potatoclips.exe":
                seen.add(exe)
                m.addAction(f"{label}  ({exe})").triggered.connect(lambda _=False, e=exe: self._add_app(e))
        if not seen:
            a = m.addAction(tr("Gerade läuft keine App mit Ton"))
            a.setEnabled(False)
        exes = running_exes()
        from ..capture import PRETTY_NAMES
        games = sorted(e for e in exes if e in PRETTY_NAMES and e not in seen)
        if games:
            m.addSeparator()
            for e in games:
                m.addAction(f"{PRETTY_NAMES[e]}  ({e})").triggered.connect(lambda _=False, x=e: self._add_app(x))

    def _add_app(self, exe: str):
        cur = [a.strip() for a in self.apps.text().split(",") if a.strip()]
        if exe not in cur:
            cur.append(exe)
        self.apps.setText(", ".join(cur))
        if not self.name.text().strip() or self.name.text() == tr("Neues Profil"):
            from ..capture import pretty_app_name
            self.name.setText(pretty_app_name(exe))

    def result_profile(self) -> dict:
        from ..profiles import clean, norm_exe
        p = dict(self.prof)
        p["name"] = self.name.text().strip() or tr("Profil")
        p["apps"] = [norm_exe(a) for a in self.apps.text().split(",") if norm_exe(a)]
        p["folder"] = self.folder.currentData() or ""
        p["wheel_source"] = self.wheel.currentData() or ""
        p["voice"] = self.voice.currentData() or ""
        return clean(p)
