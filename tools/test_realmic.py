"""Echtes Mikro, 30 s, volle Last: wie oft reisst der Stimm-Puffer ab? (nativ vs. alter Python-Pfad)
Gibt nichts auf dem Kopfhoerer aus."""
import os, sys, time, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401  (eigener Datenordner, nur lautlose Geraete)
from soundclip.config import Config
from soundclip.capture import SourceManager
from soundclip.host import HelperHost
from soundclip.mixer import Mixer

SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 30
cfg = Config()
cfg.data.update(mic_passthrough=True, voice_monitor=False, voice_enabled=False, capture_mode="all",
                route_sources={}, clean_mic=True, clean_gate=True)
_testenv.safe(cfg)
mixer = Mixer(cfg)
mixer.reopen()
mgr = SourceManager(cfg, mixer)
mgr.start()
time.sleep(4)
host = HelperHost.get()


def stats():
    host.command("stats")
    time.sleep(0.3)
    m = dict(re.findall(r"(\w+)=(-?\d+)", host.last_stats))
    return {k: int(v) for k, v in m.items()}


# 1) nativ
s0 = stats()
time.sleep(SECS)
s1 = stats()
print(f"NATIV  ({SECS:.0f} s, echtes Mikro, sauber+gate): Abrisse {s1['voice_underruns'] - s0['voice_underruns']}, "
      f"Korrekturen {s1['voice_drops'] - s0['voice_drops']}, RNNoise im Helfer: {s1['rnnoise']}, "
      f"max. Pause Wiedergabe {s1.get('render_gap', -1)} ms, Mikro {s1.get('mic_gap', -1)} ms")

# 2) alter Python-Pfad (gleiche Stimme ueber Python, wie mit Stimmeffekt)
mixer.native_voice = lambda: False
mixer.apply_voice_path()
mgr.poke()
time.sleep(2)
u0, d0 = mixer.live.underruns, mixer.live.drops
time.sleep(SECS)
print(f"PYTHON ({SECS:.0f} s, echtes Mikro, sauber+gate): Abrisse {mixer.live.underruns - u0}, "
      f"Korrekturen {mixer.live.drops - d0}")
mgr.shutdown()
mixer.close()
print("REALMIC-TEST ENDE")
