"""Diagnose (lautlos): misst die Prozess-Loopback-Lautstaerke des Test-Players vor/nach dem Leiserstellen seiner
Windows-Lautstaerke - wirkt die App-Lautstaerke VOR oder NACH dem Mitschnitt?"""
import os, sys, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401
import numpy as np
from soundclip.config import Config
from soundclip.host import HelperHost
from soundclip.mixer import Mixer
from soundclip.capture import SourceManager

cfg = _testenv.safe(Config())
mixer = Mixer(cfg)
mixer.reopen()
sm = SourceManager(cfg, mixer)
levels = []
sm.listeners = [lambda k, d: levels.append((time.time(), k, float(np.sqrt(np.mean(d ** 2))) if len(d) else 0.0))]
player = subprocess.Popen([sys.executable, "-c", _testenv.PLAYER_PRELUDE +
                           "import numpy as np\nt=np.arange(48000*14)/48000\n"
                           "sd.play((0.2*np.sin(2*np.pi*300*t))[:,None].repeat(2,1).astype('float32'),48000); sd.wait()"])
sm.start()
time.sleep(5)
host = HelperHost.get()


def lvl(t0, t1):
    v = [x for (t, k, x) in levels if t0 <= t <= t1 and k == "app:python.exe" and x > 0]
    return np.median(v) if v else None


t = time.time()
time.sleep(2)
a = lvl(t, time.time())
host.command("duck 0.30 +python.exe")
time.sleep(0.5)
t = time.time()
time.sleep(2)
b = lvl(t, time.time())
host.command("unduck")
t0 = time.time()
time.sleep(1.0)
print("Pegel normal:", a, "| bei 30 % Lautstaerke:", b, "| Verhaeltnis:", (b / a) if a and b else None)
print("Bloecke/s:", len([1 for (tt, k, x) in levels if k == "app:python.exe" and t0 - 1 <= tt <= t0]))
player.kill()
sm.shutdown()
mixer.close()
