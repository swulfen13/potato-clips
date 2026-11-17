"""UI-Smoke-Test: startet das komplette Fenster, klickt durch alle Tabs, macht Screenshots und beendet sich."""
import os, sys, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401  (eigener Datenordner, nur lautlose Geraete)
import numpy as np
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

MODE = os.environ.get("POTATO_THEME", "pro")
LANG = os.environ.get("POTATO_LANG", "de")
OUT = os.path.join(os.path.dirname(__file__), "shots", f"{MODE}_{LANG}")
os.makedirs(OUT, exist_ok=True)
app = QApplication(sys.argv)
from soundclip import i18n
from soundclip.ui import theme
theme.set_mode(MODE)
i18n.setup(LANG, MODE)
for _f in (Path(__file__).resolve().parent.parent / "assets" / "fonts").glob("*.ttf"):
    QFontDatabase.addApplicationFont(str(_f))
i18n.install(app)
from soundclip.controller import Controller
from soundclip.ui.main_window import MainWindow
from soundclip.ui.widgets import STYLE
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
ctl.sounds.update(s1["id"], hotkey="ctrl+alt+1", fav=True, folder="Memes")
ctl.sounds.update(s2["id"], trigger="bruh", folder="Reaktionen")
ctl.cfg["sound_folders"] = ["Memes", "Reaktionen"]
ctl.soundsChanged.emit()
player = subprocess.Popen([sys.executable, "-c",
    _testenv.PLAYER_PRELUDE + "import numpy as np\n"
    "t=np.arange(int(48000*30))/48000\n"
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

GER = __import__("re").compile(r"[äöüÄÖÜß]|\b(und|nicht|der|die|das|mit|ein|eine|ist|für|auf|wird|deine|Stimme|"
                                r"Einstellungen|Quellen|Aufnahme|Lautstärke|Sounds hinzufügen|Ordner|Mikrofon)\b")


def german_leftovers():
    """Im englischen Modus: sichtbare Texte, die noch deutsch aussehen."""
    from PySide6.QtWidgets import QAbstractButton, QComboBox, QGroupBox, QLabel, QWidget
    found = set()
    for w in [win] + win.findChildren(QWidget):
        texts = []
        if isinstance(w, (QLabel, QAbstractButton)):
            texts.append(w.text())
        if isinstance(w, QGroupBox):
            texts.append(w.title())
        if isinstance(w, QComboBox):
            texts += [w.itemText(i) for i in range(w.count())]
        texts.append(w.toolTip())
        for t in texts:
            if t and GER.search(t) and "Potato" not in t[:7]:
                found.add(t.replace("\n", " ")[:110])
    return sorted(found)


new_checks = {}


def remote_test():
    """Stream-Deck-Links gegen den echten Controller (Server nur auf 127.0.0.1)."""
    import json, urllib.request
    ctl.cfg.update(api_enabled=True, remote_enabled=False, remote_port=18766)
    ctl.remote.sync()
    new_checks["server lokal"] = ctl.remote.running and ctl.remote.host == "127.0.0.1"
    st = json.loads(urllib.request.urlopen(ctl.remote.local_url("/api/state"), timeout=5).read())
    new_checks["status"] = [x["name"] for x in st["sounds"]][:1] == ["Test Airhorn"] and "Memes" in st["folders"]
    urllib.request.urlopen(ctl.remote.local_url(f"/api/play/{s2['id']}"), timeout=5).read()
    urllib.request.urlopen(ctl.remote.local_url("/api/random?folder=Memes"), timeout=5).read()


def remote_check():
    ids = {v.sound_id for v in ctl.mixer.playing()}
    new_checks["Befehle ausgefuehrt"] = s2["id"] in ids and s1["id"] in ids
    print("Neue Funktionen:", new_checks)


def pykey():
    return next((k for k in ctl.app_labels() if "python" in k), "")


def voice_cmd_test():
    """Sprachbefehl 'Potato, clip Python' (wie aus der Spracherkennung) + Ansage + neue Handy-Befehle."""
    import json, urllib.request
    ctl.announceReady.connect(lambda d, to_all: new_checks.__setitem__("Ansage", (len(d) > 10000, to_all)))
    k = pykey()
    new_checks["Test-Player als Quelle"] = bool(k)
    created["n_clips"] = len(ctl.clips.clips) if hasattr(ctl.clips, "clips") else None
    ctl.voiceCommand.emit("clip", [k], "Python")
    st = json.loads(urllib.request.urlopen(ctl.remote.local_url("/api/state"), timeout=5).read())
    new_checks["Dashboard-Status"] = any(a["key"] == k for a in st["apps"]) and "rec" in st and "amount" in st
    urllib.request.urlopen(ctl.remote.local_url("/api/voice/amount/40"), timeout=5).read()
    req = urllib.request.Request(ctl.remote.local_url("/api/say"), method="POST",
                                 data=json.dumps({"text": "Hallo Test", "voice": "", "fx": True}).encode(),
                                 headers={"Content-Type": "application/json"})
    new_checks["Vorlesen angenommen"] = json.loads(urllib.request.urlopen(req, timeout=5).read())["ok"]
    try:
        urllib.request.urlopen(ctl.remote.local_url("/api/clip?apps=app:gibtsnicht.exe"), timeout=5)
        new_checks["falsche App abgelehnt"] = False
    except Exception:
        new_checks["falsche App abgelehnt"] = True
    ctl.speechReady.connect(lambda d, t: new_checks.__setitem__("Vorlesen fertig", t == "Hallo Test" and len(d) > 1000))


def voice_cmd_check():
    import json
    from soundclip.config import CLIPS_DIR
    metas = []
    for d in CLIPS_DIR.iterdir():
        try:
            metas.append(json.loads((d / "meta.json").read_text(encoding="utf-8")))
        except Exception:
            pass
    metas.sort(key=lambda m: m["created"])
    last = metas[-1] if metas else {}
    new_checks["Clip nur Python"] = [st["key"] for st in last.get("stems", [])] == [pykey()]
    print("Letzter Clip:", last.get("name"), [st["key"] for st in last.get("stems", [])], "erwartet:", pykey(),
          "Anzahl Clips:", len(metas))
    new_checks["Staerke 40"] = abs(ctl.voice_amount() - 0.4) < 0.01
    print("Neue Funktionen 1.3:", new_checks)
    ctl.mixer.stop_all()


def wizard_lang_test():
    from soundclip import i18n
    from soundclip.ui.wizard import SetupWizard
    lang0, mode0 = i18n.LANG, i18n.MODE
    w = SetupWizard(ctl, win)
    w.show()
    app.processEvents()
    before = w.next.text()
    w.lang.setCurrentIndex(w.lang.findData("en" if lang0 == "de" else "de"))
    for _ in range(5):
        app.processEvents()
    after = w.next.text()
    w.grab().save(os.path.join(OUT, "8_assistent_umgeschaltet.png"))
    new_checks["Assistent wechselt Sprache sofort"] = bool(before and after and before != after)
    print("Assistent:", before, "->", after)
    w._restarting = True          # im Test nicht neu starten
    w.reject()
    for _ in range(5):
        app.processEvents()
    i18n.setup(lang0, mode0)
    ctl.cfg["language"] = "auto"
    w.setParent(None)
    w.deleteLater()
    print("Sprache nach Assistent-Test:", i18n.LANG)


dialogs = []


def dialog_shots():
    from soundclip import i18n
    print("Sprache bei Dialogen:", i18n.LANG)
    from soundclip.ui.soundboard_tab import SoundDialog, TrimDialog
    from soundclip.ui.clips_tab import VideoDialog
    from soundclip.ui.settings_tab import QrView
    for name, d in (("7a_sound_dialog", SoundDialog(ctl.sounds.get(s2["id"]), win.soundboard, ctl.sounds.folders())),
                    ("7b_zuschneiden", TrimDialog(ctl, ctl.sounds.get(s1["id"]), win.soundboard)),
                    ("7c_video_dialog", VideoDialog(ctl, "Clip 17.11. 12:00:00", 12.0, win.clips))):
        d.show()
        app.processEvents()
        d.grab().save(os.path.join(OUT, name + ".png"))
        d.hide()
        dialogs.append(d)
    q = QrView()
    q.set_text("http://192.168.178.20:8765/?t=abcdefghijklmnop")
    q.grab().save(os.path.join(OUT, "7d_qr.png"))


def finish():
    print("Quellen:", [(k, s.status) for k, s in ctl.sources.sources.items()])
    print("Ausgaben:", ctl.mixer.devices, ctl.mixer.errors, {t: ctl.mixer.is_open(t) for t in ("monitor", "virtual")})
    print("Hotkey-Fehler:", ctl.hotkey_errors)
    print("Clips:", [(m["name"], [s["label"] for s in m["stems"]]) for m in ctl.clips.list()[:3]])
    print("Fehler im UI:", errors or "keine")
    if LANG == "en":
        left = german_leftovers()
        print("Deutsch uebrig:", len(left))
        for t in left:
            print("   ", t)
    # Testdaten aufraeumen
    for s in (s1, s2):
        ctl.sounds.remove(s["id"])
    for m in ctl.clips.list():
        ctl.clips.delete(m)
    player.kill()
    win.quit()

step(3500, shot("1_soundboard"))
step(100, lambda: win.soundboard._set_folder("*fav"))
step(500, shot("1b_soundboard_favoriten"))
step(100, lambda: win.soundboard._set_folder(""))
step(100, remote_test)
step(400, remote_check)
step(100, lambda: ctl.mixer.stop_all())
step(100, wizard_lang_test)
step(100, dialog_shots)
step(500, lambda: win.tabs.setCurrentWidget(win.sources))
step(1200, shot("3_quellen"))
step(100, rec_start)
step(1500, rec_stop)
step(100, make_clip)
step(1200, open_clip)
step(800, shot("2_clips"))
step(100, voice_cmd_test)
step(4000, voice_cmd_check)
step(100, lambda: (win.tabs.setCurrentWidget(win.voice), ctl.set_voice("potato", True)))
step(300, lambda: win.voice.amount.setValue(80))
step(300, lambda: (ctl._on_hotkey("action:voice_down"), ctl._on_hotkey("action:voice_down")))
step(300, lambda: print("Stärke Potato nach Regler 80 und 2x schwächer:", ctl.voice_amount("potato"),
                       "| Mixer:", ctl.mixer.voice.key, round(ctl.mixer.voice.amount, 2)))
step(1200, shot("6_stimme"))
step(100, lambda: ctl.set_voice(enabled=False))
step(100, lambda: win.tabs.setCurrentWidget(win.settings))
step(600, shot("4_einstellungen"))
step(100, lambda: win.settings._goto("discord"))
step(500, shot("4b_einstellungen_discord"))
step(100, lambda: win.settings._goto("hotkeys"))
step(500, shot("4c_einstellungen_hotkeys"))
step(100, lambda: win.settings._goto("clips"))
step(500, shot("4d_einstellungen_clips"))
step(100, lambda: win.settings._goto("soundboard"))
step(500, shot("4e_einstellungen_soundboard"))
step(100, lambda: win.settings._goto("fernbedienung"))
step(500, shot("4f_einstellungen_fernbedienung"))
step(100, lambda: win.settings._goto("trigger"))
step(500, shot("4g_einstellungen_trigger"))
step(100, overlay_shot)
step(1200, finish)

acc = 0
for d, fn in steps:
    acc += d
    QTimer.singleShot(acc, fn)
app.exec()
print("UI-TEST ENDE")
