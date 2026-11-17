"""Neue Funktionen 1.5 pruefen - lautlos, eigener Datenordner, keine echten Maus-/Tasten-Eingaben:
Maus/Controller-Logik, Effekte pro Sound, Statistik + Wrapped-Bild, Backup (inkl. boesartiger Dateien),
Clips in Text (Windows-Sprachausgabe nur als Datei), Untertitel-Video, Sound-Rad-Auswahl."""
import json
import os
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401
import numpy as np

ok = True


def check(name, cond, info=""):
    global ok
    ok = ok and bool(cond)
    print(("OK    " if cond else "FEHLER"), name, info, flush=True)


from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
SR = 48000
t = np.arange(SR) / SR
tone = (0.4 * np.sin(2 * np.pi * 330 * t))[:, None].repeat(2, 1).astype(np.float32)

# ---------------------------------------------------------------- 1) Maus & Controller (nur Logik)
from soundclip import inputs  # noqa: E402

check("parse Maus", inputs.parse("ctrl+mouse:x2") == ("mouse", "x2", ("ctrl",)))
check("parse Pad", inputs.parse("pad:lb+a") == ("pad", frozenset({"lb", "a"})))
check("parse Unsinn", inputs.parse("mouse:x9") is None and inputs.parse("pad:zz") is None)
check("pad_combo sortiert", inputs.pad_combo({"a", "lb"}) == "pad:lb+a")
check("pretty", "5" in inputs.pretty("mouse:x2") and "LB" in inputs.pretty("pad:lb+a"))
events = []
w = inputs.InputWatcher(lambda c, p: events.append((c, p)))
w.combos = {"pad:lb+a", "mouse:x1", "ctrl+mouse:x2"}
w._mods = lambda: ()
w._pad_update(frozenset({"lb"}))
w._pad_update(frozenset({"lb", "a"}))
w._pad_update(frozenset({"lb", "a"}))
w._pad_update(frozenset())
check("Pad-Kombi einmal gedrueckt + losgelassen", events == [("pad:lb+a", True), ("pad:lb+a", False)], str(events))
events.clear()
w._mouse_event("x1", True)
w._mouse_event("x1", False)
w._mouse_event("x2", True)        # ohne Strg -> nicht belegt
w._mouse_event("x2", False)
check("Maus 4 ausgeloest, Maus 5 ohne Strg nicht", events == [("mouse:x1", True), ("mouse:x1", False)], str(events))
events.clear()
w._mods = lambda: ("ctrl",)
w._mouse_event("x2", True)
w._mouse_event("x2", False)
check("Strg+Maus 5", events == [("ctrl+mouse:x2", True), ("ctrl+mouse:x2", False)], str(events))
got = []
w.capture = got.append
w._pad_update(frozenset({"rb"}))
w._pad_update(frozenset({"rb", "y"}))
w._pad_update(frozenset())
check("Aufnahme Controller-Kombi", got == ["pad:rb+y"], str(got))
check("XInput ladbar", inputs._load_xinput() is not None)
import ctypes  # noqa: E402

check("Raw-Input-Layout wie winuser.h", inputs.RAWMOUSE.usButtonFlags.offset == 4
      and inputs.RAWMOUSE.lLastX.offset == 12 and ctypes.sizeof(inputs.RAWMOUSE) == 24
      and ctypes.sizeof(inputs.RAWINPUTHEADER) == 24,
      f"flags@{inputs.RAWMOUSE.usButtonFlags.offset} size={ctypes.sizeof(inputs.RAWMOUSE)}")
# Ein echtes Raw-Input-Paket nachbauen (nur Speicher, keine Eingabe) und so lesen wie die App
raw = (ctypes.c_ubyte * 48)()
ctypes.c_uint32.from_buffer(raw, 0).value = 0                  # RIM_TYPEMOUSE
ctypes.c_uint16.from_buffer(raw, 24 + 4).value = 0x0080        # RI_MOUSE_BUTTON_4_UP ... Taste 4 hoch
ctypes.c_int32.from_buffer(raw, 24 + 12).value = -7
pkt = inputs.RAWINPUT.from_buffer(raw)
check("Maustaste aus Raw-Paket gelesen", pkt.mouse.usButtonFlags == 0x0080 and pkt.mouse.lLastX == -7)
check("Gemeinsame Abfrage", inputs.shared() is inputs.shared(lambda c, p: None))

from soundclip.hotkeys import HotkeyManager  # noqa: E402

