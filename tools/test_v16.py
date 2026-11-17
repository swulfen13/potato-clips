"""1.6 pruefen - lautlos (Test-Ton nur auf Steam Streaming Speakers), eigener Datenordner:
Discord-Webhook (nur gegen einen lokalen Test-Server auf 127.0.0.1), Ohrenschutz-Logik und im Audio-Helfer,
Begrenzer fuer eigene Sounds, Profile, Sprachausgabe ohne PowerShell, Autostart ueber die Registry
(mit eigenem Test-Namen, wird wieder entfernt)."""
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402
import numpy as np  # noqa: E402

ok = True


def check(name, cond, info=""):
    global ok
    ok = ok and bool(cond)
    print(("OK    " if cond else "FEHLER"), name, info, flush=True)


# ---------------------------------------------------------------- 1) Discord-Webhook
from soundclip import webhook  # noqa: E402

check("Webhook-Link erkannt", webhook.valid("https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyzABCDEF_-12"))
check("Fremde Links abgelehnt", not webhook.valid("https://evil.com/api/webhooks/1/abc")
      and not webhook.valid("http://discord.com/api/webhooks/123456/abcdefghijklmnopqrstuvwxyz")
      and not webhook.valid("https://discord.com.evil.com/api/webhooks/123456/abcdefghijklmnopqrstuvwxyz"))
got = {}


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        got["body"] = self.rfile.read(n)
        got["path"] = self.path
        got["ctype"] = self.headers.get("Content-Type", "")
        code = 404 if "gone" in self.path else 200
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"id": "1"}')

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]
import tempfile  # noqa: E402

f = os.path.join(tempfile.gettempdir(), "potato_v16_clip.mp3")
open(f, "wb").write(b"ID3" + os.urandom(3000))
r = webhook.post(f"http://127.0.0.1:{port}/api/webhooks/1/x", f, "🥔 Test @everyone", _check=False)
body = got.get("body", b"")
pj = body.split(b'name="payload_json"')[1].split(b"\r\n\r\n", 1)[1].split(b"\r\n--")[0] if body else b"{}"
payload = json.loads(pj)
check("Webhook schickt Datei + Text", r.get("id") == "1" and open(f, "rb").read() in body
      and payload["content"].startswith("🥔 Test") and "wait=true" in got.get("path", ""))
check("Keine @everyone-Erwaehnung", payload["allowed_mentions"] == {"parse": []})
try:
    webhook.post(f"http://127.0.0.1:{port}/api/webhooks/gone/x", f, "", _check=False)
    check("Geloeschter Webhook verstaendlich", False)
except webhook.WebhookError as e:
    check("Geloeschter Webhook verstaendlich", "existiert nicht" in str(e), str(e))
os.remove(f)
srv.shutdown()

# ---------------------------------------------------------------- 2) Ohrenschutz-Logik
from soundclip.earguard import EarGuard, OutputLimiter, LEVELS, HOLD  # noqa: E402

sent = []
cfg = {"ear_guard": True, "ear_guard_level": "normal"}
duck = {"f": 1.0}
g = EarGuard(cfg, sent.append, lambda exe: duck["f"])
g.own = {"potatoclips.exe"}
quiet = (0.1 * np.ones((480, 2))).astype(np.float32)
loud = (0.8 * np.ones((480, 2))).astype(np.float32)
for _ in range(10):
    g.on_chunk("app:discord.exe", quiet)
check("Normal laut: nichts passiert", sent == [])
g.on_chunk("app:discord.exe", loud)
want = LEVELS["normal"] / 0.8
check("Zu laut: sofort leiser", sent and sent[-1].startswith("guard discord.exe ")
      and abs(float(sent[-1].split()[-1]) - want) < 0.02, str(sent))
