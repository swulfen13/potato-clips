"""Einrichtungs-Assistent beim ersten Start: Aussehen, VB-Cable, Discord, Mikro."""
from __future__ import annotations

import webbrowser

import numpy as np
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout,
                               QWidget)

from .theme import P
from .widgets import LevelMeter, ToggleSwitch


class SetupWizard(QDialog):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.setWindowTitle("Potato Clips einrichten")
        self.setMinimumSize(640, 500)
        self._probe = None
        self._mic_probe = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(14)
        self.step_lbl = QLabel()
        self.step_lbl.setObjectName("sub")
        lay.addWidget(self.step_lbl)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        nav = QHBoxLayout()
        self.back = QPushButton("Zurück")
        self.back.clicked.connect(lambda: self._go(self.stack.currentIndex() - 1))
        self.skip = QPushButton("Überspringen")
        self.skip.clicked.connect(self._finish)
        self.next = QPushButton("Weiter")
        self.next.setObjectName("accent")
        self.next.clicked.connect(self._next)
        nav.addWidget(self.skip)
        nav.addStretch(1)
        nav.addWidget(self.back)
        nav.addWidget(self.next)
        lay.addLayout(nav)

        from .. import i18n
        self._lang_start = i18n.LANG                     # Sprache, in der die App gerade laeuft
        self._lang_choice = self.ctl.cfg.get("language", "auto")
        self._theme_choice = self.ctl.cfg.get("ui_theme", "pro")
        self._build_pages()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(60)
        self._go(0)

    # ---------------------------------------------------------------- Seiten
    def _build_pages(self):
        self._page_welcome()
        self._page_cable()
        self._page_discord()
        self._page_mic()
        self._page_done()

    def _lang_changed(self, *_):
        """Sprache sofort umstellen: der Assistent baut sich in der neuen Sprache neu auf."""
        # Qt meldet auch beim Abbauen alter/geschlossener Fenster eine Aenderung - die ignorieren
        if self.sender() is not self.lang or not self.isVisible() or self.lang.currentData() is None:
            return
        self._lang_choice = self.lang.currentData()
        self._theme_choice = "potato" if self.theme_btns["potato"].isChecked() else "pro"
        QTimer.singleShot(0, self._retranslate)

    def _retranslate(self):
        from PySide6.QtCore import QLocale
        from .. import i18n
        if not self.isVisible():
            return
        lang = self._lang_choice
        if lang not in ("de", "en"):
            lang = "de" if QLocale.system().language() == QLocale.German else "en"
        i18n.setup(lang, i18n.MODE)
        self._stop_probes()
        idx = self.stack.currentIndex()
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()
        self._build_pages()
        self.setWindowTitle("Potato Clips einrichten")
        self.back.setText("Zurück")
        self.skip.setText("Überspringen")
        self._go(idx)

    def _page(self, title, text=""):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        h = QLabel(title)
        h.setObjectName("h1")
        h.setWordWrap(True)
        v.addWidget(h)
        if text:
            t = QLabel(text)
            t.setWordWrap(True)
            t.setObjectName("muted")
            v.addWidget(t)
        self.stack.addWidget(w)
        return v

    def _page_welcome(self):
        from .settings_tab import _theme_preview
        v = self._page("Willkommen bei Potato Clips",
                       "In vier kurzen Schritten ist alles bereit: Aussehen, virtuelles Mikro für Discord, "
                       "Discord-Einstellungen und dein Mikrofon.")
        t = QLabel("Wie soll Potato Clips aussehen?")
        t.setStyleSheet("font-weight: 700; background: transparent;")
        v.addWidget(t)
        row = QHBoxLayout()
        self.theme_btns = {}
        for key, title, desc in (("pro", "Profi", "Ruhig, dunkel, aufgeräumt"),
                                 ("potato", "Potato-Modus", "Laut, bunt, albern")):
            b = QPushButton(f"{title}\n{desc}")
            b.setObjectName("themecard")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setIcon(QIcon(_theme_preview(key)))
            b.setIconSize(QSize(96, 53))
            b.setMinimumHeight(80)
            b.setChecked(self._theme_choice == key)
            row.addWidget(b, 1)
            self.theme_btns[key] = b
        v.addLayout(row)
        lrow = QHBoxLayout()
        lab = QLabel("Sprache / Language")
        lab.setStyleSheet("font-weight: 700; background: transparent;")
        lrow.addWidget(lab)
        lrow.addStretch(1)
        self.lang = QComboBox()
        for k, t in (("auto", "Automatisch (Windows)"), ("de", "Deutsch"), ("en", "English")):
            self.lang.addItem(t, k)
        self.lang.setCurrentIndex(max(0, self.lang.findData(self._lang_choice)))
        self.lang.currentIndexChanged.connect(self._lang_changed)
        self.lang.setMinimumWidth(220)
        lrow.addWidget(self.lang)
        v.addLayout(lrow)
        v.addStretch(1)

    def _page_cable(self):
        v = self._page("Virtuelles Mikro (VB-Cable)",
                       "Damit deine Freunde in Discord deine Sounds und Stimmeffekte hören, braucht Windows ein "
                       "virtuelles Mikrofon. Dafür gibt es das kostenlose VB-Cable.")
        self.cable_status = QLabel()
        self.cable_status.setWordWrap(True)
        self.cable_status.setTextFormat(Qt.RichText)
        self.cable_status.setStyleSheet("font-size: 12pt; font-weight: 700; background: transparent;")
        v.addWidget(self.cable_status)
        row = QHBoxLayout()
        self.cable_dl = QPushButton("VB-Cable herunterladen")
        self.cable_dl.setObjectName("accent")
        self.cable_dl.clicked.connect(lambda: webbrowser.open("https://vb-audio.com/Cable/"))
        again = QPushButton("Nochmal prüfen")
        again.clicked.connect(self._check_cable)
        row.addWidget(self.cable_dl)
        row.addWidget(again)
        row.addStretch(1)
        v.addLayout(row)
        hint = QLabel("Nach der Installation von VB-Cable den PC einmal neu starten. Du kannst auch ohne "
                      "weitermachen – dann hörst nur du die Sounds.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        v.addWidget(hint)
        v.addStretch(1)

    def _page_discord(self):
        v = self._page("Discord einstellen",
                       "Öffne in Discord: Einstellungen → Sprache & Video. Stell dort Folgendes ein:")
        steps = QLabel("1.  Eingabegerät: <b>CABLE Output (VB-Audio Virtual Cable)</b><br>"
                       "2.  Ausgabegerät: dein Kopfhörer (<b>nicht</b> das Kabel)<br>"
                       "3.  Rauschunterdrückung: <b>Keine</b> · Echoentfernung: <b>aus</b><br>"
                       "4.  Eingabeempfindlichkeit von Hand einstellen (Regler weit links)")
        steps.setTextFormat(Qt.RichText)
        steps.setWordWrap(True)
        v.addWidget(steps)
        row = QHBoxLayout()
        test = QPushButton("Test-Sound senden")
        test.clicked.connect(self._test_sound)
        row.addWidget(test)
        self.cable_meter = LevelMeter()
        row.addWidget(self.cable_meter, 1)
        v.addLayout(row)
        t = QLabel("Der Balken zeigt, was Discord gerade von Potato Clips bekommt.")
        t.setObjectName("muted")
        t.setWordWrap(True)
        v.addWidget(t)
        v.addStretch(1)

    def _page_mic(self):
        v = self._page("Dein Mikrofon", "Sag kurz etwas – der Balken sollte ausschlagen.")
        self.mic = QComboBox()
        self.mic.addItem("Windows-Standard", "default")
        for d in self.ctl.sources.devices.get("capture", []):
            self.mic.addItem(d["name"], d["id"])
        self.mic.setCurrentIndex(max(0, self.mic.findData(self.ctl.cfg["mic_device"])))
        self.mic.currentIndexChanged.connect(self._mic_changed)
        v.addWidget(self.mic)
        self.mic_meter = LevelMeter()
        v.addWidget(self.mic_meter)
        self.clean = ToggleSwitch("KI-Rauschfilter (Tastatur, Lüfter und Klicken raus)")
        self.clean.setChecked(self.ctl.cfg["clean_mic"])
        v.addWidget(self.clean)
        v.addStretch(1)

    def _page_done(self):
        v = self._page("Fertig!", "Potato Clips läuft jetzt im Hintergrund. Die wichtigsten Tasten:")
        hk = self.ctl.hotkey_text
        lines = [("Clip speichern (letzte X Sekunden)", hk("clip")), ("Aufnahme starten/stoppen", hk("record")),
                 ("Alle Sounds stoppen", hk("stop_all")), ("Stimmeffekt ein/aus", hk("voice_toggle"))]
        for text, key in lines:
            r = QHBoxLayout()
            a = QLabel(text)
            b = QLabel(key or "–")
            b.setObjectName("kbd")
            r.addWidget(a)
            r.addStretch(1)
            r.addWidget(b)
            v.addLayout(r)
        t = QLabel("Sounds legst du im Soundboard an (einfach Dateien reinziehen). Alles andere findest du in den "
                   "Einstellungen.")
        t.setWordWrap(True)
        t.setObjectName("muted")
        v.addWidget(t)
        v.addStretch(1)

    # ---------------------------------------------------------------- Ablauf
    def _go(self, i):
        i = max(0, min(self.stack.count() - 1, i))
        self.stack.setCurrentIndex(i)
        self.step_lbl.setText(f"{i + 1} / {self.stack.count()}")
        self.back.setVisible(i > 0)
        last = i == self.stack.count() - 1
        self.next.setText("Los geht's" if last else "Weiter")
        self.skip.setVisible(not last)
        if i == 1:
            self._check_cable()
        self._stop_probes()
        if i == 2:
            self._start_cable_probe()
        if i == 3:
            self._mic_changed()

    def _next(self):
        i = self.stack.currentIndex()
        if i == 0 and self._apply_look():
            return
        if i == 3:
            self._apply_mic()
        if i == self.stack.count() - 1:
            self._finish()
            return
        self._go(i + 1)

    def _apply_look(self) -> bool:
        """Design gewechselt? Dann speichern und neu starten (Assistent kommt danach wieder).
        Die Sprache wechselt im Assistenten sofort; das Hauptfenster folgt nach dem Assistenten."""
        mode = "potato" if self.theme_btns["potato"].isChecked() else "pro"
        lang = self.lang.currentData()
        cfg = self.ctl.cfg
        cfg["language"] = lang
        if mode == cfg.get("ui_theme", "pro"):
            return False
        cfg.update(ui_theme=mode, language=lang)
        self._stop_probes()
        self.accept()
        from .restart import restart_app
        restart_app()
        return True

    def _apply_mic(self):
        cfg = self.ctl.cfg
        dev = self.mic.currentData()
        changed = dev != cfg["mic_device"]
        if self.clean.isChecked() != bool(cfg["clean_mic"]):
            cfg["clean_mic"] = self.clean.isChecked()
            self.ctl.mixer.apply_clean()
        if changed:
            cfg["mic_device"] = dev
            self.ctl.mixer.apply_voice_path()
            self.ctl.sources.rebuild()
        self.ctl.settingsChanged.emit()

    def _finish(self):
        self._stop_probes()
        self.ctl.cfg["setup_done"] = True
        self.ctl.cfg["language"] = self.lang.currentData() if self.stack.count() else self._lang_choice
        self.accept()
        from .. import i18n
        if i18n.LANG != self._lang_start:          # Hauptfenster in der neuen Sprache neu starten
            from .restart import restart_app
            restart_app()

    def closeEvent(self, e):
        self._stop_probes()
        self.ctl.cfg["setup_done"] = True
        super().closeEvent(e)
        self._keep_language()

    def reject(self):
        self._stop_probes()
        self.ctl.cfg["setup_done"] = True
        super().reject()
        self._keep_language()

    def _keep_language(self):
        """Fenster geschlossen, nachdem die Sprache umgestellt wurde: Sprache merken und neu starten."""
        from .. import i18n
        if i18n.LANG != self._lang_start and not getattr(self, "_restarting", False):
            self._restarting = True
            self.ctl.cfg["language"] = self._lang_choice
            from .restart import restart_app
            restart_app()

    # ---------------------------------------------------------------- Pruefungen
    def _check_cable(self):
        from ..capture import run_helper_list
        from ..mixer import find_cable_device
        try:
            name = find_cable_device(run_helper_list().get("render", []))
        except Exception:
            name = ""
        if name:
            self.cable_status.setText(f"<span style='color:{P['green']}'>✓</span> Gefunden: {name}")
            self.cable_dl.setObjectName("")
        else:
            self.cable_status.setText(f"<span style='color:{P['red']}'>✕</span> Noch kein VB-Cable installiert")
            self.cable_dl.setObjectName("accent")
        self.cable_dl.style().unpolish(self.cable_dl)
        self.cable_dl.style().polish(self.cable_dl)

    def _test_sound(self):
        if not self.ctl.mixer.is_open("virtual"):
            self.ctl.mixer.reopen()
        if not self.ctl.mixer.is_open("virtual"):
            self.ctl.toast.emit("Kein virtuelles Mikro aktiv – bitte oben auswählen", "warn")
            return
        t = np.arange(int(0.9 * 48000)) / 48000
        env = np.minimum(1, t * 40) * np.exp(-t * 3)
        tone = 0.35 * env * (np.sin(2 * np.pi * 660 * t) + 0.5 * np.sin(2 * np.pi * 990 * t))
        self.ctl.mixer.play(np.repeat(tone[:, None], 2, axis=1).astype(np.float32), sound_id="__test__",
                            name="Test", targets=["virtual"])

    def _start_cable_probe(self):
        from ..capture import LevelProbe, run_helper_list
        from ..mixer import find_cable_capture
        m = self.ctl.mixer
        name = m.devices.get("virtual", "") if m.is_open("virtual") else m.virtual_device_name()
        try:
            cap = find_cable_capture(run_helper_list().get("capture", []), name)
            if cap:
                self._probe = LevelProbe(cap["id"])
        except Exception:
            self._probe = None

    def _mic_changed(self, *_):
        from ..capture import LevelProbe
        if self._mic_probe is not None:
            self._mic_probe.stop()
            self._mic_probe = None
        if self.stack.currentIndex() == 3:
            try:
                self._mic_probe = LevelProbe(self.mic.currentData() or "default")
            except Exception:
                self._mic_probe = None

    def _stop_probes(self):
        for p in (self._probe, self._mic_probe):
            if p is not None:
                try:
                    p.stop()
                except Exception:
                    pass
        self._probe = self._mic_probe = None

    def _tick(self):
        if self._probe is not None:
            self.cable_meter.push(self._probe.take())
        if self._mic_probe is not None:
            self.mic_meter.push(self._mic_probe.take())
