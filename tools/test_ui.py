"""UI-Smoke-Test: startet das komplette Fenster, klickt durch alle Tabs, macht Screenshots und beendet sich."""
import os, sys, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401  (eigener Datenordner, nur lautlose Geraete)
import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from soundclip.controller import Controller
from soundclip.ui.main_window import MainWindow
from soundclip.ui.widgets import STYLE

OUT = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(OUT, exist_ok=True)
app = QApplication(sys.argv)
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
ctl = Controller()
win = MainWindow(ctl)
ctl.start()
win.show()
errors = []
sys.excepthook = lambda et, ev, tb: errors.append(f"{et.__name__}: {ev}")

# Test-Sound + Test-Clip anlegen
t = np.arange(int(48000 * 1.5)) / 48000
tone = (0.2 * np.sin(2 * np.pi * 440 * t) * np.exp(-t * 2))[:, None].repeat(2, 1).astype("float32")
s1 = ctl.sounds.add_array("Test Airhorn", tone)
s2 = ctl.sounds.add_array("Bruh", tone * 0.5)
ctl.sounds.update(s1["id"], hotkey="ctrl+alt+1")
ctl.soundsChanged.emit()
player = subprocess.Popen([sys.executable, "-c",
    _testenv.PLAYER_PRELUDE + "import numpy as np\n"
    "t=np.arange(int(48000*6))/48000\n"
    "sd.play((0.03*np.sin(2*np.pi*330*t)*(1+np.sin(2*np.pi*2*t))).astype('float32'),48000); sd.wait()"])

steps = []
def step(delay, fn):
    steps.append((delay, fn))

def shot(name):
    def f():
        win.grab().save(os.path.join(OUT, name + ".png"))
    return f

def make_clip():
    print("Verfügbar beim Clip:", {k: v["arg"] for k, v in ctl.sources.available.items()},
          "laufend:", {k: s.status for k, s in ctl.sources.sources.items()}, "player:", player.pid, player.poll())
    ctl.clip_now(4)

created = {}
def open_clip():
    win.tabs.setCurrentWidget(win.clips)
    win.clips.reload()
    if win.clips.list.count():
        win.clips.list.setCurrentRow(0)
        created["meta"] = win.clips.meta
        win.clips.fx_combo.setCurrentIndex(win.clips.fx_combo.findData("potato"))
        win.clips._add_fx()
        win.clips.fx_combo.setCurrentIndex(win.clips.fx_combo.findData("reverb"))
        win.clips._add_fx()
        win.clips._play(True)

def overlay_shot():
    ctl.toast.emit("✂ Clip gespeichert (4s): Python, Mikrofon", "ok")
    ctl.play_sound(s1["id"])
    QTimer.singleShot(300, lambda: win.overlay.grab().save(os.path.join(OUT, "5_overlay.png")))

def rec_start():
    ctl.start_recording()

def rec_stop():
    ctl.stop_recording()

def finish():
    print("Quellen:", [(k, s.status) for k, s in ctl.sources.sources.items()])
    print("Ausgaben:", ctl.mixer.devices, ctl.mixer.errors, {t: ctl.mixer.is_open(t) for t in ("monitor", "virtual")})
    print("Hotkey-Fehler:", ctl.hotkey_errors)
    print("Clips:", [(m["name"], [s["label"] for s in m["stems"]]) for m in ctl.clips.list()[:3]])
    print("Fehler im UI:", errors or "keine")
    # Testdaten aufraeumen
    for s in (s1, s2):
        ctl.sounds.remove(s["id"])
    for m in ctl.clips.list():
        ctl.clips.delete(m)
    player.kill()
    win.quit()

step(3500, shot("1_soundboard"))
step(500, lambda: win.tabs.setCurrentWidget(win.sources))
step(1200, shot("3_quellen"))
step(100, rec_start)
step(1500, rec_stop)
step(100, make_clip)
step(1200, open_clip)
step(800, shot("2_clips"))
step(100, lambda: (win.tabs.setCurrentWidget(win.voice), ctl.set_voice("potato", True)))
step(300, lambda: win.voice.amount.setValue(80))
step(300, lambda: (ctl._on_hotkey("action:voice_down"), ctl._on_hotkey("action:voice_down")))
step(300, lambda: print("Stärke Potato nach Regler 80 und 2x schwächer:", ctl.voice_amount("potato"),
                       "| Mixer:", ctl.mixer.voice.key, round(ctl.mixer.voice.amount, 2)))
step(1200, shot("6_stimme"))
step(100, lambda: ctl.set_voice(enabled=False))
step(100, lambda: win.tabs.setCurrentWidget(win.settings))
step(600, shot("4_einstellungen"))
step(100, overlay_shot)
step(1200, finish)

acc = 0
for d, fn in steps:
    acc += d
    QTimer.singleShot(acc, fn)
app.exec()
print("UI-TEST ENDE")
