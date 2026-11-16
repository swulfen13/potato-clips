"""Gemeinsame, sichere Test-Umgebung (zuerst importieren!):

- eigener, temporaerer Datenordner -> echte Sounds, Clips und Einstellungen bleiben unberuehrt
- Kopfhoerer UND virtuelles Mikro zeigen auf die unhoerbaren 'Steam Streaming Speakers'
  -> nichts ist auf deinen Kopfhoerern zu hoeren und nichts landet bei Freunden in Discord
"""
import atexit
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="potato_test_")
os.environ["POTATO_CLIPS_DATA"] = TMP
atexit.register(shutil.rmtree, TMP, True)

SILENT = "Steam Streaming Speakers"

from soundclip.capture import run_helper_list  # noqa: E402

SILENT_DEVICE = next((d["name"] for d in run_helper_list()["render"] if SILENT in d["name"]), "")
if not SILENT_DEVICE:
    sys.exit("Abbruch: kein lautloses Testgeraet (Steam Streaming Speakers) gefunden - Tests wuerden hoerbar sein.")

with open(os.path.join(TMP, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"monitor_device": SILENT_DEVICE, "virtual_device": SILENT_DEVICE}, f)


def safe(cfg):
    """Fuer Tests, die cfg.data.update(...) nutzen: Geraete erneut erzwingen."""
    cfg.data.update(monitor_device=SILENT_DEVICE, virtual_device=SILENT_DEVICE)
    return cfg


# Test-Player (Unterprozess): spielt lautlos auf dem Steam-Geraet ueber MME
PLAYER_PRELUDE = r'''
import sounddevice as sd
_dev = None
for _i, _d in enumerate(sd.query_devices()):
    if _d["max_output_channels"] > 0 and "Steam Streaming S" in _d["name"] and sd.query_hostapis(_d["hostapi"])["name"] == "MME":
        _dev = _i; break
if _dev is None:
    raise SystemExit("kein lautloses Testgeraet")
sd.default.device = (None, _dev)
'''
