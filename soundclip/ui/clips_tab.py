from __future__ import annotations

import datetime as _dt
import subprocess

import soundfile as sf
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
                               QSlider, QSplitter, QToolButton, QVBoxLayout, QWidget, QCheckBox)

from ..config import EXPORT_DIR, SR
from ..effects import CATEGORIES, EFFECTS
from ..library import mix_stems, render
from .widgets import WaveformView


def _fmt_dur(s: float) -> str:
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


class ClipsTab(QWidget):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("page")
        self.meta: dict | None = None
        self.stems: dict = {}
        self.edit: dict = {}
        self.voice = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_edit)
        self._wave_timer = QTimer(self)
        self._wave_timer.setSingleShot(True)
        self._wave_timer.timeout.connect(self._update_wave)

        root = QHBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 20)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split)

        # ---------- Liste
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 10, 0)
        h = QLabel("Clips & Aufnahmen")
        h.setObjectName("h1")
        ll.addWidget(h)
        self.btn_clip = QPushButton("✂ Jetzt clippen")
        self.btn_clip.setObjectName("accent")
        self.btn_clip.clicked.connect(lambda: ctl.clip_now())
        ll.addWidget(self.btn_clip)
        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.currentItemChanged.connect(self._select)
        self.list.itemDoubleClicked.connect(lambda *_: self._play(False))
        ll.addWidget(self.list, 1)
        row = QHBoxLayout()
        b_ren = QPushButton("Umbenennen")
        b_ren.clicked.connect(self._rename)
        b_del = QPushButton("Löschen")
        b_del.setObjectName("danger")
        b_del.clicked.connect(self._delete)
        b_dir = QPushButton("Ordner")
        b_dir.clicked.connect(self._open_dir)
        row.addWidget(b_ren)
        row.addWidget(b_del)
        row.addWidget(b_dir)
        ll.addLayout(row)
        split.addWidget(left)

        # ---------- Editor
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 0, 0, 0)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name")
        self.name.editingFinished.connect(self._name_changed)
        self.name.setStyleSheet("font-size: 13pt; font-weight: 600;")
        rl.addWidget(self.name)
        self.info = QLabel()
        self.info.setObjectName("muted")
        rl.addWidget(self.info)

        lbl = QLabel("Quellen – wähle aus, was im Clip zu hören sein soll")
        lbl.setObjectName("h2")
        rl.addWidget(lbl)
        self.stems_box = QFrame()
        self.stems_grid = QGridLayout(self.stems_box)
        self.stems_grid.setContentsMargins(0, 0, 0, 0)
        self.stems_grid.setColumnStretch(1, 1)
        rl.addWidget(self.stems_box)

        lbl = QLabel("Schneiden – grünen/roten Marker ziehen (Linksklick setzt Start, Rechtsklick Ende)")
        lbl.setObjectName("h2")
        rl.addWidget(lbl)
        self.wave = WaveformView()
        self.wave.rangeChanged.connect(self._range_changed)
        rl.addWidget(self.wave)
        trim_row = QHBoxLayout()
        b_reset = QPushButton("Schnitt zurücksetzen")
        b_reset.clicked.connect(self._reset_trim)
        b_last5 = QPushButton("Nur letzte 5s")
        b_last5.clicked.connect(lambda: self._last(5))
        b_last10 = QPushButton("Nur letzte 10s")
        b_last10.clicked.connect(lambda: self._last(10))
        b_auto = QPushButton("Stille abschneiden")
        b_auto.clicked.connect(self._auto_trim)
        for b in (b_reset, b_last5, b_last10, b_auto):
            trim_row.addWidget(b)
        trim_row.addStretch(1)
        rl.addLayout(trim_row)

        lbl = QLabel("Effekte (werden der Reihe nach angewendet)")
        lbl.setObjectName("h2")
        rl.addWidget(lbl)
        fx_row = QHBoxLayout()
        self.fx_combo = QComboBox()
        self.fx_combo.setMaxVisibleItems(24)
        cat_names = {"Stimme": "— Stimme —", "Klang": "— Klang —", "Raum": "— Raum —", "Clip": "— Nur für Clips —"}
        for cat in CATEGORIES:
            if self.fx_combo.count():
                self.fx_combo.insertSeparator(self.fx_combo.count())
            self.fx_combo.addItem(cat_names[cat], None)
            hdr = self.fx_combo.model().item(self.fx_combo.count() - 1)
            hdr.setEnabled(False)
            for key, spec in EFFECTS.items():
                if spec[1] == cat:
                    self.fx_combo.addItem("    " + spec[0], key)
        self.fx_combo.setCurrentIndex(1)
        fx_row.addWidget(self.fx_combo, 1)
        b_add = QPushButton("+ Effekt")
        b_add.clicked.connect(self._add_fx)
        fx_row.addWidget(b_add)
        rl.addLayout(fx_row)
        self.fx_area = QScrollArea()
        self.fx_area.setWidgetResizable(True)
        self.fx_area.setMinimumHeight(140)
        self.fx_area.setMaximumHeight(230)
        self.fx_inner = QWidget()
        self.fx_inner.setObjectName("page")
        self.fx_layout = QVBoxLayout(self.fx_inner)
        self.fx_layout.setContentsMargins(0, 0, 0, 0)
        self.fx_layout.addStretch(1)
        self.fx_area.setWidget(self.fx_inner)
        rl.addWidget(self.fx_area)

        act = QHBoxLayout()
        self.b_prev = QPushButton("🎧 Vorhören")
        self.b_prev.setToolTip("Nur du hörst es")
        self.b_prev.clicked.connect(lambda: self._play(True))
        self.b_play = QPushButton("▶ Für alle abspielen")
        self.b_play.setToolTip("Du und deine Freunde (virtuelles Mikro)")
        self.b_play.clicked.connect(lambda: self._play(False))
        self.b_stop = QPushButton("■ Stop")
        self.b_stop.clicked.connect(self._stop)
        self.b_sound = QPushButton("➕ Ins Soundboard")
        self.b_sound.setObjectName("accent")
        self.b_sound.clicked.connect(self._to_soundboard)
        self.b_export = QPushButton("💾 Exportieren…")
        self.b_export.clicked.connect(self._export)
        for b in (self.b_prev, self.b_play, self.b_stop):
            act.addWidget(b)
        act.addStretch(1)
        act.addWidget(self.b_export)
        act.addWidget(self.b_sound)
        rl.addLayout(act)
        rl.addStretch(1)
        split.addWidget(right)
        split.setSizes([300, 800])

        self.editor_widgets = [self.name, self.wave, self.fx_combo, b_add, self.b_prev, self.b_play,
                               self.b_stop, self.b_sound, self.b_export, b_reset, b_last5, b_last10, b_auto]
        self._enable(False)
        ctl.clipsChanged.connect(self._on_new_clip)
        self.reload()
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._playhead)
        self.play_timer.start(40)

    # ------------------------------------------------------------ Liste
    def _enable(self, on):
        for w in self.editor_widgets:
            w.setEnabled(on)

    def reload(self, select_id: str | None = None):
        cur = select_id or (self.meta or {}).get("id")
        self.list.blockSignals(True)
        self.list.clear()
        sel_item = None
        for m in self.ctl.clips.list():
            try:
                when = _dt.datetime.fromisoformat(m["created"]).strftime("%d.%m.%Y %H:%M")
            except Exception:
                when = ""
            icon = {"clip": "✂", "recording": "●", "sound": "♪"}.get(m.get("kind"), "✂")
            srcs = ", ".join(s["label"].split(" (")[0] for s in m.get("stems", []))
            it = QListWidgetItem(f"{icon}  {m['name']}\n     {when} · {_fmt_dur(m.get('duration', 0))} · {srcs}")
            it.setData(Qt.UserRole, m)
            self.list.addItem(it)
            if m["id"] == cur:
                sel_item = it
        self.list.blockSignals(False)
        if sel_item:
            same = self.meta is not None and sel_item.data(Qt.UserRole)["id"] == self.meta["id"]
            if same:  # aktuell bearbeiteten Clip nicht neu laden
                self.list.blockSignals(True)
                self.list.setCurrentItem(sel_item)
                self.list.blockSignals(False)
                sel_item.setData(Qt.UserRole, dict(self.meta))
            else:
                self.list.setCurrentItem(sel_item)
        elif self.meta is not None:
            self._select(None)

    def _on_new_clip(self, cid: str):
        # neuen Clip nur automatisch oeffnen, wenn gerade nichts bearbeitet wird
        if self.meta is None and cid:
            self.reload(cid)
        else:
            self.reload()

    def open_clip(self, cid: str):
        self.reload(cid)

    def _select(self, item, *_):
        self._flush()
        self._stop()
        if item is None:
            self.meta, self.stems, self.edit = None, {}, {}
            self._enable(False)
            self.name.clear()
            self.info.clear()
            self.wave.set_audio(None, 0)
            self._build_stems()
            self._build_fx()
            return
        self.meta = dict(item.data(Qt.UserRole))
        try:
            self.stems = self.ctl.clips.stems(self.meta)
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Clip kann nicht geladen werden:\n{e}")
            self.stems = {}
        self.edit = dict(self.meta.get("edit") or {})
        self.edit.setdefault("stems", {})
        self.edit.setdefault("effects", [])
        self.name.setText(self.meta["name"])
        kind = {"clip": "Clip", "recording": "Aufnahme", "sound": "Sound"}.get(self.meta.get("kind"), "Clip")
        self.info.setText(f"{kind} · {len(self.stems)} Quelle(n) · {_fmt_dur(self._duration())}")
        self._enable(True)
        self._build_stems()
        self._build_fx()
        self._update_wave(reset_range="start" not in self.edit)

    def _duration(self) -> float:
        return max((len(a) for a in self.stems.values()), default=0) / SR

    def _rename(self):
        it = self.list.currentItem()
        if not it:
            return
        m = it.data(Qt.UserRole)
        name, ok = QInputDialog.getText(self, "Umbenennen", "Name:", text=m["name"])
        if ok and name.strip():
            self.name.setText(name.strip())
            self._name_changed()

    def _name_changed(self):
        if self.meta and self.name.text().strip() and self.name.text().strip() != self.meta["name"]:
            self.meta["name"] = self.name.text().strip()
            self._save_edit()
            self.reload()

    def _delete(self):
        it = self.list.currentItem()
        if not it:
            return
        m = it.data(Qt.UserRole)
        if QMessageBox.question(self, "Löschen", f"„{m['name']}“ wirklich löschen?") != QMessageBox.Yes:
            return
        self._stop()
        self.meta = None
        self.ctl.clips.delete(m)
        self.reload()
        self._select(self.list.currentItem())

    def _open_dir(self):
        it = self.list.currentItem()
        if it:
            subprocess.Popen(["explorer", str(self.ctl.clips.dir(it.data(Qt.UserRole)))])
        else:
            from ..config import CLIPS_DIR
            subprocess.Popen(["explorer", str(CLIPS_DIR)])

    # ------------------------------------------------------------ Spuren
    def _build_stems(self):
        while self.stems_grid.count():
            w = self.stems_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not self.meta:
            return
        for row, st in enumerate(self.meta.get("stems", [])):
            key = st["key"]
            s = self.edit["stems"].setdefault(key, {"on": True, "gain": 1.0})
            cb = QCheckBox(st["label"])
            cb.setChecked(s.get("on", True))
            cb.setMinimumWidth(220)
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, 200)
            sl.setValue(int(float(s.get("gain", 1.0)) * 100))
            pct = QLabel(f"{sl.value()}%")
            pct.setFixedWidth(42)
            solo = QToolButton()
            solo.setText("🎧")
            solo.setToolTip("Nur diese Quelle vorhören")
            cb.toggled.connect(lambda v, k=key: self._stem_set(k, on=v))
            sl.valueChanged.connect(lambda v, k=key, l=pct: (l.setText(f"{v}%"), self._stem_set(k, gain=v / 100)))
            solo.clicked.connect(lambda _=False, k=key: self._solo(k))
            self.stems_grid.addWidget(cb, row, 0)
            self.stems_grid.addWidget(sl, row, 1)
            self.stems_grid.addWidget(pct, row, 2)
            self.stems_grid.addWidget(solo, row, 3)

    def _stem_set(self, key, **kw):
        self.edit["stems"].setdefault(key, {"on": True, "gain": 1.0}).update(kw)
        self._changed(wave=True)

    def _solo(self, key):
        a = self.stems.get(key)
        if a is None:
            return
        s, e = self._range()
        self._stop()
        self.voice = self.ctl.play_data(a[int(s * SR):int(e * SR)], "Solo", preview=True)

    # ------------------------------------------------------------ Schnitt
    def _range(self):
        d = self._duration()
        s = float(self.edit.get("start", 0.0))
        e = float(self.edit.get("end", d) or d)
        return max(0.0, min(s, d)), max(0.0, min(e, d))

    def _update_wave(self, reset_range=False):
        if not self.meta:
            return
        mix = mix_stems(self.meta, self.stems, self.edit)
        d = len(mix) / SR
        if reset_range:
            self.edit["start"], self.edit["end"] = 0.0, d
        self.wave.set_audio(mix, d)
        s, e = self._range()
        self.wave.set_range(s, e)

    def _range_changed(self, s, e):
        self.edit["start"], self.edit["end"] = round(s, 3), round(e, 3)
        self._changed()

    def _reset_trim(self):
        d = self._duration()
        self.edit["start"], self.edit["end"] = 0.0, d
        self.wave.set_range(0.0, d)
        self._changed()

    def _last(self, sec):
        d = self._duration()
        self.edit["start"], self.edit["end"] = max(0.0, d - sec), d
        self.wave.set_range(*self._range())
        self._changed()

    def _auto_trim(self):
        import numpy as np
        mix = mix_stems(self.meta, self.stems, self.edit)
        if not len(mix):
            return
        env = np.abs(mix).max(axis=1)
        thr = max(0.01, float(env.max()) * 0.05)
        idx = np.nonzero(env > thr)[0]
        if not len(idx):
            return
        pad = int(0.08 * SR)
        s = max(0, idx[0] - pad) / SR
        e = min(len(mix), idx[-1] + pad) / SR
        self.edit["start"], self.edit["end"] = s, e
        self.wave.set_range(s, e)
        self._changed()

    # ------------------------------------------------------------ Effekte
    def _build_fx(self):
        while self.fx_layout.count() > 1:
            w = self.fx_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not self.meta:
            return
        for i, fx in enumerate(self.edit.get("effects", [])):
            spec = EFFECTS.get(fx.get("type"))
            if not spec:
                continue
            row = QFrame()
            row.setMinimumHeight(38)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 6, 2)
            lbl = QLabel(f"{i + 1}. {spec[0]}")
            lbl.setMinimumWidth(200)
            rl.addWidget(lbl)
            if fx["type"] != "reverse":
                sl = QSlider(Qt.Horizontal)
                sl.setRange(0, 100)
                sl.setValue(int(float(fx.get("amount", spec[3])) * 100))
                sl.setToolTip("Stärke")
                sl.valueChanged.connect(lambda v, f=fx: (f.__setitem__("amount", v / 100), self._changed()))
                rl.addWidget(sl, 1)
            else:
                rl.addStretch(1)
            up = QToolButton()
            up.setText("↑")
            up.clicked.connect(lambda _=False, k=i: self._move_fx(k, -1))
            rm = QToolButton()
            rm.setText("✕")
            rm.clicked.connect(lambda _=False, k=i: self._remove_fx(k))
            rl.addWidget(up)
            rl.addWidget(rm)
            self.fx_layout.insertWidget(self.fx_layout.count() - 1, row)

    def _add_fx(self):
        key = self.fx_combo.currentData()
        if not key:
            return
        self.edit.setdefault("effects", []).append({"type": key, "amount": EFFECTS[key][3]})
        self._build_fx()
        self._changed()

    def _remove_fx(self, i):
        fx = self.edit.get("effects", [])
        if 0 <= i < len(fx):
            fx.pop(i)
        self._build_fx()
        self._changed()

    def _move_fx(self, i, d):
        fx = self.edit.get("effects", [])
        j = i + d
        if 0 <= i < len(fx) and 0 <= j < len(fx):
            fx[i], fx[j] = fx[j], fx[i]
            self._build_fx()
            self._changed()

    # ------------------------------------------------------------ Speichern/Rendern
    def _changed(self, wave=False):
        self._save_timer.start(600)
        if wave:
            self._wave_timer.start(150)

    def _flush(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_edit()

    def _save_edit(self):
        if not self.meta:
            return
        self.meta["edit"] = self.edit
        try:
            self.ctl.clips.save_meta(self.meta)
        except Exception:
            pass
        it = self.list.currentItem()
        if it and it.data(Qt.UserRole).get("id") == self.meta["id"]:
            it.setData(Qt.UserRole, dict(self.meta))

    def _rendered(self):
        if not self.meta:
            return None
        try:
            return render(self.meta, self.stems, self.edit)
        except Exception as e:
            QMessageBox.warning(self, "Fehler beim Rendern", str(e))
            return None

    def _play(self, preview: bool):
        data = self._rendered()
        if data is None or not len(data):
            self.ctl.toast.emit("Nichts zu hören – ist mindestens eine Quelle aktiv?", "warn")
            return
        self._stop()
        self.voice = self.ctl.mixer.play(data, sound_id="__preview__", name=self.meta["name"], preview=preview)

    def _stop(self):
        self.ctl.mixer.stop("__preview__")
        self.voice = None
        self.wave.playhead = -1
        self.wave.update()

    def _playhead(self):
        v = self.voice
        if v is None:
            return
        if v.finished:
            self.voice = None
            self.wave.playhead = -1
        else:
            s, e = self._range()
            self.wave.playhead = v.progress() * (e - s)
        self.wave.update()

    def _to_soundboard(self):
        data = self._rendered()
        if data is None or not len(data):
            return
        name, ok = QInputDialog.getText(self, "Ins Soundboard", "Name des Sounds:", text=self.meta["name"])
        if not ok or not name.strip():
            return
        s = self.ctl.sounds.add_array(name.strip(), data)
        self.ctl.soundsChanged.emit()
        self.ctl.toast.emit(f"„{s['name']}“ ist jetzt im Soundboard – Rechtsklick drauf für Hotkey", "ok")

    def _export(self):
        data = self._rendered()
        if data is None or not len(data):
            return
        from ..capture import safe_name
        default = str(EXPORT_DIR / (safe_name(self.meta["name"]) + ".wav"))
        path, _ = QFileDialog.getSaveFileName(self, "Exportieren", default, "WAV (*.wav);;FLAC (*.flac);;OGG (*.ogg)")
        if not path:
            return
        try:
            sub = "PCM_16" if path.lower().endswith((".wav", ".flac")) else None
            sf.write(path, data, SR, subtype=sub)
            self.ctl.toast.emit("Exportiert: " + path, "ok")
        except Exception as e:
            QMessageBox.warning(self, "Export fehlgeschlagen", str(e))

    def shutdown(self):
        self._flush()
