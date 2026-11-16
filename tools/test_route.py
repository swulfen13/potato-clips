"""Prueft 'App -> Discord': ein Test-Player spielt einen Ton, Potato Clips schickt NUR diese App ins virtuelle Mikro."""
import os, sys, time, subprocess, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401  (eigener Datenordner, nur lautlose Geraete)
import numpy as np
from soundclip.config import Config, HELPER
from soundclip.host import HelperHost
from soundclip.capture import SourceManager
from soundclip.mixer import Mixer

cfg = Config()
cfg.data.update(mic_passthrough=False, voice_monitor=False, capture_mode="selected", selected_sources=[],
                route_sources={})
_testenv.safe(cfg)
mixer = Mixer(cfg)
mixer.reopen()
mgr = SourceManager(cfg, mixer)
mgr.start()
player = subprocess.Popen([sys.executable, "-c",
    _testenv.PLAYER_PRELUDE + "import numpy as np\n"
    "t=np.arange(int(48000*7))/48000\n"
    "sd.play((0.1*np.sin(2*np.pi*500*t)).astype('float32'),48000); sd.wait()"])
key = None
for _ in range(40):
    time.sleep(0.25)
    for k, v in mgr.available.items():
        if v.get("arg") == player.pid:
            key = k
    if key:
        break
print("Test-Player als Quelle:", key)
cfg.data["route_sources"] = {key: 1.0}
mgr.poke()
time.sleep(2)
buf = bytearray()
p = subprocess.Popen([str(HELPER), "process", str(HelperHost.get().pid)], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
threading.Thread(target=lambda: [buf.extend(b) for b in iter(lambda: p.stdout.read1(65536), b"")], daemon=True).start()
time.sleep(2.5)
p.stdin.close(); p.wait(3)
a = np.frombuffer(bytes(buf[: len(buf) // 8 * 8]), np.float32).reshape(-1, 2)[:, 0]
X = np.abs(np.fft.rfft(a)); f = np.fft.rfftfreq(len(a), 1 / 48000)
print(f"an Discord geschickt: rms {np.sqrt((a**2).mean()):.4f} (erwartet ~0.07), stärkste Frequenz {f[np.argmax(X)]:.0f} Hz (erwartet 500)")
fifo = mixer.routes.get(key)
print("Aussetzer im Puffer:", fifo.underruns if fifo else None, "| Korrekturen:", fifo.drops if fifo else None)
cfg.data["route_sources"] = {}
mgr.shutdown(); mixer.close(); player.kill()
print("ROUTE-TEST ENDE")
