"""End-to-End-Test der Engine ohne UI:
spielt in einem eigenen Prozess einen Ton, laesst den SourceManager alles mitschneiden,
macht einen Clip und eine Aufnahme und prueft, ob der Ton in der richtigen Spur landet.
Effekte werden ebenfalls einmal durchgerechnet."""
import os, sys, subprocess, time, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401  (eigener Datenordner, nur lautlose Geraete)
import numpy as np
import soundfile as sf
from soundclip.config import Config, SR
from soundclip.capture import SourceManager
from soundclip.effects import EFFECTS, apply_chain
from soundclip.library import ClipLibrary, render

cfg = Config()
_testenv.safe(cfg)
cfg.data["buffer_seconds"] = 10
cfg.data["capture_mode"] = "all"
mgr = SourceManager(cfg)
mgr.start()

player = subprocess.Popen([sys.executable, "-c",
    _testenv.PLAYER_PRELUDE + "import numpy as np\n"
    "t=np.arange(int(48000*5))/48000\n"
    "x=(0.04*np.sin(2*np.pi*660*t)).astype('float32')\n"
    "sd.play(x,48000); sd.wait()"])
exe_name = None
for i in range(40):
    time.sleep(0.25)
    for k, s in list(mgr.sources.items()):
        if str(s.arg) == str(player.pid) and s.status == "läuft":
            exe_name = k
    if exe_name:
        break
print("Quellen:", {k: (s.label, s.status) for k, s in mgr.sources.items()})
assert exe_name, "Test-Player wurde nicht als Quelle erkannt"
mgr.start_recording()
time.sleep(2.5)
rec = mgr.stop_recording()
clip = mgr.make_clip(5)
player.wait()
print("Clip-Spuren:", [(s["label"], s["peak"]) for s in clip["stems"]])
print("Aufnahme-Spuren:", [(s["label"], s["peak"]) for s in rec["stems"]] if rec else None)
st = next(s for s in clip["stems"] if s["key"] == exe_name)
assert 0.03 < st["peak"] < 0.06, st
lib = ClipLibrary()
meta = next(m for m in lib.list() if m["id"] == clip["id"])
stems = lib.stems(meta)
edit = {"stems": {k: {"on": k == exe_name, "gain": 1.0} for k in stems}, "start": 1.0, "end": 3.0,
        "effects": [{"type": k, "amount": 0.5} for k in EFFECTS if k != "earrape"]}
t = time.time()
out = render(meta, stems, edit)
print(f"Render mit allen Effekten: {len(out)/SR:.2f}s Audio in {time.time()-t:.2f}s, peak={np.abs(out).max():.3f}")
for k in EFFECTS:
    y = apply_chain(stems[exe_name][:SR], [{"type": k, "amount": 0.8}])
    assert np.isfinite(y).all() and len(y) > 0, k
print("Alle Effekte OK")
# Testdaten wieder entfernen
for m in (clip, rec):
    if m:
        shutil.rmtree(lib.dir({"id": m["id"]}), ignore_errors=True)
mgr.shutdown()
print("ENGINE-TEST BESTANDEN")
