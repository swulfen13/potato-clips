"""Neue Funktionen 1.2 pruefen – lautlos, eigener Datenordner, Server nur auf 127.0.0.1:
Lautstaerke angleichen, Zuschneiden, Ordner/Favoriten, Packs, Auto-Clip, Sprach-Trigger (mit Windows-
Sprachausgabe als 'Sprecher', nur als Datei), Fernbedienungs-Server, Video-Export."""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401
import numpy as np
import soundfile as sf

ok = True


def check(name, cond, info=""):
    global ok
    ok = ok and bool(cond)
    print(("OK    " if cond else "FEHLER"), name, info, flush=True)


SR = 48000
t = np.arange(SR) / SR
tone = (0.5 * np.sin(2 * np.pi * 440 * t))[:, None].repeat(2, 1).astype(np.float32)

# ---------------------------------------------------------------- 1) Lautheit & Stille
from soundclip.loudness import apply_trim, norm_gain, silence_bounds
quiet, loud = tone * 0.1, tone * 0.9
gq, gl = norm_gain(quiet), norm_gain(loud)


def rms_db(a):
    return 20 * np.log10(np.sqrt(np.mean(a ** 2)))


check("Leiser Sound wird lauter", gq > 2, f"x{gq:.2f}")
check("Lauter Sound wird leiser", gl < 1, f"x{gl:.2f}")
check("Danach gleich laut", abs(rms_db(quiet * gq) - rms_db(loud * gl)) < 1.0,
      f"{rms_db(quiet * gq):.1f} / {rms_db(loud * gl):.1f} dB")