n = len(sent)
g.on_chunk("app:discord.exe", loud * g.fac["discord.exe"])     # Mitschnitt kommt schon leiser an
time.sleep(0.1)
g.on_chunk("app:discord.exe", loud * g.fac["discord.exe"])
check("Kein Hochschaukeln (eigene Daempfung rausgerechnet)", len(sent) == n, str(sent[n:]))
g.tick()
check("Haelt waehrend der Haltezeit", len(sent) == n)
g.hold["discord.exe"] = time.time() - 0.01
for _ in range(40):
    g.tick()
check("Danach langsam wieder normal", sent[-1] == "guard discord.exe 1" and "discord.exe" not in g.fac,
      f"{len(sent) - n} Schritte")
sent.clear()
g.on_chunk("app:potatoclips.exe", loud)
g.on_chunk("mic", loud)
check("Eigene App und Mikro werden nie gebremst", sent == [])
duck["f"] = 0.3
g2 = EarGuard(cfg, sent.append, lambda exe: duck["f"])
g2.own = set()
g2.on_chunk("app:spotify.exe", (0.8 * 0.3 * np.ones((480, 2))).astype(np.float32))
check("Ducking wird mitgerechnet", sent and sent[-1].startswith("guard spotify.exe"), str(sent))
sent.clear()
cfg["ear_guard"] = False
g2.tick()
check("Ausschalten gibt alles frei", sent == ["unguard"] and not g2.fac)
cfg["ear_guard"] = True
lim = OutputLimiter()
blk = (0.9 * np.sin(np.linspace(0, 200, 960)))[:, None].repeat(2, 1).astype(np.float32)
outs = [lim.process(blk.copy(), LEVELS["normal"]) for _ in range(5)]
rms = float(np.sqrt(np.mean(outs[-1] ** 2)))
check("Begrenzer fuer eigene Sounds", rms <= LEVELS["normal"] * 1.05 and float(np.abs(outs[-1]).max()) <= 0.91,
      f"rms {rms:.2f}")
small = (0.05 * np.ones((960, 2))).astype(np.float32)
for _ in range(300):
    o = lim.process(small.copy(), LEVELS["normal"])
check("Begrenzer laesst Normales wieder durch", abs(float(o[0, 0]) - 0.05) < 0.002, f"{float(o[0, 0]):.3f}")

# ---------------------------------------------------------------- 3) Ohrenschutz im Audio-Helfer (echt, lautlos)
from soundclip.config import Config  # noqa: E402
from soundclip.host import HelperHost  # noqa: E402
from soundclip.mixer import Mixer  # noqa: E402
from soundclip.capture import SourceManager  # noqa: E402

cfgc = _testenv.safe(Config())
mixer = Mixer(cfgc)
mixer.reopen()
sm = SourceManager(cfgc, mixer)
levels = []
sm.listeners = [lambda k, d: levels.append((time.time(), k, float(np.sqrt(np.mean(d ** 2))) if len(d) else 0.0))]
player = subprocess.Popen([sys.executable, "-c", _testenv.PLAYER_PRELUDE +
                           "import numpy as np\nt=np.arange(48000*20)/48000\n"
                           "sd.play((0.2*np.sin(2*np.pi*300*t))[:,None].repeat(2,1).astype('float32'),48000); sd.wait()"])
sm.start()
time.sleep(5)
host = HelperHost.get()


def lvl(sec=1.5):
    t0 = time.time()
    time.sleep(sec)
    v = [x for (t, k, x) in levels if t >= t0 and k == "app:python.exe" and x > 0]
    return float(np.median(v)) if v else 0.0


