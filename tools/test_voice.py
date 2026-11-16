"""End-to-End: (kuenstliche) Stimme -> Stimmeffekt -> CABLE Input -> CABLE Output (= was Discord hoert).
Speist eine Test-Stimme in Echtzeit genau dort ein, wo sonst das Mikrofon ankommt."""
import os, sys, time, subprocess, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401  (eigener Datenordner, nur lautlose Geraete)
import numpy as np
from soundclip.host import HelperHost
from soundclip.config import Config, HELPER
from soundclip.capture import run_helper_list
from soundclip.mixer import Mixer, find_cable_capture

SR = 48000


def capture(args):
    p = subprocess.Popen([str(HELPER)] + args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buf = bytearray()
    def rd():
        while True:
            b = p.stdout.read1(65536)
            if not b:
                break
            buf.extend(b)
    threading.Thread(target=rd, daemon=True).start()
    return p, buf


def test_voice(seconds):
    """Saegezahn-'Stimme' mit wechselnder Tonhoehe und Silben."""
    t = np.arange(int(SR * seconds)) / SR
    f0 = 130 + 25 * np.sin(2 * np.pi * 0.7 * t)
    ph = 2 * np.pi * np.cumsum(f0) / SR
    x = sum(np.sin(k * ph) / k for k in range(1, 30))
    env = np.clip(np.sin(2 * np.pi * 2.2 * t), 0, 1) ** 0.5
    return (0.25 * x * env)[:, None].repeat(2, 1).astype(np.float32)


def spectrum_stats(x):
    X = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    tot = X.sum() + 1e-12
    centroid = float((f * X).sum() / tot)
    hf = float(X[f > 4000].sum() / tot)
    # Grundton: staerkster Peak 60-600 Hz
    band = (f > 60) & (f < 600)
    f0 = float(f[band][np.argmax(X[band])])
    return centroid, hf, f0


cfg = Config()
cfg.data.update(mic_passthrough=True, voice_monitor=False)
_testenv.safe(cfg)
mixer = Mixer(cfg)
mixer.native_voice = lambda: False     # Klang der Effekte ueber den direkten Python-Pfad messen
mixer.reopen()
time.sleep(0.8)
cab = find_cable_capture(run_helper_list()["capture"], mixer.devices["virtual"])
voice = test_voice(3.0)
print(f"{'Effekt':12s} {'Pegel':>7s} {'Klangschwerpunkt':>17s} {'Höhen>4k':>9s} {'Grundton':>9s} {'Aussetzer':>9s} {'CPU':>8s}")
for preset in ["", "potato", "robot", "pitch_up", "pitch_down", "demon", "telephone", "radio", "megaphone",
               "underwater", "reverb", "bitcrush", "earrape"]:
    cfg.data.update(voice_enabled=bool(preset), voice_preset=preset or "potato", voice_amount=0.5)
    mixer.apply_voice()
    mixer.live.clear()
    # genau das aufnehmen, was SoundClip ins Kabel schickt (andere Apps auf dem Kabel stoeren so nicht)
    p1, b = capture(["process", str(HelperHost.get().pid)])
    time.sleep(0.3)
    t0 = time.perf_counter()
    blk = 480
    for i in range(0, len(voice), blk):       # in Echtzeit wie ein Mikrofon einspeisen
        mixer.feed_live(voice[i:i + blk])
        target = t0 + (i + blk) / SR
        d = target - time.perf_counter()
        if d > 0:
            time.sleep(d)
    time.sleep(0.4)
    p1.stdin.close()
    p1.wait(3)
    c = np.frombuffer(bytes(b[: len(b) // 8 * 8]), np.float32).reshape(-1, 2)[:, 0]
    env = np.abs(c)
    nz = np.nonzero(env > 0.01)[0]
    seg = c[nz[0]: nz[-1]] if len(nz) else c
    # Aussetzer: harte Nullstrecken >= 10 ms mitten in einer Silbe
    gaps = 0
    run = 0
    for v in (seg[: SR * 2] == 0):
        run = run + 1 if v else 0
        if run == 480:
            gaps += 1
    cen, hf, f0 = spectrum_stats(seg[: SR * 2] if len(seg) > SR else seg)
    print(f"{preset or 'ohne':12s} {np.sqrt((seg**2).mean()):7.3f} {cen:14.0f} Hz {hf*100:8.1f}% {f0:6.0f} Hz "
          f"{gaps:9d} {mixer.voice.cpu_ms:6.2f}ms")
mixer.close()