spiky = np.zeros((SR, 2), np.float32)
spiky[1000] = 0.9
check("Nie ueber 0 dBFS", np.abs(spiky * norm_gain(spiky)).max() <= 0.99)
padded = np.concatenate([np.zeros((SR, 2), np.float32), tone, np.zeros((SR // 2, 2), np.float32)])
b = silence_bounds(padded)
check("Stille erkannt", b and abs(b[0] - 0.97) < 0.05 and abs(b[1] - 2.03) < 0.05, str(b))
check("Zuschnitt angewendet", abs(len(apply_trim(padded, b)) / SR - 1.06) < 0.03)
check("Kein Zuschnitt noetig", silence_bounds(tone) is None)

# ---------------------------------------------------------------- 2) Bibliothek: Ordner, Favoriten, Packs
from soundclip.library import SoundLibrary
from soundclip.packs import export_pack, import_pack
lib = SoundLibrary()
src = os.path.join(tempfile.gettempdir(), "potato_pad_test.wav")
sf.write(src, padded, SR)
e = lib.add_file(src, auto_trim=True, folder="Memes")
os.remove(src)
check("Import mit Zuschnitt", e and e.get("trim") and abs(len(lib.audio(e)) / SR - 1.06) < 0.03, str(e.get("trim")))
check("Import in Ordner + Lautheit", e["folder"] == "Memes" and e.get("norm"), f"norm {e.get('norm')}")
check("Rohdatei unveraendert", abs(len(lib.audio_raw(e)) / SR - 2.5) < 0.01)
lib.set_trim(e["id"], None)
check("Zuschnitt zuruecksetzen", "trim" not in e and abs(len(lib.audio(e)) / SR - 2.5) < 0.01)
lib.set_trim(e["id"], [1.0, 2.0])
f2 = lib.add_array("Zweiter", tone)
lib.update(f2["id"], fav=True, folder="Musik")
check("Ordnerliste", lib.folders(["Leer"]) == ["Leer", "Memes", "Musik"], str(lib.folders(["Leer"])))
lib.rename_folder("Memes", "Lustig")
check("Ordner umbenennen", e["folder"] == "Lustig")
check("Lautstaerke-Faktor", abs(lib.gain_for({"volume": 0.5, "norm": 2.0}, None, True) - 1.0) < 1e-6 and
      lib.gain_for({"volume": 0.5, "norm": 2.0}, None, False) == 0.5)
pk = os.path.join(tempfile.gettempdir(), "potato_test2.potatopack")
export_pack(lib, [e["id"]], pk)
n0 = len(lib.sounds)
import_pack(lib, pk)
imp = lib.sounds[n0]
check("Pack behaelt Ordner + Zuschnitt", imp["folder"] == "Lustig" and imp.get("trim") == [1.0, 2.0])
os.remove(pk)

# ---------------------------------------------------------------- 3) Auto-Clip
from soundclip.autoclip import AutoClip
cfg = {"autoclip_enabled": True, "autoclip_source": "discord", "autoclip_db": -16.0, "autoclip_after": 0.3,
       "autoclip_cooldown": 2}
fired = []
ac = AutoClip(cfg, lambda: fired.append(time.time()))
chunk = 480
quiet_c = (0.01 * np.random.randn(chunk, 2)).astype(np.float32)
loud_c = (0.6 * np.random.randn(chunk, 2)).astype(np.float32).clip(-1, 1)
for _ in range(200):
    ac.on_chunk("app:discord.exe", quiet_c)
for _ in range(100):
    ac.on_chunk("app:spotify.exe", loud_c)            # andere App zaehlt bei "discord" nicht
time.sleep(0.5)
check("Leise/fremde App loest nicht aus", not fired)
for _ in range(60):
    ac.on_chunk("app:discord.exe", loud_c)
time.sleep(0.6)
check("Lauter Moment loest aus", len(fired) == 1)
for _ in range(60):
    ac.on_chunk("app:discord.exe", loud_c)
time.sleep(0.6)
check("Pause zwischen Auto-Clips", len(fired) == 1)
very_quiet = tone * 0.003
check("Sehr leiser Sound: hoechstens x6", norm_gain(very_quiet) == 6.0)
cfg["autoclip_source"] = "mic"
check("Quelle Mikro", ac.watches("mic") and not ac.watches("app:discord.exe"))

# ---------------------------------------------------------------- 4) Sprach-Trigger
from soundclip import triggers as trg
from soundclip import tts
from soundclip.mixer import load_audio
t0 = time.time()
trg.download_model("de")
check("Sprachpaket geladen", trg.model_ready("de"), f"{time.time() - t0:.1f} s")
lib2 = SoundLibrary()
lib2.sounds = []
sa = lib2.add_array("Kartoffel-Sound", tone)
sb = lib2.add_array("Boom-Sound", tone)
sc = lib2.add_array("Nie", tone)
lib2.update(sa["id"], trigger="Kartoffel")
lib2.update(sb["id"], trigger="boom, krass")
lib2.update(sc["id"], trigger="Banane")
hits = []
vt = trg.VoiceTriggers({"triggers_enabled": True, "trigger_lang": "de"}, lib2, hits.append)
vt.sync()
check("Erkennung laeuft", vt.running)
voice = next((v["name"] for v in tts.voices() if str(v.get("culture", "")).lower().startswith("de")), "")
w = tts.synth("Ach du meine Güte, Kartoffel! Und dann noch mal Boom, was für ein Tor.", voice)
speech = load_audio(w)
os.remove(w)
speech = np.concatenate([speech, np.zeros((SR, 2), np.float32)])
for i in range(0, len(speech), 480):                     # wie aus dem Mikro: 10-ms-Bloecke
    vt.on_chunk("mic", speech[i:i + 480])
    vt.on_chunk("app:discord.exe", speech[i:i + 480])    # andere Quellen werden ignoriert
    time.sleep(0.002)
deadline = time.time() + 10
while time.time() < deadline and len(hits) < 2:
    time.sleep(0.1)
time.sleep(1.0)
vt.stop()
check("Trigger erkannt", hits.count(sa["id"]) == 1 and hits.count(sb["id"]) == 1, f"gehört: „{vt.heard}“")
check("Falscher Trigger blieb still", sc["id"] not in hits, str(hits))
check("Erkennung stoppt", not vt.running)

# ---------------------------------------------------------------- 5) Fernbedienungs-Server (nur 127.0.0.1)
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from soundclip.remote import RemoteServer


class FakeCtl(QObject):
    remoteCommand = Signal(str)

    def __init__(self):
        super().__init__()
        self.cfg = {"remote_enabled": False, "api_enabled": True, "remote_port": 18765, "remote_token": "",
                    "ui_theme": "potato"}
        self.got = []
        self.remoteCommand.connect(self.got.append)

    def remote_state(self):
        return {"sounds": [{"id": "abc", "name": "Test"}], "folders": [], "voice": {}, "presets": [],
                "recording": False}

    def remote_now(self):
        return {"playing": [], "recording": True, "voice": ""}

    def remote_command_ok(self, cmd):
        return cmd in ("stop", "play/abc", "random:Memes")


fc = FakeCtl()
srv = RemoteServer(fc)
srv.sync()
check("Server nur lokal", srv.running and srv.host == "127.0.0.1", f"{srv.host}:{srv.port}")


def get(url, method="GET"):
    req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, ""


base = f"http://127.0.0.1:{srv.port}"
check("Ohne Schluessel verboten", get(base + "/api/state")[0] == 403 and get(base + "/api/stop?t=falsch")[0] == 403)
code, body = get(srv.local_url("/api/state"))
check("Status-Abfrage", code == 200 and json.loads(body)["sounds"][0]["name"] == "Test")
check("Handy-Seite", "Potato Clips" in get(srv.local_url("/"))[1])
check("OBS-Overlay", "api/now" in get(srv.local_url("/overlay"))[1])
check("Befehl per POST", get(srv.local_url("/api/play/abc"), "POST")[0] == 200)
check("Befehl per GET (Stream Deck)", get(srv.local_url("/api/stop"))[0] == 200)
check("Zufall aus Ordner", get(srv.local_url("/api/random?folder=Memes"))[0] == 200)
check("Unbekannter Befehl", get(srv.local_url("/api/format_c"))[0] == 404)
for _ in range(20):
    app.processEvents()
    time.sleep(0.02)
check("Befehle angekommen", fc.got == ["play/abc", "stop", "random:Memes"], str(fc.got))
srv.stop()
check("Server gestoppt", not srv.running)

# ---------------------------------------------------------------- 6) Video
from soundclip import video
noise = (0.2 * np.random.randn(SR * 3, 2)).astype(np.float32)
clip = np.concatenate([tone, noise])[: SR * 3]
for fmt, style in (("9:16", "potato"), ("16:9", "pro")):
    out = os.path.join(tempfile.gettempdir(), f"potato_test_{fmt.replace(':', 'x')}.mp4")
    t0 = time.time()
    video.render_video(clip, out, "Test-Clip mit langem Titel, der umbrechen muss", fmt, style)
    import subprocess
    info = subprocess.run([video.ffmpeg_exe(), "-i", out], capture_output=True, text=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stderr
    W, H = video.FORMATS[fmt]
    has = f"{W}x{H}" in info and "Audio: aac" in info and "Duration: 00:00:03" in info
    check(f"Video {fmt} {style}", os.path.getsize(out) > 20000 and has,
          f"{os.path.getsize(out) // 1024} KB in {time.time() - t0:.1f} s")
    if fmt == "9:16":
        frame = os.path.join(tempfile.gettempdir(), "potato_test_frame.png")
        subprocess.run([video.ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", "1.5", "-i", out, "-frames:v", "1", frame],
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        shots = os.path.join(os.path.dirname(__file__), "shots")
        os.makedirs(shots, exist_ok=True)
        if os.path.exists(frame):
            os.replace(frame, os.path.join(shots, "video_frame.png"))
    os.remove(out)
cancel = threading.Event()
cancel.set()
try:
    video.render_video(clip, os.path.join(tempfile.gettempdir(), "potato_cancel.mp4"), "x", cancel=cancel)
    check("Abbrechen", False)
except RuntimeError:
    check("Abbrechen", not os.path.exists(os.path.join(tempfile.gettempdir(), "potato_cancel.mp4")))

print("NEU-TEST BESTANDEN" if ok else "NEU-TEST FEHLGESCHLAGEN", flush=True)
sys.exit(0 if ok else 1)
