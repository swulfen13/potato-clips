"""Diagnose Effekt-Pfad: wann kommen Stimm-Bloecke in Python an, wie lange dauert die Antwort."""
import os, re, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401  (eigener Datenordner, nur lautlose Geraete)
import numpy as np
from soundclip.config import Config
from soundclip.capture import SourceManager
from soundclip.host import HelperHost
from soundclip import mixer as mx

LOAD = "load" in sys.argv
cfg = Config()
cfg.data.update(mic_passthrough=True, voice_monitor=False, voice_enabled=True, voice_preset="potato",
                capture_mode="all", route_sources={}, clean_mic=True, clean_gate=True)
_testenv.safe(cfg)
arr, proc = [], []
orig = mx.VoiceIn.on_audio
def wrapped(self, payload):
    t = time.perf_counter()
    orig(self, payload)
    arr.append(t); proc.append(time.perf_counter() - t)
mx.VoiceIn.on_audio = wrapped
mixer = mx.Mixer(cfg)
mixer.reopen()
mgr = None
if LOAD:
    mgr = SourceManager(cfg, mixer); mgr.start()
time.sleep(3)
arr.clear(); proc.clear()
time.sleep(10)
host = HelperHost.get()
host.command("stats"); time.sleep(0.3)
a = np.diff(np.array(arr)) * 1000
print("Last" if LOAD else "ohne Last", "| Bloecke:", len(arr), "(erwartet ~1000)")
print("Abstaende ms: median %.1f  p99 %.1f  max %.1f  >50ms: %d  >100ms: %d" % (
    np.median(a), np.percentile(a, 99), a.max(), (a > 50).sum(), (a > 100).sum()))
print("Verarbeitung ms: median %.2f max %.2f" % (np.median(proc) * 1000, max(proc) * 1000))
print(host.last_stats)
if mgr: mgr.shutdown()
mixer.close()