hm = HotkeyManager()
fired = []
hm.triggered.connect(fired.append)
errs = hm.set_bindings({"action:clip": "mouse:x1", "action:wheel_hold": "pad:lb+rb"})
check("Hotkeys mit Maus/Pad ohne Fehler", not errs, str(errs))
hm._special_event("mouse:x1", True)
hm._special_event("pad:lb+rb", True)
hm._special_event("pad:lb+rb", False)
check("Hotkey-Weiterleitung (halten = down/up)",
      fired == ["action:clip", "action:wheel_hold:down", "action:wheel_hold:up"], str(fired))
wat = hm.watcher()
t0 = time.time()
while not wat.mouse_ok and time.time() - t0 < 3:
    time.sleep(0.05)
check("Raw Input angemeldet (nur zuhoeren)", wat.mouse_ok)
hm.set_bindings({})
hm.shutdown()

# ---------------------------------------------------------------- 2) Effekte pro Sound
from soundclip.library import SoundLibrary  # noqa: E402

lib = SoundLibrary()
s = lib.add_array("Testton", tone)
plain, g0 = lib.playable(s, True)
lib.update(s["id"], fx={"preset": "robot", "amount": 0.8})
s = lib.get(s["id"])
fxd, g1 = lib.playable(s, True)
check("Effekt veraendert den Sound", fxd.shape[1] == 2 and not np.allclose(plain[:len(fxd)], fxd[:len(plain)]))
t0 = time.time()
fxd2, _ = lib.playable(s, True)
check("Effekt wird zwischengespeichert", fxd2 is fxd and time.time() - t0 < 0.05)
check("Kein Clipping", float(np.abs(fxd * g1).max()) <= 1.0, f"{float(np.abs(fxd * g1).max()):.2f}")
from soundclip import packs  # noqa: E402

pk = os.path.join(tempfile.gettempdir(), "potato_v15_test.potatopack")
try:
    packs.export_pack(lib, [s["id"]], pk)
    with zipfile.ZipFile(pk) as z:
        man = json.loads(z.read(next(n for n in z.namelist() if n.endswith(".json"))))
    check("Pack enthaelt Effekt", "robot" in json.dumps(man), "")
except Exception as e:
    check("Pack enthaelt Effekt", False, repr(e))
finally:
    if os.path.exists(pk):
        os.remove(pk)

# ---------------------------------------------------------------- 3) Statistik & Wrapped
from soundclip import stats as stmod  # noqa: E402

st = stmod.Stats()
for _ in range(5):
    st.sound(s["id"], "Testton")
st.add("clips", 3)
st.add("autoclips")
st.voice("robot", 125)
st.save()
st2 = stmod.Stats()
sm = st2.summary(lib)
check("Statistik gespeichert + geladen", sm["plays"] == 5 and sm["clips"] == 3 and sm["top"][0] == ("Testton", 5),
      str(sm["top"]))
check("Lieblings-Stimme", sm["voice_top"] == "robot" and sm["voice_minutes"] == 2)
check("Titel", stmod.title_for(sm)[0] == "Frische Kartoffel")
from soundclip.ui import wrapped_tab  # noqa: E402

for pot in (False, True):
    img = wrapped_tab.render_wrapped(sm, pot)
    px = {img.pixel(x, y) for x in range(0, 1080, 37) for y in range(0, 1920, 41)}
    check(f"Wrapped-Bild ({'Potato' if pot else 'Profi'})", img.width() == 1080 and img.height() == 1920
          and len(px) > 6, f"{len(px)} Farben")
check("Wrapped leer klappt", not wrapped_tab.render_wrapped({**sm, "plays": 0, "top": [], "voice_top": ""},
                                                             False).isNull())

# ---------------------------------------------------------------- 4) Sound-Rad
from soundclip.ui.wheel import wheel_items  # noqa: E402


class FakeCtl:
    def __init__(self, cfg, sounds):
        self.cfg = cfg
        self.sounds = sounds


class FakeLib:
    sounds = [{"id": str(i), "name": f"s{i}", "fav": i in (5, 7), "folder": "memes" if i < 3 else ""}
              for i in range(12)]


items = wheel_items(FakeCtl({"wheel_source": "fav"}, FakeLib()))
check("Rad: Favoriten zuerst, max 8", [x["id"] for x in items[:2]] == ["5", "7"] and len(items) == 8)
items = wheel_items(FakeCtl({"wheel_source": "memes"}, FakeLib()))
check("Rad: Ordner", [x["id"] for x in items] == ["0", "1", "2"])

# Rad geht zu, auch wenn das Loslassen nicht gemeldet wird
from soundclip.ui.wheel import SoundWheel  # noqa: E402
from PySide6.QtCore import QObject, Signal  # noqa: E402


