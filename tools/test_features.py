"""Neue Funktionen pruefen – lautlos und mit eigenem Datenordner:
Sound-Packs, Clip-Teilen (MP3), Vorlesen (nur Datei), eigene Effekte (auch im Effekt-Prozess),
Ducking (nur am Test-Player), Update-Pruefung."""
import os, sys, re, time, subprocess, zipfile, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401  (eigener Datenordner, nur lautlose Geraete)
import numpy as np
import soundfile as sf

ok = True


def check(name, cond, info=""):
    global ok
    ok = ok and bool(cond)
    print(("OK    " if cond else "FEHLER"), name, info)


SR = 48000
t = np.arange(SR) / SR
tone = (0.2 * np.sin(2 * np.pi * 440 * t))[:, None].repeat(2, 1).astype(np.float32)

# 1) Sound-Packs
from soundclip.library import SoundLibrary
from soundclip.packs import export_pack, import_pack
lib = SoundLibrary()
a = lib.add_array("Test A", tone)
b = lib.add_array("Test B", tone * 0.5)
lib.update(a["id"], hotkey="ctrl+alt+1", volume=0.7)
pack = os.path.join(tempfile.gettempdir(), "potato_test.potatopack")
n = export_pack(lib, [a["id"], b["id"]], pack)
check("Pack exportiert", n == 2 and os.path.getsize(pack) > 1000, f"{n} Sounds, {os.path.getsize(pack)} Bytes")
before = len(lib.sounds)
m = import_pack(lib, pack)
new = lib.sounds[before:]
check("Pack importiert", m == 2 and [s["name"] for s in new] == ["Test A", "Test B"])
check("Hotkeys nicht mitgeschickt", all(not s.get("hotkey") for s in new) and abs(new[0]["volume"] - 0.7) < 1e-6)
evil = os.path.join(tempfile.gettempdir(), "potato_evil.potatopack")
with zipfile.ZipFile(evil, "w") as z:
    z.writestr("pack.json", '{"sounds":[{"name":"x","file":"sounds/../../evil.wav"},{"name":"y","file":"../y.wav"}]}')
    z.writestr("sounds/../../evil.wav", b"RIFF")
check("Boese Pfade ignoriert", import_pack(lib, evil) == 0)
os.remove(pack)
os.remove(evil)

# 2) Clip teilen
from soundclip.share import encode
p = encode(np.concatenate([tone] * 5), "Test Clip")
d, sr = sf.read(str(p))
check("Clip als " + p.suffix, p.suffix in (".mp3", ".ogg") and abs(len(d) / sr - 5.0) < 0.2,
      f"{p.stat().st_size // 1024} KB, {len(d) / sr:.2f} s")

# 3) Vorlesen (nur in eine Datei, nichts wird abgespielt)
from soundclip import tts
try:
    vs = tts.voices()
    w = tts.synth("Hallo, das ist ein Test.", vs[0]["name"] if vs else "")
    d, sr = sf.read(str(w))
    check("Vorlesen", len(d) / sr > 0.5, f"{len(vs)} Stimmen, {len(d) / sr:.1f} s")
    os.remove(w)
except Exception as e:
    check("Vorlesen", False, str(e))

# 4) Eigener Effekt
from soundclip.effects import VOICE_PRESETS, VoiceChanger, register_custom, voice_name
register_custom("custom_test", "Testmix", "★", [["robot", 0.6], ["reverb", 0.4], ["gibtsnicht", 1]])
vc = VoiceChanger()
vc.set("custom_test", 0.5)
y = vc.process(tone[:4800])
check("Eigener Effekt (lokal)", vc.active() and np.isfinite(y).all() and voice_name("custom_test") == "Testmix"
      and len(VOICE_PRESETS["custom_test"][1]) == 2)

from soundclip.config import Config
from soundclip.host import HelperHost
from soundclip.mixer import Mixer
from soundclip.capture import SourceManager
cfg = Config()
cfg.data.update(mic_passthrough=True, voice_monitor=False, voice_enabled=True, voice_preset="custom_test",
                custom_voices={"custom_test": {"name": "Testmix", "emoji": "★",
                                               "chain": [["robot", 0.6], ["reverb", 0.4]]}})
_testenv.safe(cfg)
mixer = Mixer(cfg)
mixer.reopen()
mixer.apply_voice()
time.sleep(4)
host = HelperHost.get()


def stats():
    host.command("stats")
    time.sleep(0.3)
    return {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", host.last_stats)}


s0 = stats()
time.sleep(8)
s1 = stats()
check("Eigener Effekt im Effekt-Prozess", s1.get("pymode") == 2 and s1.get("fx_ready") == 1
      and s1["voice_underruns"] - s0["voice_underruns"] == 0,
      f"Modus {s1.get('pymode')}, bereit {s1.get('fx_ready')}, Abrisse {s1['voice_underruns'] - s0['voice_underruns']}")

# 5) Ducking nur am lautlosen Test-Player
player = subprocess.Popen([sys.executable, "-c", _testenv.PLAYER_PRELUDE +
                           "import numpy as np\nt=np.arange(48000*8)/48000\n"
                           "sd.play((0.05*np.sin(2*np.pi*300*t)).astype('float32'),48000); sd.wait()"])
time.sleep(2.5)
duckfile = os.path.join(tempfile.gettempdir(), "potato_clips_duck.txt")
host.command("duck 0.30 +python.exe")
time.sleep(0.8)
lines = open(duckfile, encoding="utf-8-sig").read().strip().splitlines() if os.path.exists(duckfile) else []
check("Ducking leiser", len(lines) >= 1, f"{len(lines)} Session(s)")
host.command("unduck")
time.sleep(0.8)
check("Ducking zurueckgestellt", not os.path.exists(duckfile))


def pyvol():
    from soundclip.config import HELPER
    out = subprocess.run([str(HELPER), "sessions", "python.exe"], capture_output=True, text=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    vals = [float(line.split("\t")[1]) for line in out.splitlines() if "\t" in line]
    return min(vals) if vals else None


# App wird beendet, waehrend sie leiser ist -> beim naechsten Start muss sie wieder normal laut sein
host.command("duck 0.30 +python.exe")
time.sleep(0.8)
v_duck = pyvol()
player.kill()
player.wait()
time.sleep(0.5)
host.command("unduck")
time.sleep(0.8)
pending = os.path.exists(duckfile)
player = subprocess.Popen([sys.executable, "-c", _testenv.PLAYER_PRELUDE +
                           "import numpy as np\nsd.play(np.zeros((48000*8,2),'float32'),48000); sd.wait()"])
time.sleep(6)
v_after = pyvol()
check("Beendete App wird spaeter zurueckgesetzt", v_duck is not None and abs(v_duck - 0.3) < 0.02 and pending
      and v_after is not None and v_after > 0.99 and not os.path.exists(duckfile),
      f"leiser {v_duck}, vorgemerkt {pending}, danach {v_after}")
player.kill()
mixer.close()
host.shutdown()

# 6) Updates
from soundclip import updater
check("Versionsvergleich", updater._ver("v1.10.0") > updater._ver("1.9.3") > updater._ver("1.9"))
try:
    info = updater.check()
    check("Update-Pruefung", True, f"neuer: {info['version']}" if info else "aktuell")
except Exception as e:
    check("Update-Pruefung", False, str(e))

print("FEATURE-TEST", "BESTANDEN" if ok else "FEHLGESCHLAGEN")
