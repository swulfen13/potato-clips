"""Sound-Rad-Editor: selbst festlegen, welche Sounds auf welcher Seite des Rads liegen.

Links die Seiten, in der Mitte das Rad mit 8 Feldern, rechts alle Sounds. Feld anklicken, dann einen Sound
anklicken (danach springt die Auswahl ins naechste freie Feld). Rechtsklick auf ein Feld = leeren."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from ..i18n import tr
from . import theme
from .theme import P
from .wheel import MAX_ITEMS, MAX_PAGES, clean_pages


class WheelView(QWidget):
    """Das Rad zum Anklicken (8 Felder)."""
    slotClicked = Signal(int)
    slotMenu = Signal(int, object)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(360, 360)
        self.names = [""] * MAX_ITEMS
        self.sel = 0
        self.hover = -1
        self.setMouseTracking(True)

    def set_names(self, names, sel):
        self.names = list(names)
        self.sel = sel
        self.update()

    def _slot_at(self, pos) -> int:
        c = QPointF(self.width() / 2, self.height() / 2)
        r_out = min(self.width(), self.height()) / 2 - 6
        r_in = r_out * 0.32
        d = QPointF(pos) - c
        dist = math.hypot(d.x(), d.y())
        if dist < r_in or dist > r_out:
            return -1
        ang = (math.degrees(math.atan2(d.x(), -d.y())) + 360) % 360
        span = 360 / MAX_ITEMS
        return int(((ang + span / 2) % 360) // span)

    def mouseMoveEvent(self, e):
        h = self._slot_at(e.position())
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, e):
        self.hover = -1
        self.update()

    def mousePressEvent(self, e):
        i = self._slot_at(e.position())
        if i < 0:
            return
        if e.button() == Qt.RightButton:
            self.slotMenu.emit(i, e.globalPosition().toPoint())
        else:
            self.slotClicked.emit(i)

    def paintEvent(self, e):
        pot = theme.potato()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        r_out = min(self.width(), self.height()) / 2 - 6
        r_in = r_out * 0.32
        span = 360.0 / MAX_ITEMS
        f = QFont(P.get("font_body", "Inter"))
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        for i, name in enumerate(self.names):
            start = 90 - (i * span) + span / 2
            path = QPainterPath()
            path.moveTo(c)
            path.arcTo(QRectF(c.x() - r_out, c.y() - r_out, 2 * r_out, 2 * r_out), start, -span)
            path.closeSubpath()
            hole = QPainterPath()
            hole.addEllipse(c, r_in, r_in)
            path = path.subtracted(hole)
            on = i == self.sel
            if pot:
                fill = QColor("#FF3D8B") if on else (QColor("#FFF6A8") if i == self.hover else
                                                     (QColor("#FFE94D") if name else QColor("#FFFBE0")))
                pen = QPen(QColor("#111"), 3 if on else 2, Qt.SolidLine if name or on else Qt.DashLine)
            else:
                fill = QColor("#F2A93B") if on else (QColor(48, 52, 62) if i == self.hover else
                                                     (QColor(34, 37, 44) if name else QColor(22, 24, 29)))
                pen = QPen(QColor("#F2A93B") if on else QColor("#3A3F4A"), 2 if on else 1.2,
                           Qt.SolidLine if name or on else Qt.DashLine)
            p.setPen(pen)
            p.setBrush(fill)
            p.drawPath(path)
            mid = math.radians(i * span)
            tx = c.x() + math.sin(mid) * (r_in + r_out) / 2
            ty = c.y() - math.cos(mid) * (r_in + r_out) / 2
            p.setPen(QColor("#111") if (pot or on) else (QColor(P["text"]) if name else QColor(P["muted"])))
            txt = name if len(name) <= 14 else name[:13] + "…"
            p.drawText(QRectF(tx - 62, ty - 22, 124, 44), Qt.AlignCenter | Qt.TextWordWrap,
                       f"{i + 1}\n{txt}" if name else f"{i + 1}\n+")
        p.setPen(QPen(QColor("#111") if pot else QColor("#3A3F4A"), 2))
        p.setBrush(QColor("#FFE94D") if pot else QColor(13, 14, 17))
        p.drawEllipse(c, r_in - 4, r_in - 4)
        p.setPen(QColor("#111") if pot else QColor(P["muted"]))
        f.setPixelSize(11)
        f.setBold(False)
        p.setFont(f)
        p.drawText(QRectF(c.x() - r_in + 8, c.y() - 30, 2 * r_in - 16, 60), Qt.AlignCenter | Qt.TextWordWrap,
                   tr("Feld wählen,\ndann Sound"))
        p.end()


class WheelEditor(QDialog):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.setWindowTitle(tr("Sound-Rad einrichten"))
        self.resize(940, 560)
        self.pages = clean_pages(ctl.cfg.get("wheel_pages"))
        if not self.pages:                           # Start: Favoriten als erste Seite vorschlagen
            fav = [s["id"] for s in ctl.sounds.sounds if s.get("fav")][:MAX_ITEMS]
            self.pages = [{"name": tr("Seite {n}").format(n=1), "slots": fav + [""] * (MAX_ITEMS - len(fav))}]
        self.page = 0
        self.slot = 0
        root = QVBoxLayout(self)
        hint = QLabel(tr("Feld im Rad anklicken, dann rechts einen Sound anklicken – danach geht es automatisch beim "
                         "nächsten freien Feld weiter. Rechtsklick auf ein Feld = leeren. Im Spiel blätterst du mit "
                         "dem Mausrad zwischen den Seiten, während du die Rad-Taste hältst."))
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        root.addWidget(hint)
        body = QHBoxLayout()
        root.addLayout(body, 1)
        # Seiten
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>" + tr("Seiten") + "</b>"))
        self.plist = QListWidget()
        self.plist.setMaximumWidth(200)
        self.plist.currentRowChanged.connect(self._page_changed)
        self.plist.itemDoubleClicked.connect(lambda _it: self._rename())
        left.addWidget(self.plist, 1)
        b_add = QPushButton(tr("+ Seite"))
        b_add.clicked.connect(self._add_page)
        b_ren = QPushButton(tr("Umbenennen"))
        b_ren.clicked.connect(self._rename)
        b_up = QPushButton("↑")
        b_up.setToolTip(tr("Seite nach vorne"))
        b_up.clicked.connect(lambda: self._move(-1))
        b_dn = QPushButton("↓")
        b_dn.setToolTip(tr("Seite nach hinten"))
        b_dn.clicked.connect(lambda: self._move(1))
        b_del = QPushButton(tr("Seite löschen"))
        b_del.clicked.connect(self._del_page)
        row = QHBoxLayout()
        row.addWidget(b_add)
        row.addWidget(b_up)
        row.addWidget(b_dn)
        left.addLayout(row)
        left.addWidget(b_ren)
        left.addWidget(b_del)
        self.b_add, self.b_del = b_add, b_del
        body.addLayout(left)
        # Rad
        mid = QVBoxLayout()
        self.view = WheelView()
        self.view.slotClicked.connect(self._pick_slot)
        self.view.slotMenu.connect(self._slot_menu)
        mid.addWidget(self.view, 1)
        self.slot_lbl = QLabel()
        self.slot_lbl.setAlignment(Qt.AlignCenter)
        mid.addWidget(self.slot_lbl)
        b_clear = QPushButton(tr("Feld leeren"))
        b_clear.clicked.connect(lambda: self._set_slot(self.slot, ""))
        mid.addWidget(b_clear, 0, Qt.AlignCenter)
        body.addLayout(mid, 1)
        # Sounds
        right = QVBoxLayout()
        right.addWidget(QLabel("<b>" + tr("Sounds") + "</b>"))
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Suchen …"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._fill_sounds)
        right.addWidget(self.search)
        self.slist = QListWidget()
        self.slist.setMinimumWidth(240)
        self.slist.itemClicked.connect(lambda it: self._set_slot(self.slot, it.data(Qt.UserRole), advance=True))
        right.addWidget(self.slist, 1)
        body.addLayout(right)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText(tr("Speichern"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Abbrechen"))
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self._fill_pages()
        self._fill_sounds()

    # ---- Seiten
    def _fill_pages(self):
        self.plist.blockSignals(True)
        self.plist.clear()
        for i, pg in enumerate(self.pages):
            n = sum(1 for x in pg["slots"] if x)
            self.plist.addItem(f"{i + 1}. {pg['name']}  ({n}/{MAX_ITEMS})")
        self.plist.setCurrentRow(self.page)
        self.plist.blockSignals(False)
        self.b_add.setEnabled(len(self.pages) < MAX_PAGES)
        self.b_del.setEnabled(len(self.pages) > 1)
        self._refresh_view()

    def _page_changed(self, row):
        if 0 <= row < len(self.pages):
            self.page = row
            self.slot = self._first_free(0)
            self._refresh_view()

    def _add_page(self):
        if len(self.pages) >= MAX_PAGES:
            return
        self.pages.append({"name": tr("Seite {n}").format(n=len(self.pages) + 1), "slots": [""] * MAX_ITEMS})
        self.page = len(self.pages) - 1
        self.slot = 0
        self._fill_pages()

    def _rename(self):
        pg = self.pages[self.page]
        name, ok = QInputDialog.getText(self, tr("Seite umbenennen"), tr("Name der Seite:"), text=pg["name"])
        if ok and name.strip():
            pg["name"] = name.strip()[:24]
            self._fill_pages()

    def _move(self, d):
        j = self.page + d
        if 0 <= j < len(self.pages):
            self.pages[self.page], self.pages[j] = self.pages[j], self.pages[self.page]
            self.page = j
            self._fill_pages()

    def _del_page(self):
        if len(self.pages) <= 1:
            return
        pg = self.pages[self.page]
        if any(pg["slots"]) and QMessageBox.question(
                self, tr("Seite löschen"), tr("Seite „{n}“ löschen?").format(n=pg["name"])) != QMessageBox.Yes:
            return
        del self.pages[self.page]
        self.page = max(0, self.page - 1)
        self._fill_pages()

    # ---- Felder
    def _names(self):
        by_id = {s["id"]: s["name"] for s in self.ctl.sounds.sounds}
        return [by_id.get(x, "") for x in self.pages[self.page]["slots"]]

    def _refresh_view(self):
        names = self._names()
        self.view.set_names(names, self.slot)
        cur = names[self.slot]
        self.slot_lbl.setText(tr("Feld {n}: ").format(n=self.slot + 1) + (cur or tr("leer")))
        for i in range(self.plist.count()):
            pg = self.pages[i]
            n = sum(1 for x in pg["slots"] if x)
            self.plist.item(i).setText(f"{i + 1}. {pg['name']}  ({n}/{MAX_ITEMS})")

    def _first_free(self, start):
        slots = self.pages[self.page]["slots"]
        for k in range(MAX_ITEMS):
            i = (start + k) % MAX_ITEMS
            if not slots[i]:
                return i
        return start % MAX_ITEMS

    def _pick_slot(self, i):
        self.slot = i
        self._refresh_view()

    def _set_slot(self, i, sid, advance=False):
        slots = self.pages[self.page]["slots"]
        if sid and sid in slots and slots.index(sid) != i:     # nicht doppelt auf einer Seite
            slots[slots.index(sid)] = ""
        slots[i] = sid or ""
        if advance and sid:
            self.slot = self._first_free(i + 1) if "" in slots else (i + 1) % MAX_ITEMS
        self._refresh_view()

    def _slot_menu(self, i, pos):
        self.slot = i
        self._refresh_view()
        m = QMenu(self)
        a_clear = m.addAction(tr("Feld leeren"))
        a_clear.setEnabled(bool(self.pages[self.page]["slots"][i]))
        act = m.exec(pos)
        if act == a_clear:
            self._set_slot(i, "")

    # ---- Sound-Liste
    def _fill_sounds(self, *_):
        t = self.search.text().lower().strip()
        self.slist.clear()
        for s in self.ctl.sounds.sounds:
            if t and t not in s["name"].lower() and t not in s.get("folder", "").lower():
                continue
            label = ("★ " if s.get("fav") else "") + s["name"] + (f"   · {s['folder']}" if s.get("folder") else "")
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, s["id"])
            self.slist.addItem(it)

    def _save(self):
        self.ctl.save_wheel(self.pages, use=True)
        self.accept()
