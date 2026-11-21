"""1.7 pruefen - eigenes Sound-Rad mit Seiten (lautlos, keine echten Eingaben, eigener Datenordner)."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401

ok = True


def check(name, cond, info=""):
    global ok
    ok = ok and bool(cond)
    print(("OK    " if cond else "FEHLER"), name, info, flush=True)


from PySide6.QtCore import QObject, QPointF, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
from soundclip import inputs  # noqa: E402
from soundclip.ui import wheel as wh  # noqa: E402

# ---- Seiten absichern
pg = wh.clean_pages([{"name": "A", "slots": ["1", "2"]}, "kaputt", {"slots": ["x"] * 12}] + [{"name": "p"}] * 10)
check("Seiten abgesichert", len(pg) == wh.MAX_PAGES and pg[0]["slots"] == ["1", "2"] + [""] * 6
      and len(pg[1]["slots"]) == 8 and pg[1]["name"], str(pg[1]["name"]))


class Lib:
    sounds = [{"id": str(i), "name": f"s{i}", "fav": i in (3, 9), "folder": "memes" if i >= 10 else ""}
              for i in range(22)]


class Ctl(QObject):
    wheelHold = Signal(bool)
    toast = Signal(str, str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = {"hotkeys": {"wheel_hold": "pad:lb+rb"}, **cfg}
        self.sounds = Lib()
        self.played = []
        self.stats = type("S", (), {"add": lambda *a: None})()
        self.hotkeys = type("H", (), {"watcher": lambda _s: fake})()
        self.src = None

    def wheel_source(self):
        return self.src or self.cfg.get("wheel_source", "fav")

    def play_sound(self, sid):
        self.played.append(sid)


custom = {"wheel_source": "custom", "wheel_pages": [
    {"name": "Lachen", "slots": ["1", "", "2", "", "", "", "", ""]},
    {"name": "Leer", "slots": [""] * 8},
    {"name": "Memes", "slots": ["10", "11", "12", "gibtsnicht", "", "", "", ""]}]}
pages = wh.wheel_pages(Ctl(custom))
check("Eigene Seiten (leere Seite weg, Luecken bleiben)", [p["name"] for p in pages] == ["Lachen", "Memes"]
      and [x and x["id"] for x in pages[0]["items"]] == ["1", None, "2"]
      and [x and x["id"] for x in pages[1]["items"]] == ["10", "11", "12"])
c = Ctl(custom)
c.src = "page:2"
check("Profil: nur eine Seite", [p["name"] for p in wh.wheel_pages(c)] == ["Memes"])
c.src = "page:9"
check("Kaputte Seitennummer -> Favoriten", wh.wheel_pages(c)[0]["items"][0]["id"] == "3")
fav = wh.wheel_pages(Ctl({"wheel_source": "fav"}))
check("Favoriten zuerst, auf Seiten verteilt", [x["id"] for x in fav[0]["items"][:2]] == ["3", "9"]
      and len(fav) == 3 and len(fav[0]["items"]) == 8, f"{len(fav)} Seiten")
mem = wh.wheel_pages(Ctl({"wheel_source": "memes"}))
check("Ordner mit 12 Sounds = 2 Seiten", [len(p["items"]) for p in mem] == [8, 4])
check("Leere eigene Auswahl -> Favoriten", wh.wheel_pages(Ctl({"wheel_source": "custom", "wheel_pages": []}))[0]
      ["items"][0]["id"] == "3")

# ---- Mausrad aus Raw Input
fake = inputs.InputWatcher(lambda c, p: None)
fake.track_motion = lambda on: None
fake.wheel = -250
check("Mausrad-Rasten", fake.take_wheel() == -2 and fake.wheel == -10)
fake.wheel = 0
import ctypes  # noqa: E402

check("Mausrad-Richtung aus Raw-Daten", ctypes.c_short(0xFF88).value == -120 and inputs.RI_MOUSE_WHEEL == 0x0400)

# ---- Rad im Spiel: blaettern + abspielen
ctl = Ctl(custom)
w = wh.SoundWheel(ctl)
fake._held = {"pad:lb+rb"}
w.hold(True)
app.processEvents()
check("Rad offen auf Seite 1", w.isVisible() and w.page == 0 and len(w.items) == 3)
os.makedirs(os.path.join(os.path.dirname(__file__), "shots"), exist_ok=True)
w.grab().save(os.path.join(os.path.dirname(__file__), "shots", "rad_seite1.png"))
fake.wheel = -120                       # eine Raste nach unten -> naechste Seite
t0 = time.time()
while time.time() - t0 < 0.2:
    app.processEvents()
    time.sleep(0.01)
check("Mausrad blaettert", w.page == 1 and [x["id"] for x in w.items] == ["10", "11", "12"])
fake.wheel = -120                       # weiter -> wieder Seite 1 (rundherum)
t0 = time.time()
while time.time() - t0 < 0.2:
    app.processEvents()
    time.sleep(0.01)
check("Rundherum blaettern", w.page == 0)
fake.wheel = 120
t0 = time.time()
while time.time() - t0 < 0.2:
    app.processEvents()
    time.sleep(0.01)
fake.dx, fake.dy = 0, -200              # nach oben = Feld 1
fake.mouse_ok = True
t0 = time.time()
while time.time() - t0 < 0.2:
    app.processEvents()
    time.sleep(0.01)
fake._held = set()
t0 = time.time()
while time.time() - t0 < 0.4:
    app.processEvents()
    time.sleep(0.01)
check("Sound von Seite 2 gespielt", ctl.played == ["10"] and not w.isVisible(), str(ctl.played))
check("Merkt sich die Seite", getattr(ctl, "_wheel_page", None) == 1)
# leeres Feld spielt nichts
ctl2 = Ctl(custom)
w2 = wh.SoundWheel(ctl2)
fake._held = {"pad:lb+rb"}
fake.dx, fake.dy = 0, 0
w2.hold(True)
app.processEvents()
fake.dx, fake.dy = 200, 0               # rechts = Feld 3? bei 3 Feldern: rechts-unten -> Feld 2 (leer)
w2.items = [ctl2.sounds.sounds[1], None, ctl2.sounds.sounds[2]]
w2._update_sel()
sel = w2.sel
fake._held = set()
t0 = time.time()
while time.time() - t0 < 0.4:
    app.processEvents()
    time.sleep(0.01)
check("Leeres Feld spielt nichts", sel == 1 and ctl2.played == [], f"sel={sel} {ctl2.played}")

# ---- Editor-Rad: Felder anklicken
from soundclip.ui.wheel_editor import WheelView  # noqa: E402

v = WheelView()
v.resize(400, 400)
check("Editor: Feld oben = 1, rechts = 3, links = 7",
      v._slot_at(QPointF(200, 30)) == 0 and v._slot_at(QPointF(370, 200)) == 2 and v._slot_at(QPointF(30, 200)) == 6
      and v._slot_at(QPointF(200, 200)) == -1)
for x in (w, w2, v):
    x.close()
    x.deleteLater()
app.processEvents()
# ---- Mikro weg -> Ersatz (nie das virtuelle Kabel)
from soundclip.capture import pick_mic  # noqa: E402

caps = [{"id": "cable", "name": "CABLE Output (VB-Audio Virtual Cable)", "default": False},
        {"id": "ow", "name": "Kopfhörer (OW810)", "default": True},
        {"id": "cam", "name": "Mikrofon (EMEET SmartCam Nova)", "default": False}]
check("Mikro da -> bleibt", pick_mic("cam", caps) == "cam")
check("Mikro weg -> Windows-Standard", pick_mic("nothing-ear", caps) == "ow")
check("Standard bleibt Standard", pick_mic("default", caps) == "default")
caps2 = [dict(caps[0], default=True), dict(caps[2])]
check("Standard ist das Kabel -> echtes Mikro", pick_mic("weg", caps2) == "cam" and pick_mic("default", caps2) == "cam")
check("Liste leer -> nichts aendern", pick_mic("x", []) == "x")
from soundclip.config import Config  # noqa: E402
from soundclip.capture import SourceManager  # noqa: E402


class _Mix:
    mic_effective = None
    applied = 0

    def apply_voice_path(self):
        self.applied += 1


cfgm = Config()
cfgm["mic_device"] = "nothing-ear"
smx = SourceManager.__new__(SourceManager)
smx.cfg, smx.mixer, smx.devices = cfgm, _Mix(), {"capture": caps, "render": []}
said = []
smx.on_mic_fallback = said.append
smx._check_mic()
check("Ersatz-Mikro gemeldet", smx.mixer.mic_effective == "ow" and said == ["Kopfhörer (OW810)"], str(said))
smx.devices["capture"] = caps + [{"id": "nothing-ear", "name": "Kopfhörer (Nothing Ear Hands-Free)"}]
smx._check_mic()
check("Mikro wieder da -> zurueck", smx.mixer.mic_effective == "nothing-ear" and smx.mixer.applied == 1)

# ---- Kopfhoerer weg -> Ersatz-Ausgabe (nie das virtuelle Kabel), und zurueck wenn er wieder da ist
from soundclip.mixer import Mixer  # noqa: E402

cfgo = Config()
cfgo["monitor_device"] = "Kopfhörer (Nothing Ear)"
cfgo["virtual_device"] = "auto"
mx = Mixer(cfgo)
mx._open = lambda t: True
mx.close = lambda: None
mx.apply_voice_path = lambda: None
devs = [{"id": "cab", "name": "CABLE Input (VB-Audio Virtual Cable)", "default": True},
        {"id": "steam", "name": "Lautsprecher (Steam Streaming Speakers)", "default": False},
        {"id": "ow", "name": "Kopfhörer (OW810)", "default": False}]
mx.reopen(devs)
check("Kopfhoerer weg, Standard ist Kabel -> echte Ausgabe", mx._want["monitor"] == ("ow", "Kopfhörer (OW810)"),
      str(mx._want["monitor"]))
re_ = []
mx.reopen = lambda d=None: re_.append(1)
devs2 = [dict(devs[0], default=False), dict(devs[1]), dict(devs[2], default=True)]
mx.watchdog(devs2)
check("Ersatz folgt dem Windows-Standard", re_ == [1])
mx._default_id = "ow"
mx.watchdog(devs2 + [{"id": "ne", "name": "Kopfhörer (Nothing Ear)", "default": False}])
check("Kopfhoerer wieder da -> zurueck", re_ == [1, 1])

print("ALLES OK" if ok else "ES GIBT FEHLER", flush=True)
sys.stdout.flush()
os._exit(0 if ok else 1)