class WheelCtl(QObject):
    wheelHold = Signal(bool)
    toast = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.cfg = {"wheel_source": "fav", "hotkeys": {"wheel_hold": "pad:lb+rb"}}
        self.sounds = FakeLib()
        self.played = []
        self.stats = type("S", (), {"add": lambda *a: None})()
        self.hotkeys = type("H", (), {"watcher": lambda _s: wat_fake})()

    def play_sound(self, sid):
        self.played.append(sid)


wat_fake = inputs.InputWatcher(lambda c, p: None)
wat_fake.track_motion = lambda on: None
wctl = WheelCtl()
wheel = SoundWheel(wctl)
wat_fake._held = {"pad:lb+rb"}
wheel.hold(True)
t0 = time.time()
while time.time() - t0 < 0.5:
    app.processEvents()
    time.sleep(0.01)
check("Rad bleibt offen, solange gehalten", wheel.isVisible())
wat_fake._held = set()                     # losgelassen, aber KEIN up-Ereignis
t0 = time.time()
while time.time() - t0 < 0.5:
    app.processEvents()
    time.sleep(0.01)
check("Rad geht zu ohne Loslassen-Ereignis", not wheel.isVisible(),
      f"(abgespielt: {wctl.played} - nur wenn die Maus gerade bewegt wurde)")
wat_fake._held = {"pad:lb+rb"}
wheel.hold(True)
wheel._opened -= 9                         # Notbremse
t0 = time.time()
while time.time() - t0 < 0.2:
    app.processEvents()
    time.sleep(0.01)
check("Rad Notbremse nach 8 s", not wheel.isVisible())
wheel.hold(False)

# Voice-Chat-Apps statt fest Discord
from soundclip.config import DEFAULTS  # noqa: E402
check("Voice-Chat-Apps Standard = Discord", "discord.exe" in DEFAULTS["voice_chat_apps"])
from soundclip import profiles as prmod  # noqa: E402
check("Programmname normalisieren", prmod.norm_exe(" Fortnite ") == "fortnite.exe" and prmod.norm_exe("a\\b.exe") == ""
      and prmod.norm_exe("app:WhatsApp.Root.exe") == "whatsapp.root.exe")

# ---------------------------------------------------------------- 5) Backup
from soundclip import backup  # noqa: E402
from soundclip.config import DATA_DIR  # noqa: E402

lib.save()
cfgp = DATA_DIR / "config.json"
orig_cfg = json.loads(cfgp.read_text(encoding="utf-8"))
orig_cfg["marker"] = "vorher"
cfgp.write_text(json.dumps(orig_cfg), encoding="utf-8")
cdir = DATA_DIR / "clips" / "c_test"
cdir.mkdir(parents=True, exist_ok=True)
(cdir / "meta.json").write_text(json.dumps({"id": "c_test", "name": "x"}), encoding="utf-8")
bk = os.path.join(tempfile.gettempdir(), "potato_v15_test.potatobackup")
out = backup.create(bk, include_clips=True, version="1.5.0")
info = backup.inspect(out)
check("Backup erstellt + geprueft", info["sound_files"] >= 1 and info["clip_count"] == 1 and info["has_config"],
      str({k: info[k] for k in ("sound_files", "clip_count")}))
out2 = backup.create(bk.replace(".potatobackup", "_noclips.potatobackup"), include_clips=False)
check("Backup ohne Clips", backup.inspect(out2)["clip_count"] == 0)
# Stand aendern, dann zurueckspielen
cfgp.write_text(json.dumps({**orig_cfg, "marker": "nachher"}), encoding="utf-8")
for f in (DATA_DIR / "sounds").glob("*"):
    f.unlink()
backup.restore_prepare(out)
check("Noch nichts ersetzt vor dem Neustart", json.loads(cfgp.read_text(encoding="utf-8"))["marker"] == "nachher")
check("Einspielen", backup.apply_pending())
now = json.loads(cfgp.read_text(encoding="utf-8"))
check("Einstellungen zurueck", now["marker"] == "vorher" and now.get("setup_done") is True)
check("Sounds zurueck", any((DATA_DIR / "sounds").glob("*.wav")))
check("Alter Stand aufgehoben", any(DATA_DIR.glob("_vor_backup_*/config.json")))
check("Nichts mehr ausstehend", not backup.PENDING.exists() and not backup.apply_pending())


def evil(name, entries):
    p = os.path.join(tempfile.gettempdir(), name)
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("potato_backup.json", json.dumps({"app": "Potato Clips", "format": 1}))
        for n, d in entries:
            z.writestr(n, d)
    return p


