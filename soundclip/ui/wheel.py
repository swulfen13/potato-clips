"""Sound-Rad: Taste gedrueckt halten -> rundes Menue ueber dem Spiel, Maus in eine Richtung, loslassen = Sound.

Die Richtung kommt aus der rohen Mausbewegung (Raw Input) - das klappt auch in Spielen, die den Mauszeiger
festhalten. Ohne Raw Input wird die Zeigerposition benutzt. Mit dem Mausrad blaettert man zwischen mehreren
Seiten (wie bei den Emotes in Fortnite). Was auf welcher Seite liegt, legt man im Sound-Rad-Editor fest."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import theme
from .theme import P

MAX_ITEMS = 8          # Felder pro Seite
MAX_PAGES = 8
DEAD_ZONE = 40          # so weit (in Pixeln Mausbewegung) muss man in eine Richtung, bevor etwas gewaehlt ist


def clean_pages(pages) -> list[dict]:
    """Eigene Rad-Seiten aus der Konfiguration absichern: [{"name", "slots": [sound_id oder "", x8]}]."""
    out = []
    for pg in (pages if isinstance(pages, list) else []):
        if not isinstance(pg, dict):
            continue
        slots = [str(x or "") for x in (pg.get("slots") or [])][:MAX_ITEMS]
        slots += [""] * (MAX_ITEMS - len(slots))
        if not pg.get("name"):
            from ..i18n import tr
            pg = {**pg, "name": tr("Seite {n}").format(n=len(out) + 1)}
        out.append({"name": str(pg["name"])[:24], "slots": slots})
        if len(out) >= MAX_PAGES:
            break
    return out


def wheel_pages(ctl) -> list[dict]:
    """Seiten fuers Rad: [{"name", "items": [sound-dict oder None, ...]}].
    "custom" = eigene Auswahl aus dem Editor; Ordner/Favoriten werden automatisch auf Seiten verteilt."""
    src = ctl.wheel_source() if hasattr(ctl, "wheel_source") else ctl.cfg.get("wheel_source", "fav")
    sounds = list(ctl.sounds.sounds)
    by_id = {s["id"]: s for s in sounds}
    if src == "custom" or src.startswith("page:"):
        allp = clean_pages(ctl.cfg.get("wheel_pages"))
        if src.startswith("page:"):                 # Profil: nur eine bestimmte Seite
            try:
                allp = [allp[int(src[5:])]]
            except (ValueError, IndexError):
                allp = []
        pages = []
        for pg in allp:
            items = [by_id.get(x) for x in pg["slots"]]
            if any(items):
                # leere Felder am Ende weglassen, damit z. B. 3 Sounds ein 3er-Rad ergeben
                while items and items[-1] is None:
                    items.pop()
                pages.append({"name": pg["name"], "items": items})
        if pages:
            return pages
        src = "fav"
    if src not in ("", "fav"):
        sel = [s for s in sounds if s.get("folder", "") == src]
        name = src
    else:
        sel = sorted(sounds, key=lambda s: not s.get("fav"))      # Favoriten zuerst, dann der Rest
        name = ""
    pages = []
    for i in range(0, min(len(sel), MAX_ITEMS * MAX_PAGES), MAX_ITEMS):
        pages.append({"name": name, "items": sel[i:i + MAX_ITEMS]})
    return pages


def wheel_items(ctl) -> list[dict]:
    """Erste Seite (fuer alte Aufrufer/Tests)."""
    pages = wheel_pages(ctl)
    return [x for x in pages[0]["items"] if x] if pages else []


class SoundWheel(QWidget):
    def __init__(self, ctl):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.ctl = ctl
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(480, 524)
        self.items: list = []
        self.pages: list[dict] = []
        self.page = 0
        self.sel = -1
        self._start = QPointF()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        ctl.wheelHold.connect(self.hold)

    # ---- Ablauf
    def hold(self, down: bool):
        if down:
            self.open()
        else:
            self.release()

    def open(self):
        if self.isVisible():                    # Tasten-Wiederholung beim Halten -> nichts tun
            return
        self.pages = wheel_pages(self.ctl)
        if self.pages:
            self.page = min(getattr(self.ctl, "_wheel_page", 0), len(self.pages) - 1)   # wie zuletzt
            self.items = self.pages[self.page]["items"]
        else:
            self.items = []
        if not self.items:
            import time
            if time.time() - getattr(self, "_warned", 0) > 3:
                self._warned = time.time()
                self.ctl.toast.emit("Sound-Rad: noch keine Sounds im Soundboard", "warn")
            return
        self.sel = -1
        import time
        self._opened = time.time()
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = scr.geometry()
        self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
        self._start = QPointF(QCursor.pos())
        w = self._watcher()
        if w is not None:
            w.track_motion(True)
        self.show()
        self.raise_()
        self.timer.start(16)

    def release(self):
        if not self.isVisible():
            return
        self.timer.stop()
        self._update_sel()
        w = self._watcher()
        if w is not None:
            w.track_motion(False)
        self.hide()
        self.ctl._wheel_page = self.page
        if 0 <= self.sel < len(self.items) and self.items[self.sel]:
            self.ctl.stats.add("wheel")
            self.ctl.play_sound(self.items[self.sel]["id"])

    def turn(self, steps: int):
        """Mausrad: Seite wechseln (runter = naechste Seite, rundherum)."""
        if len(self.pages) < 2 or not steps:
            return
        self.page = (self.page - steps) % len(self.pages)
        self.items = self.pages[self.page]["items"]
        self.sel = -1
        w = self._watcher()
        if w is not None:                       # nach dem Blaettern neu zielen
            w.dx = w.dy = 0
        self._start = QPointF(QCursor.pos())
        self.update()

    def cancel(self):
        """Schliessen, ohne etwas abzuspielen."""
        self.sel = -1
        self.timer.stop()
        w = self._watcher()
        if w is not None:
            w.track_motion(False)
        self.hide()

    def _watcher(self):
        try:
            return self.ctl.hotkeys.watcher()
        except Exception:
            return None

    def _key_held(self) -> bool:
        """Ist die Rad-Taste noch gedrueckt? (Nicht nur auf das Loslassen-Ereignis verlassen.)"""
        combo = str(self.ctl.cfg["hotkeys"].get("wheel_hold") or "")
        if not combo:
            return False
        try:
            if "mouse:" in combo or "pad:" in combo:
                w = self._watcher()
                return w is not None and combo in w._held
            import keyboard
            return bool(keyboard.is_pressed(combo))
        except Exception:
            return False

    def _tick(self):
        import time
        age = time.time() - getattr(self, "_opened", 0)
        if age > 8:                             # Notbremse: nie laenger als 8 s offen
            self.cancel()
            return
        if age > 0.15 and not self._key_held():
            self.release()
            return
        w = self._watcher()
        if w is not None and hasattr(w, "take_wheel"):
            st = w.take_wheel()
            if st:
                self._opened = time.time()          # beim Blaettern nicht in die 8-s-Notbremse laufen
                self.turn(st)
        self._update_sel()

    def _update_sel(self):
        dx = dy = 0.0
        w = self._watcher()
        if w is not None and w.mouse_ok and (w.dx or w.dy):
            dx, dy = float(w.dx), float(w.dy)
        else:
            d = QPointF(QCursor.pos()) - self._start
            dx, dy = d.x(), d.y()
        n = len(self.items)
        sel = -1
        if n and math.hypot(dx, dy) > DEAD_ZONE:
            ang = (math.degrees(math.atan2(dx, -dy)) + 360) % 360          # 0 Grad = oben, im Uhrzeigersinn
            sel = int(((ang + 180 / n) % 360) // (360 / n))
        if sel != self.sel:
            self.sel = sel
            self.update()

    # ---- Zeichnen
    def paintEvent(self, e):
        n = len(self.items)
        if not n:
            return
        pot = theme.potato()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, 240.0)
        r_out, r_in = 220.0, 70.0
        span = 360.0 / n
        f = QFont(P.get("font_body", "Inter"))
        f.setPixelSize(15)
        f.setBold(True)
        p.setFont(f)
        for i, s in enumerate(self.items):
            start = 90 - (i * span) + span / 2          # Qt: 0 Grad = rechts, gegen den Uhrzeigersinn
            path = QPainterPath()
            path.moveTo(c)
            path.arcTo(QRectF(c.x() - r_out, c.y() - r_out, 2 * r_out, 2 * r_out), start, -span)
            path.closeSubpath()
            hole = QPainterPath()
            hole.addEllipse(c, r_in, r_in)
            path = path.subtracted(hole)
            on = i == self.sel
            empty = s is None
            if empty:
                p.setPen(QPen(QColor("#111") if pot else QColor("#2C3038"), 2 if pot else 1.2, Qt.DashLine))
                p.setBrush(QColor(255, 233, 77, 90) if pot else QColor(22, 24, 29, 150))
                p.drawPath(path)
                continue
            if pot:
                fill = QColor("#FF3D8B") if on else QColor("#FFE94D")
                pen = QPen(QColor("#111"), 3)
            else:
                fill = QColor("#F2A93B") if on else QColor(22, 24, 29, 235)
                pen = QPen(QColor("#2C3038") if not on else QColor("#F2A93B"), 1.5)
            p.setPen(pen)
            p.setBrush(fill)
            p.drawPath(path)
            mid = math.radians(i * span)
            tx = c.x() + math.sin(mid) * (r_in + r_out) / 2
            ty = c.y() - math.cos(mid) * (r_in + r_out) / 2
            p.setPen(QColor("#111") if (pot or on) else QColor(P["text"]))
            name = s["name"] if len(s["name"]) <= 16 else s["name"][:15] + "…"
            p.drawText(QRectF(tx - 70, ty - 24, 140, 48), Qt.AlignCenter | Qt.TextWordWrap,
                       f"{i + 1}\n{name}" if n > 1 else name)
        # Mitte
        p.setBrush(QColor("#111") if pot else QColor(13, 14, 17, 240))
        p.setPen(QPen(QColor("#FFE94D") if pot else QColor("#2C3038"), 3 if pot else 1.5))
        p.drawEllipse(c, r_in - 6, r_in - 6)
        p.setPen(QColor("#FFE94D") if pot else QColor(P["text"]))
        f.setPixelSize(12)
        p.setFont(f)
        from ..i18n import tr
        cur = self.items[self.sel] if 0 <= self.sel < n else None
        txt = cur["name"] if cur else tr("Richtung zeigen,\nloslassen = Sound")
        p.drawText(QRectF(c.x() - r_in + 10, c.y() - 30, 2 * r_in - 20, 60), Qt.AlignCenter | Qt.TextWordWrap, txt)
        # Seiten: Name + Punkte unten
        if len(self.pages) > 1 or (self.pages and self.pages[0]["name"]):
            title = self.pages[self.page]["name"] or tr("Seite {n}").format(n=self.page + 1)
            f.setPixelSize(14)
            p.setFont(f)
            box = QRectF(c.x() - 110, self.height() - 16 - 26, 220, 26)
            p.setPen(Qt.NoPen if not pot else QPen(QColor("#111"), 2))
            p.setBrush(QColor("#FFE94D") if pot else QColor(13, 14, 17, 225))
            if pot:
                p.drawRect(box)
            else:
                p.drawRoundedRect(box, 13, 13)
            p.setPen(QColor("#111") if pot else QColor(P["text"]))
            dots = "  " + " ".join("●" if i == self.page else "○" for i in range(len(self.pages))) \
                if len(self.pages) > 1 else ""
            p.drawText(box, Qt.AlignCenter, title + dots)
        p.end()
