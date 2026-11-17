"""Sprachbefehle ("Potato, clip Spotify"), Ansage und Auto-Clip-App-Auswahl pruefen.
Lautlos: die Saetze spricht die Windows-Sprachausgabe in eine Datei, nichts wird abgespielt."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import _testenv  # noqa: E402,F401
import numpy as np

ok = True


def check(name, cond, info=""):
    global ok
    ok = ok and bool(cond)
    print(("OK    " if cond else "FEHLER"), name, info, flush=True)


from soundclip import triggers as trg
from soundclip import tts
from soundclip.mixer import load_audio

for lang in ("de", "en"):
    if not trg.model_ready(lang):
        trg.download_model(lang)
check("Sprachpakete da", trg.model_ready("de") and trg.model_ready("en"))
vde, ven = trg.vocab("de"), trg.vocab("en")
check("Wortschatz gelesen", len(vde) > 100000 and len(ven) > 100000, f"{len(vde)} / {len(ven)} Woerter")
check("Potato bekannt", "potato" in vde and "potato" in ven and "kartoffel" in vde)
check("Unbekanntes Wort erkannt", not trg.known("de", "bruh") and trg.known("de", "boom"))

apps = {"mic": "Mikrofon", "app:spotify.exe": "Spotify", "app:discord.exe": "Discord", "app:chrome.exe": "Chrome",
        "app:valorant-win64-shipping.exe": "Valorant", "app:steam.exe": "Steam"}
tde = trg.build_commands("de", apps)
check("Befehl clip spotify", tde.get(("clip", "spotify"), (None, None))[1] == ["app:spotify.exe"])
check("Discord ueber Aussprache", tde.get(("clip", "disco", "kord"), (None, None))[1] == ["app:discord.exe"])
check("Spiel = Spiele-Apps", tde.get(("clip", "spiel"), (None, None))[1] == ["app:valorant-win64-shipping.exe"])
check("Aufnahme App", tde.get(("aufnahme", "spotify"), ("",))[0] == "rec_start")
ten = trg.build_commands("en", apps)
check("EN record discord", ten.get(("record", "discord"), (None, None))[1] == ["app:discord.exe"])
check("Parser", trg.parse_command(["[unk]", "potato", "clip", "spotify"], [1, 1, 1, 1], tde, ["potato"])[:2]
      == ("clip", ["app:spotify.exe"]))
check("Parser ohne Weckwort", trg.parse_command(["clip", "spotify"], [1, 1], tde, ["potato"]) is None)
check("Parser unsicher", trg.parse_command(["potato", "clip"], [0.2, 0.9], tde, ["potato"]) is None)
check("Parser mit Fuellwort", trg.parse_command(["potato", "it", "klipp", "it"], [1, 1, 0.5, 1], tde, ["potato"])[:2]
      == ("clip", None))
check("Parser laengster Befehl", trg.parse_command(["potato", "aufnahme", "spotify", "starten"], [1, 1, 1, 1], tde,
                                                   ["potato"])[:2] == ("rec_start", ["app:spotify.exe"]))

voices = tts.voices()


def speak(text, lang):
    v = next((x["name"] for x in voices if str(x.get("culture", "")).lower().startswith(lang)), "")
    p = tts.synth(text, v)
    a = load_audio(p)
    os.remove(p)
    return a


def run(lang, sentences):
    got = []
    cfg = {"triggers_enabled": False, "voice_commands": True, "trigger_lang": lang}

    class Lib:
        sounds = []
    vt = trg.VoiceTriggers(cfg, Lib(), lambda sid: None, command=lambda a, k, l: got.append((a, k)),
                           apps=lambda: apps)
    vt.sync()
    results = []
    for text in sentences:
        n0 = len(got)
        a = np.concatenate([np.zeros((24000, 2), np.float32), speak(text, lang), np.zeros((48000, 2), np.float32)])
        for i in range(0, len(a), 480):
            vt.on_chunk("mic", a[i:i + 480])
            time.sleep(0.0015)
        t0 = time.time()
        while time.time() - t0 < 2.5 and len(got) == n0:
            time.sleep(0.05)
        results.append(got[n0:])
    vt.stop()
    return results


de_ok = [("Potato, clip it!", ("clip", None)), ("Potato, clip Spotify.", ("clip", ["app:spotify.exe"])),
         ("Kartoffel, clip das!", ("clip", None)), ("Potato, Aufnahme starten.", ("rec_start", None)),
         ("Potato, Aufnahme stoppen.", ("rec_stop", None)), ("Kartoffel, Aufnahme Spotify.", ("rec_start", ["app:spotify.exe"])),
         ("Potato, clip Chrome.", ("clip", ["app:chrome.exe"])), ("Potato, stopp!", ("stop", None))]
de_no = ["Ich habe gestern einen Clip auf Spotify gehört, der war echt lustig.",
         "Die Partei hat im Fernsehen über Kartoffeln und Tomaten gesprochen.",
         "Kannst du mal kurz die Aufnahme von gestern schicken? Danke dir.",
         "Wir spielen heute Abend noch eine Runde, kommst du auch?",
         "Die Partei hat beim Spiel die Aufnahme gestoppt, das war ein Clip für Discord.",
         "Ich glaube, er hat Potato gesagt, aber ich bin mir nicht sicher."]
res = run("de", [t for t, _ in de_ok] + de_no)
hits = 0
for (text, want), got in zip(de_ok, res):
    good = len(got) == 1 and got[0] == want
    hits += good
    print("   ", "✓" if good else "✗", text, "->", got, flush=True)
check("Deutsche Befehle erkannt", hits >= len(de_ok) - 1, f"{hits}/{len(de_ok)}")
false = [(t, g) for t, g in zip(de_no, res[len(de_ok):]) if g]
check("Deutsch: normale Saetze loesen nichts aus", not false, str(false))

en_ok = [("Potato, clip it!", ("clip", None)), ("Potato, clip Discord.", ("clip", ["app:discord.exe"])),
         ("Potato, start recording.", ("rec_start", None)), ("Potato, stop recording.", ("rec_stop", None)),
         ("Potato, record Spotify.", ("rec_start", ["app:spotify.exe"])), ("Potato, clip that!", ("clip", None))]
en_no = ["I made a clip of the stream yesterday and posted it on Discord.",
         "Can you pass me the potatoes? We're having dinner at seven.",
         "Let's start the recording session after lunch, okay?"]
res = run("en", [t for t, _ in en_ok] + en_no)
hits = 0
for (text, want), got in zip(en_ok, res):
    good = len(got) == 1 and got[0] == want
    hits += good
    print("   ", "✓" if good else "✗", text, "->", got, flush=True)
check("Englische Befehle erkannt", hits >= len(en_ok) - 1, f"{hits}/{len(en_ok)}")
false = [(t, g) for t, g in zip(en_no, res[len(en_ok):]) if g]
check("Englisch: normale Saetze loesen nichts aus", not false, str(false))

# ---------------------------------------------------------------- Ansage
from soundclip.announce import Announcer


class FakeCtl:
    cfg = {"announce_mode": "me", "announce_text": "Clip by Potato!", "announce_effect": "potato", "announce_voice": ""}
    played = []

    class _Sig:
        def __init__(self, store):
            self.store = store

        def emit(self, *a):
            self.store.append(a)
    toast = _Sig([])


fc = FakeCtl()
fc.announceReady = FakeCtl._Sig(fc.played)
an = Announcer(fc)
t0 = time.time()
d1 = an.render("Clip by Potato!")
t1 = time.time() - t0
t0 = time.time()
d2 = an.render("Clip by Potato!")
t2 = time.time() - t0
check("Ansage erzeugt", d1 is not None and 0.4 < len(d1) / 48000 < 4 and np.abs(d1).max() > 0.05,
      f"{len(d1) / 48000:.1f} s, erstes Mal {t1:.2f} s, danach {t2 * 1000:.0f} ms")
check("Ansage zwischengespeichert", d2 is d1)
an.say("clip")
fc.cfg["announce_mode"] = "off"
an.say("clip")
an.say("rec_start")
fc.cfg["announce_mode"] = "all"
an.say("rec_stop")
time.sleep(4)
check("Ansage-Modi", len(fc.played) == 2 and fc.played[0][1] is False and fc.played[1][1] is True,
      str([(len(x[0]), x[1]) for x in fc.played]))

# ---------------------------------------------------------------- Auto-Clip-Apps
from soundclip.autoclip import AutoClip
ac = AutoClip({"autoclip_apps": ["app:spotify.exe", "mic"]}, lambda: None)
check("Auto-Clip: gewaehlte Apps", ac.watches("app:spotify.exe") and ac.watches("mic") and not ac.watches("app:discord.exe"))
ac = AutoClip({"autoclip_apps": ["*"]}, lambda: None)
check("Auto-Clip: alle", ac.watches("app:valorant.exe"))
ac = AutoClip({"autoclip_apps": None, "autoclip_source": "mic"}, lambda: None)
check("Auto-Clip: alte Einstellung", ac.apps() == ["mic"] and ac.watches("mic") and not ac.watches("app:discord.exe"))

print("BEFEHL-TEST BESTANDEN" if ok else "BEFEHL-TEST FEHLGESCHLAGEN", flush=True)
sys.exit(0 if ok else 1)