base = lvl()
host.command("guard python.exe 0.5")
time.sleep(0.4)
a = lvl()
host.command("duck 0.40 +python.exe")
time.sleep(0.4)
b = lvl()
host.command("guard python.exe 1")
time.sleep(0.4)
c = lvl()
host.command("unduck")
time.sleep(0.4)
d = lvl()
host.command("guard python.exe 0.3")
time.sleep(0.4)
host.command("unguard")
time.sleep(0.4)
e = lvl()
r = [round(x / base, 2) if base else 0 for x in (a, b, c, d, e)]
check("Helfer: Ohrenschutz bremst", base > 0.05 and abs(r[0] - 0.5) < 0.06, f"{r}")
check("Helfer: Ohrenschutz + Ducking zusammen", abs(r[1] - 0.2) < 0.05 and abs(r[2] - 0.4) < 0.06)
check("Helfer: alles wieder auf 100 %", abs(r[3] - 1) < 0.06 and abs(r[4] - 1) < 0.06)
player.kill()
sm.shutdown()
mixer.close()

# ---------------------------------------------------------------- 4) Profile
from soundclip import profiles as pr  # noqa: E402

p1 = pr.clean({"name": "Fortnite", "apps": ["FortniteClient-Win64-Shipping", "x\\y.exe"], "folder": "fn"})
check("Profil saeubern", p1["apps"] == ["fortniteclient-win64-shipping.exe"] and p1["folder"] == "fn" and p1["id"])
p2 = pr.clean({"name": "Py", "apps": ["python.exe"]})
check("Profil-Erkennung (Reihenfolge)", pr.match([p1, p2], {"python.exe", "fortniteclient-win64-shipping.exe"})
      == p1["id"] and pr.match([p1, p2], {"python.exe"}) == p2["id"] and pr.match([p1], {"x.exe"}) == "")
check("Laufende Programme lesbar", "python.exe" in pr.running_exes())
found = []
w = pr.ProfileWatcher({"profiles": [p2], "profile_auto": True}, found.append, interval=0.2)
w.start()
time.sleep(1.0)
w.stop()
check("Spiel wird im Hintergrund erkannt", found and found[0] == p2["id"], str(found))

# ---------------------------------------------------------------- 5) Sprachausgabe ohne PowerShell
from soundclip import tts  # noqa: E402
from soundclip.mixer import load_audio  # noqa: E402

vs = tts.voices()
check("Windows-Stimmen gefunden", len(vs) >= 1 and all(v["name"] for v in vs), ", ".join(v["name"] for v in vs[:3]))
check("Sprache der Stimmen", any(v["culture"].startswith(("de", "en")) for v in vs))
de = next((v["name"] for v in vs if v["culture"].startswith("de")), "")
res = {}


def bg():
    try:
        res["p"] = tts.synth("<volume level='0'>Hallo Potato</volume>", de)
    except Exception as ex:
        res["e"] = ex


th = threading.Thread(target=bg)
th.start()
th.join(30)
pth = res.get("p")
check("Sprachausgabe aus Hintergrund-Thread", pth is not None and pth.exists(), repr(res.get("e", "")))
if pth:
    audio = load_audio(pth)
    check("Text wird nicht als Steuerbefehl gelesen", float(np.abs(audio).max()) > 0.05,
          f"{len(audio) / 48000:.1f}s")
    os.remove(pth)
import psutil  # noqa: E402

kids = [c.name().lower() for c in psutil.Process().children(recursive=True)]
check("Kein PowerShell gestartet", "powershell.exe" not in kids, str(kids))

# ---------------------------------------------------------------- 6) Autostart ueber die Registry (Test-Name)
from soundclip import autostart  # noqa: E402

autostart.RUN_NAME = "Potato Clips TEST (wird geloescht)"
autostart.LINK = autostart.STARTUP_DIR / "Potato Clips TEST.lnk"
try:
    autostart.enable()
    v = autostart._run_value()
    check("Autostart eingetragen", autostart.is_enabled() and v and "--minimized" in v, v)
finally:
    autostart.disable()
check("Autostart entfernt", not autostart.is_enabled() and autostart._run_value() is None)

print("ALLES OK" if ok else "ES GIBT FEHLER", flush=True)
sys.stdout.flush()
os._exit(0 if ok else 1)
