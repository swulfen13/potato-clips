from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
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
from . import theme
from .theme import P
from .widgets import app_icon, brand_pixmap, hard_shadow, save_icon_file

NAV_ICONS = {
    "soundboard": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>'
                  '<rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "voice": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
    "clips": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.6 7.6 20 18M8.6 16.4 20 6"/>',
    "sources": '<path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="m3 13 9 5 9-5"/>',
    "wrapped": '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4Z"/><path d="M7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1'
                'M4.9 19.1 7 17M17 7l2.1-2.1"/>',
}


def line_icon(name: str, color: str, size: int = 18):
    """Schlichtes Linien-Icon (Profi-Design)."""
    from PySide6.QtGui import QIcon, QPixmap
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size * 2}" height="{size * 2}" viewBox="0 0 24 24" '
           f'fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
           f'{NAV_ICONS[name]}</svg>')
    pm = QPixmap()
    pm.loadFromData(svg.encode("utf-8"), "SVG")
    return QIcon(pm)


class LogoLabel(QLabel):
    def __init__(self):
        super().__init__()
        n = 44 if theme.potato() else 34
        self.setPixmap(brand_pixmap(n * 2).scaled(n, n, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setFixedSize(n, n)
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
        name = QLabel("POTATO CLIPS" if theme.potato() else "Potato Clips")
        name.setObjectName("brand")
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
        from .wrapped_tab import WrappedTab
        self.wrapped = WrappedTab(ctl)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = {}
        for page, text, ic in ((self.soundboard, "🎛   Soundboard", "soundboard"),
                               (self.voice, "🎭   Stimme verändern", "voice"),
                               (self.clips, "✂   Clips && Editor", "clips"),
                               (self.sources, "🎙   Quellen && Aufnahme", "sources"),
                               (self.wrapped, "🏆   Potato Wrapped", "wrapped"),
                               (self.settings, "⚙   Einstellungen", "settings")):
            self.stack.addWidget(page)
            b = QPushButton(text)
            b.setObjectName("nav")
            if not theme.potato():
                b.setIcon(line_icon(ic, P["muted"]))
                b.setIconSize(QSize(18, 18))
            else:
                hard_shadow(b, 4)
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
        if theme.potato():
            stop.setObjectName("danger")
            for b in (self.btn_clip, self.btn_rec, stop):
                hard_shadow(b, 4)
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
        from .wheel import SoundWheel
        self.wheel = SoundWheel(ctl)

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
        a_quit.triggered.connect(self._quit_from_tray)
        for a in (a_open, a_clip, self.a_rec, a_stop, a_ov):
            menu.addAction(a)
        self.prof_menu = menu.addMenu("🎮  Profil")
        self.prof_menu.aboutToShow.connect(self._fill_prof_menu)
        menu.addSeparator()
        menu.addAction(a_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show_normal() if r in (QSystemTrayIcon.Trigger,
                                                                           QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()
        self._tray_hint_shown = False
        self._pending_ask = None
        self.tray.messageClicked.connect(self._tray_message_clicked)
        ctl.updateReady.connect(self._update_ready)
        ctl.installUpdate.connect(self._install_update)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(500)
        self._tick()
        ctl.updateFound.connect(self._update_found)
        if not ctl.cfg.get("setup_done", True):
            QTimer.singleShot(700, self._first_run)

    def _first_run(self):
        from .wizard import SetupWizard
        self.show_normal()
        SetupWizard(self.ctl, self).exec()

    def _update_found(self, info: dict):
        """Neue Version: Fenster offen -> gleich fragen; sonst nur dezent im Tray melden (nicht mitten im Spiel)."""
        from ..i18n import tr
        if self.isVisible() and not self.isMinimized() and self.isActiveWindow():
            self._ask_update(info)
            return
        self._pending_ask = info
        self.tray.showMessage(tr("Update verfügbar"),
                              tr("Potato Clips {v} ist da – hier klicken zum Aktualisieren").format(
                                  v=info.get("version", "?")), app_icon(), 8000)

    def _tray_message_clicked(self):
        self.show_normal()

    def _update_ready(self, ver: str):
        from ..i18n import tr
        self.tray.showMessage(tr("Update geladen"),
                              tr("Potato Clips {v} wird installiert, sobald gerade nichts los ist "
                                 "(oder beim Beenden).").format(v=ver), app_icon(), 6000)

    def _install_update(self, path: str):
        from .. import updater
        from ..i18n import tr
        self.ctl.toast.emit("⬇ Update wird installiert – Potato Clips startet gleich neu", "info")
        self.tray.showMessage(tr("Update wird installiert"), tr("Potato Clips startet gleich neu."), app_icon(), 4000)

        def go():
            try:
                updater.run_installer(path)
            except Exception as e:
                self.ctl.toast.emit("Update fehlgeschlagen: " + str(e), "warn")
                return
            self.quit()
        QTimer.singleShot(2500, go)

    def _quit_from_tray(self):
        """Beenden ueber das Tray: ein schon geladenes Update noch schnell installieren (ohne Neustart)."""
        p = self.ctl.take_pending_update()
        if p:
            from .. import updater
            try:
                updater.run_installer(p, relaunch=False)
            except Exception:
                pass
        self.quit()

    def _ask_update(self, info: dict):
        from PySide6.QtWidgets import QMessageBox
        from .. import updater
        from ..i18n import tr
        self._pending_ask = None
        ver = info.get("version", "?")
        r = QMessageBox.question(self, tr("Update verfügbar"),
                                 tr("Potato Clips {v} ist da. Jetzt aktualisieren?").format(v=ver))
        if r != QMessageBox.Yes:
            self.ctl.decline_update(ver)
            return
        if not (updater.can_self_update() and info.get("url")):
            import webbrowser
            webbrowser.open(info.get("page") or updater.PAGE)
            return
        self._download_update(info["url"], info.get("sha256", ""))

    def _download_update(self, url, sha256=""):
        import threading
        from PySide6.QtWidgets import QProgressDialog
        from .. import updater
        from ..i18n import tr
        dlg = QProgressDialog(tr("Update wird geladen …"), tr("Abbrechen"), 0, 100, self)
        dlg.setWindowTitle("Potato Clips")
        dlg.setMinimumDuration(0)
        state = {"p": 0.0, "path": None, "err": None}

        def work():
            try:
                state["path"] = updater.download(url, lambda f: state.__setitem__("p", f), sha256)
            except Exception as e:
                state["err"] = str(e)
        threading.Thread(target=work, daemon=True).start()

        def poll():
            dlg.setValue(int(state["p"] * 100))
            if dlg.wasCanceled():
                t.stop()
                return
            if state["err"]:
                t.stop()
                dlg.close()
                self.ctl.toast.emit("Update fehlgeschlagen: " + state["err"], "warn")
            elif state["path"]:
                t.stop()
                dlg.close()
                updater.run_installer(state["path"])
                self.quit()
        t = QTimer(self)
        t.timeout.connect(poll)
        t.start(100)

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

    def _fill_prof_menu(self):
        from ..i18n import tr
        m = self.prof_menu
        m.clear()
        man = self.ctl.cfg["profile_manual"]
        cur = (self.ctl.profile or {}).get("id", "")
        a = m.addAction(tr("Automatisch"))
        a.setCheckable(True)
        a.setChecked(not man)
        a.triggered.connect(lambda: self.ctl.choose_profile(""))
        profs = self.ctl.profiles()
        if profs:
            m.addSeparator()
        for p in profs:
            a = m.addAction(p["name"])
            a.setCheckable(True)
            a.setChecked(bool(man) and p["id"] == cur)
            a.triggered.connect(lambda _=False, pid=p["id"]: self.ctl.choose_profile(pid))
        if not profs:
            x = m.addAction(tr("Noch keine Profile – Einstellungen → Profile pro Spiel"))
            x.setEnabled(False)

    def _tick(self):
        src = self.ctl.sources
        if not src.helper_ok:
            self.side_status.setText("⚠ bin\\audiocap.exe fehlt – setup.bat ausführen")
            return
        n = src.running_count()
        from ..i18n import tr
        lines = [f"<span style='color:{P['green']}'>●</span> " + tr(f"{n} Quellen laufen"),
                 tr(f"Puffer: letzte {self.ctl.cfg['buffer_seconds']} s")]
        hk = self.ctl.hotkey_text("clip")
        if hk:
            lines.append(tr(f"Clip-Hotkey: {hk}"))
        if self.ctl.profile:
            lines.append("🎮 " + self.ctl.profile["name"])
        if self.ctl.cfg["voice_enabled"]:
            from ..effects import voice_name
            lines.append(f"<span style='color:{P['accent']}'>" + tr(voice_name(self.ctl.cfg['voice_preset'])) + "</span>")
        if src.recording:
            t = int(src.recording_seconds())
            lines.insert(0, f"<span style='color:{P['red']}'><b>● REC {t // 60}:{t % 60:02d}</b></span>")
        self.side_status.setText("<br>".join(lines))

    def show_normal(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()
        if self._pending_ask:
            info = self._pending_ask
            QTimer.singleShot(400, lambda: self._ask_update(info))

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
        self.wheel.cancel()
        self.overlay.hide()
        self.tray.hide()
        self.ctl.shutdown()
        QApplication.quit()