bad = [("Zip-Slip ../", [("sounds/../../boese.txt", "x")]),
       ("Absoluter Pfad", [("C:/Windows/boese.txt", "x")]),
       ("Fremde Datei", [("autostart.bat", "x")]),
       ("Backslash", [("sounds\\..\\..\\boese.txt", "x")]),
       ("Zu gross / Zip-Bombe", [("sounds/gross.wav", b"\0" * (12 * 1024 * 1024))])]
backup.MAX_TOTAL = 10 * 1024 * 1024          # nur fuer den Test: Grenze klein, damit es schnell geht
for label, entries in bad:
    p = evil("potato_evil.potatobackup", entries)
    try:
        backup.inspect(p)
        check(f"Abgelehnt: {label}", False)
    except backup.BackupError as e:
        check(f"Abgelehnt: {label}", True, str(e)[:60])
    os.remove(p)
backup.MAX_TOTAL = 20 * 1024 ** 3
p = os.path.join(tempfile.gettempdir(), "potato_kein.potatobackup")
open(p, "wb").write(b"kein zip")
try:
    backup.inspect(p)
    check("Abgelehnt: kein Zip", False)
except backup.BackupError:
    check("Abgelehnt: kein Zip", True)
os.remove(p)
check("Nichts ausserhalb geschrieben", not os.path.exists(os.path.join(tempfile.gettempdir(), "boese.txt")))
for f in (out, out2):
    os.remove(f)

# ---------------------------------------------------------------- 6) Clips in Text + Untertitel-Video
from soundclip import triggers as trg  # noqa: E402
from soundclip import transcribe as tx  # noqa: E402
from soundclip import tts  # noqa: E402
from soundclip.mixer import load_audio  # noqa: E402

check("edit_sig: Standard = unbearbeitet",
      tx.edit_sig({}) == tx.edit_sig({"start": 0.0, "end": 30.0, "stems": {"a": {"on": True, "gain": 1.0}},
                                      "effects": []}, 30.0))
check("edit_sig: Schnitt erkannt", tx.edit_sig({}) != tx.edit_sig({"start": 2.0, "end": 30.0}, 30.0))
lines = tx.subtitle_lines([{"w": f"w{i}", "s": i * 0.3, "e": i * 0.3 + 0.25} for i in range(10)]
                          + [{"w": "spaet", "s": 9.0, "e": 9.4}])
check("Untertitel-Zeilen", len(lines) == 3 and len(lines[0]["words"]) == 6 and lines[-1]["words"][0]["w"] == "spaet",
      str([len(x["words"]) for x in lines]))
if not trg.model_ready("de"):
    trg.download_model("de")
voices = tts.voices()
v = next((x["name"] for x in voices if str(x.get("culture", "")).lower().startswith("de")), "")
pth = tts.synth("Hallo Welt, heute gewinnen wir das Spiel", v)
speech = load_audio(pth)
os.remove(pth)
clip = np.concatenate([np.zeros((SR // 2, 2), np.float32), speech, np.zeros((SR // 2, 2), np.float32)])
t0 = time.time()
words = tx.transcribe(clip, "de")
txt = " ".join(w["w"] for w in words)
hits = sum(x in txt for x in ("hallo", "welt", "spiel", "gewinnen"))
check("Sprache erkannt", hits >= 3, f"„{txt}“ ({time.time() - t0:.1f}s)")
check("Wortzeiten plausibel", words and words[0]["s"] >= 0.3 and words[-1]["e"] <= len(clip) / SR + 0.1
      and all(a["s"] <= b["s"] for a, b in zip(words, words[1:])))
check("Stille -> keine Woerter", tx.transcribe(np.zeros((SR, 2), np.float32), "de") == [])
from soundclip import video  # noqa: E402

for fmt, style in (("9:16", "pro"), ("16:9", "potato")):
    mp4 = os.path.join(tempfile.gettempdir(), f"potato_v15_{style}.mp4")
    try:
        video.render_video(clip[:SR * 3], mp4, "Test", fmt, style, words=words)
        check(f"Video mit Untertiteln ({fmt}, {style})", os.path.getsize(mp4) > 20000, f"{os.path.getsize(mp4)} B")
    except Exception as e:
        check(f"Video mit Untertiteln ({fmt}, {style})", False, repr(e))
    finally:
        if os.path.exists(mp4):
            os.remove(mp4)

print("ALLES OK" if ok else "ES GIBT FEHLER", flush=True)
# Qt-Objekte geordnet abbauen, bevor Python beendet wird (sonst kann der Abbau in falscher Reihenfolge abstuerzen)
wheel.close()
wheel.deleteLater()
wctl.deleteLater()
app.processEvents()
inputs.shared().shutdown()
time.sleep(0.2)
sys.stdout.flush()
os._exit(0 if ok else 1)
