"""Update-Logik pruefen (ohne etwas zu installieren): GitHub-Abfrage, Download mit Pruefsumme, falsche Pruefsumme."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401
from soundclip import updater

ok = True


def check(name, cond, info=""):
    global ok
    ok = ok and bool(cond)
    print(("OK    " if cond else "FEHLER"), name, info, flush=True)


updater.__version__ = "1.2.0"           # so tun, als waere eine alte Version installiert
info = updater.check()
check("Neue Version gefunden", info and updater._ver(info["version"]) >= (1, 3, 0), str(info and info["version"]))
check("Pruefsumme von GitHub", info and len(info.get("sha256", "")) == 64, info and info.get("sha256", "")[:16])
t0 = time.time()
p = updater.download(info["url"], sha256=info["sha256"])
check("Download mit passender Pruefsumme", p.exists() and p.stat().st_size > 50_000_000,
      f"{p.stat().st_size // 1_000_000} MB in {time.time() - t0:.1f} s")
os.remove(p)
try:
    updater.download(info["url"], sha256="0" * 64)
    check("Falsche Pruefsumme abgelehnt", False)
except IOError as e:
    check("Falsche Pruefsumme abgelehnt", not p.exists() and not p.with_suffix(p.suffix + ".part").exists(), str(e))
try:
    updater.download("https://example.com/evil.exe")
    check("Fremde Adresse abgelehnt", False)
except ValueError:
    check("Fremde Adresse abgelehnt", True)
updater.__version__ = "9.9.9"
check("Keine neuere Version", updater.check() is None)
print("UPDATE-TEST BESTANDEN" if ok else "UPDATE-TEST FEHLGESCHLAGEN", flush=True)
sys.exit(0 if ok else 1)
