"""Stimme mit echtem Mikro unter voller Last: ohne Effekt und mit Stimmeffekten.
Lautlos und ungefaehrlich: Ziel ist NICHT das VB-Cable (Discord), sondern die unhoerbaren
'Steam Streaming Speakers'. Gemessen werden nur die Zaehler im Helfer."""
import os, re, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401  (eigener Datenordner, nur lautlose Geraete)
from soundclip.config import Config
from soundclip.capture import SourceManager
from soundclip.host import HelperHost
from soundclip.mixer import Mixer

SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 20
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
print("Ziel:", mixer.devices["virtual"], "| Quellen:", mgr.running_count())


def stats():
    host.command("stats")
    time.sleep(0.3)
    return {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", host.last_stats)}


for name, preset in (("ohne Effekt", ""), ("Potato", "potato"), ("Demon", "demon"), ("Robot", "robot")):
    cfg.data.update(voice_enabled=bool(preset), voice_preset=preset or "potato")
    mixer.apply_voice()
    time.sleep(2)
    s0 = stats()
    time.sleep(SECS)
    s1 = stats()
    print(f"{name:12s} ({SECS:.0f} s): Abrisse {s1['voice_underruns'] - s0['voice_underruns']}, "
          f"Korrekturen {s1['voice_drops'] - s0['voice_drops']}, Puffer {s1['fill_ms']} ms, "
          f"Taktausgleich {s1['drift_ppm']} ppm, Modus {s1['pymode']}, "
          f"max. Pause Wiedergabe {s1['render_gap']} ms / Mikro {s1['mic_gap']} ms, "
          f"Effekt-Prozess bereit {s1.get('fx_ready')} (Starts {s1.get('fx_starts')}, uebersprungen {s1.get('fx_skipped')})")
mgr.shutdown()
mixer.close()
print("VOICEFX-TEST ENDE")
