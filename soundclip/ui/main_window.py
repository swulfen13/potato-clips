from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QMenu, QPushButton,
                               QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from ..autostart import ICON
from .clips_tab import ClipsTab
from .overlay import Overlay
from .settings_tab import SettingsTab
from .soundboard_tab import SoundboardTab
from .sources_tab import SourcesTab
from .voice_tab import VoiceTab
from .widgets import app_icon, save_icon_file


class LogoLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.setPixmap(app_icon().pixmap(34, 34))
        self.setFixedSize(34, 34)
        self.setStyleSheet("background: transparent;")


class MainWindow(QMainWindow):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.quitting = False
        self.setWindowTitle("Potato Clips")
        self.setWindowIcon(app_icon())
        self.resize(1240, 800)
        self.setMinimumSize(980, 640)
        if not ICON.exists():
            save_icon_file(ICON)

        central = QWidget()
        central.setObjectName("page")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------------- Seitenleiste
        side = QWidget()
        side.setObjectName("sidebar")
        side.setAttribute(Qt.WA_StyledBackground, True)
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 18, 14, 16)
        sl.setSpacing(4)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(LogoLabel())
        bt = QVBoxLayout()
        bt.setSpacing(0)
        name = QLabel("Potato Clips")
        name.setStyleSheet("font-size: 14pt; font-weight: 700; background: transparent;")
        tag = QLabel("Soundboard & Clips")
        tag.setObjectName("sub")
        bt.addWidget(name)
        bt.addWidget(tag)
        brand.addLayout(bt)
        brand.addStretch(1)
        sl.addLayout(brand)
        sl.addSpacing(22)

        self.stack = QStackedWidget()
        self.soundboard = SoundboardTab(ctl)
        self.voice = VoiceTab(ctl)
        self.clips = ClipsTab(ctl)
        self.sources = SourcesTab(ctl)
        self.settings = SettingsTab(ctl)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = {}
        for page, text in ((self.soundboard, "🎛   Soundboard"), (self.voice, "🎭   Stimme verändern"),
                           (self.clips, "✂   Clips && Editor"),
                           (self.sources, "🎙   Quellen && Aufnahme"), (self.settings, "⚙   Einstellungen")):
            self.stack.addWidget(page)
            b = QPushButton(text)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, w=page: self.show_page(w))
            self.nav_group.addButton(b)
            self.nav_buttons[page] = b
            sl.addWidget(b)
        sl.addStretch(1)

        self.btn_clip = QPushButton("✂  Clip speichern")
        self.btn_clip.setObjectName("accent")
        self.btn_clip.setCursor(Qt.PointingHandCursor)
        self.btn_clip.clicked.connect(lambda: ctl.clip_now())
        self.btn_rec = QPushButton("●  Aufnahme starten")
        self.btn_rec.setObjectName("rec")
        self.btn_rec.setCursor(Qt.PointingHandCursor)
        self.btn_rec.clicked.connect(lambda: ctl.toggle_recording())
        stop = QPushButton("■  Alle Sounds stoppen")
        stop.setCursor(Qt.PointingHandCursor)
        stop.clicked.connect(ctl.stop_all)
        for b in (self.btn_clip, self.btn_rec, stop):
            sl.addWidget(b)
        sl.addSpacing(10)
        self.side_status = QLabel()
        self.side_status.setObjectName("sub")
        self.side_status.setWordWrap(True)
        self.side_status.setTextFormat(Qt.RichText)
        sl.addWidget(self.side_status)

        root.addWidget(side)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.show_page(self.soundboard)

        self.soundboard.openInEditor.connect(self._sound_to_editor)
        self.voice.openSettings.connect(lambda: self.show_page(self.settings))
        ctl.recordingChanged.connect(self._rec_changed)

        self.overlay = Overlay(ctl)
        self.overlay.apply_visibility()

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Potato Clips")
        menu = QMenu()
        a_open = QAction("Öffnen", self)
        a_open.triggered.connect(self.show_normal)
        a_clip = QAction("✂  Clip speichern", self)
        a_clip.triggered.connect(lambda: ctl.clip_now())
        self.a_rec = QAction("●  Aufnahme starten", self)
        self.a_rec.triggered.connect(lambda: ctl.toggle_recording())
        a_ov = QAction("Overlay ein/aus", self)
        a_ov.triggered.connect(self._toggle_overlay)
        a_stop = QAction("■  Alle Sounds stoppen", self)
        a_stop.triggered.connect(ctl.stop_all)
        a_quit = QAction("Beenden", self)
        a_quit.triggered.connect(self.quit)
        for a in (a_open, a_clip, self.a_rec, a_stop, a_ov):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(a_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show_normal() if r in (QSystemTrayIcon.Trigger,
                                                                           QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()
        self._tray_hint_shown = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(500)
        self._tick()

    # Kompatibilitaet fuer Tests: win.tabs.setCurrentWidget(...)
    @property
    def tabs(self):
        return self

    def setCurrentWidget(self, w):
        self.show_page(w)

    def show_page(self, w):
        self.stack.setCurrentWidget(w)
        self.nav_buttons[w].setChecked(True)

    def _toggle_overlay(self):
        self.ctl.cfg["overlay_enabled"] = not self.ctl.cfg["overlay_enabled"]
        self.ctl.overlayToggled.emit(self.ctl.cfg["overlay_enabled"])

    def _sound_to_editor(self, sid):
        s = self.ctl.sounds.get(sid)
        if not s:
            return
        meta = self.ctl.clips.from_sound(s["name"], self.ctl.sounds.audio(s))
        self.show_page(self.clips)
        self.clips.open_clip(meta["id"])

    def _rec_changed(self, on):
        self.btn_rec.setText("■  Aufnahme stoppen" if on else "●  Aufnahme starten")
        self.btn_rec.setProperty("recording", "true" if on else "false")
        self.btn_rec.style().unpolish(self.btn_rec)
        self.btn_rec.style().polish(self.btn_rec)
        self.a_rec.setText("■  Aufnahme stoppen" if on else "●  Aufnahme starten")

    def _tick(self):
        src = self.ctl.sources
        if not src.helper_ok:
            self.side_status.setText("⚠ bin\\audiocap.exe fehlt – setup.bat ausführen")
            return
        n = src.running_count()
        lines = [f"<span style='color:#2ec4b6'>●</span> {n} Quellen laufen",
                 f"Puffer: letzte {self.ctl.cfg['buffer_seconds']} s"]
        hk = self.ctl.hotkey_text("clip")
        if hk:
            lines.append(f"Clip-Hotkey: {hk}")
        if self.ctl.cfg["voice_enabled"]:
            from ..effects import voice_name
            lines.append(f"<span style='color:#b9a8ff'>🎭 {voice_name(self.ctl.cfg['voice_preset'])}</span>")
        if src.recording:
            t = int(src.recording_seconds())
            lines.insert(0, f"<span style='color:#ff4d6d'><b>● REC {t // 60}:{t % 60:02d}</b></span>")
        self.side_status.setText("<br>".join(lines))

    def show_normal(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        if not self.quitting and self.ctl.cfg["minimize_to_tray"] and QSystemTrayIcon.isSystemTrayAvailable():
            e.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self.tray.showMessage("Potato Clips läuft weiter",
                                      "Hotkeys und Clip-Puffer sind aktiv. Beenden über das Tray-Symbol.",
                                      app_icon(), 4000)
                self._tray_hint_shown = True
            return
        self.quit()
        e.accept()

    def quit(self):
        if self.quitting:
            return
        self.quitting = True
        self.clips.shutdown()
        self.overlay.hide()
        self.tray.hide()
        self.ctl.shutdown()
        QApplication.quit()
