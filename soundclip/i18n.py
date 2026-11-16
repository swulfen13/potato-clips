"""Sprache (Deutsch/Englisch) und die Texte des Potato-Modus.

Die Oberflaeche ist auf Deutsch geschrieben. tr() uebersetzt einen deutschen Text ins Englische
(wenn eingestellt) und legt im Potato-Modus die albernen Texte darueber. install() haengt tr() an
Qt (setText, Tooltips, Titel, Menues, Dialoge ...), damit nicht jede Stelle im Code angepasst werden muss.
"""
from __future__ import annotations

import re

LANG = "de"          # "de" | "en"
MODE = "pro"         # "pro" | "potato"


def setup(lang: str, mode: str) -> None:
    global LANG, MODE
    LANG = lang if lang in ("de", "en") else "de"
    MODE = mode if mode in ("pro", "potato") else "pro"


# ---------------------------------------------------------------- Deutsch -> Englisch
EN: dict[str, str] = {
    # Navigation / Seitenleiste
    "Soundboard": "Soundboard", "Stimme verändern": "Voice changer", "Clips && Editor": "Clips && Editor",
    "Clips & Editor": "Clips & Editor", "Quellen && Aufnahme": "Sources && Recording",
    "Quellen & Aufnahme": "Sources & Recording", "Einstellungen": "Settings", "Soundboard & Clips": "Soundboard & Clips",
    "Clip speichern": "Save clip", "Aufnahme starten": "Start recording", "Aufnahme stoppen": "Stop recording",
    "Alle Sounds stoppen": "Stop all sounds", "Öffnen": "Open", "Overlay ein/aus": "Overlay on/off", "Beenden": "Quit",
    "Potato Clips läuft weiter": "Potato Clips is still running",
    "Hotkeys und Clip-Puffer sind aktiv. Beenden über das Tray-Symbol.":
        "Hotkeys and the clip buffer stay active. Quit from the tray icon.",
    "bin\\audiocap.exe fehlt – setup.bat ausführen": "bin\\audiocap.exe is missing – run setup.bat",
    "bin\\audiocap.exe fehlt – bitte setup.bat ausführen": "bin\\audiocap.exe is missing – please run setup.bat",
    # Clips
    "Clips & Aufnahmen": "Clips & recordings", "Jetzt clippen": "Clip now", "Umbenennen": "Rename", "Löschen": "Delete",
    "Ordner": "Folder", "Name": "Name", "Quellen – wähle aus, was im Clip zu hören sein soll":
        "Sources – choose what should be heard in the clip",
    "Schneiden – grünen/roten Marker ziehen (Linksklick setzt Start, Rechtsklick Ende)":
        "Trim – drag the green/red markers (left click sets start, right click sets end)",
    "Schnitt zurücksetzen": "Reset trim", "Nur letzte 5s": "Last 5 s only", "Nur letzte 10s": "Last 10 s only",
    "Stille abschneiden": "Trim silence", "Effekte (werden der Reihe nach angewendet)": "Effects (applied in order)",
    "Stimme": "Voice", "Klang": "Tone", "Raum": "Space", "Clip": "Clip", "Stimme —": "Voice —", "Klang —": "Tone —",
    "Raum —": "Space —", "Nur für Clips —": "Clips only —", "Effekt": "Effect", "Vorhören": "Preview",
    "Nur du hörst es": "Only you hear it", "Für alle abspielen": "Play for everyone",
    "Du und deine Freunde (virtuelles Mikro)": "You and your friends (virtual mic)", "Stop": "Stop",
    "Ins Soundboard": "Add to soundboard", "Exportieren": "Export", "Name des Sounds": "Sound name",
    "Nur diese Quelle vorhören": "Preview only this source", "Solo": "Solo",
    "Nichts zu hören – ist mindestens eine Quelle aktiv?": "Nothing to hear – is at least one source enabled?",
    "Aufnahme": "Recording", "Sound": "Sound", "Stärke": "Strength", "Exportiert": "Exported",
    # Overlay / Status
    "Stimme: {name} · {n} %": "Voice: {name} · {n} %",
    # Einstellungen
    "Nur für Clips": "Clips only", "schwach": "weak", "stark": "strong", "Mikrofon-Gerät": "Microphone device",
    "Ruhig, dunkel, aufgeräumt": "Calm, dark, tidy", "Laut, bunt, albern": "Loud, colorful, silly",
    "Allgemein": "General", "Automatisch (Windows)": "Automatic (Windows)", "Aussehen": "Appearance", "Sprache": "Language", "Profi": "Pro",
    "Potato-Modus": "Potato mode", "Ruhig und dunkel, wie ein Audio-Programm": "Calm and dark, like an audio tool",
    "Laut, bunt und absichtlich albern": "Loud, colorful and silly on purpose",
    "Mit Windows starten": "Start with Windows", "Startet unsichtbar im Hintergrund": "Starts quietly in the background",
    "Beim Schließen im Hintergrund weiterlaufen": "Keep running in the background when closed",
    "Clips und Hotkeys funktionieren weiter, Symbol unten rechts": "Clips and hotkeys keep working, icon in the tray",
    "Overlay im Spiel": "In-game overlay", "Zeigt Aufnahme, laufende Sounds und Meldungen":
        "Shows recording, playing sounds and messages",
    "Oben rechts": "Top right", "Oben links": "Top left", "Unten rechts": "Bottom right", "Unten links": "Bottom left",
    "Discord & Freunde": "Discord & friends", "Virtuelles Mikrofon": "Virtual microphone",
    "In Discord als Eingabe „CABLE Output“ wählen": "In Discord pick “CABLE Output” as input",
    "Meine Stimme mitschicken": "Send my voice", "Mikrofon geht mit Effekt an Discord": "Your mic goes to Discord, with effect",
    "Lautstärke der Stimme": "Voice volume", "Das hört Discord gerade": "What Discord hears right now",
    "Test-Sound senden": "Send test sound", "Test-Sound an Discord": "Test sound to Discord",
    "Spielt einen kurzen Ton NUR ins virtuelle Mikro – der Balken links muss ausschlagen":
        "Plays a short tone ONLY into the virtual mic – the meter on the left should move",
    "VB-Cable gefunden": "VB-Cable found", "Kein VB-Cable gefunden": "No VB-Cable found",
    "Lautstärke auf 100 %": "Volume at 100 %", "Lautstärke zu niedrig": "Volume too low",
    "Keine fremden Apps im Kabel": "No other apps in the cable", "Andere Apps im Kabel": "Other apps in the cable",
    "VB-Cable installieren": "Install VB-Cable",
    "In Discord unter Sprache & Video: Rauschunterdrückung auf „Keine“, Echoentfernung aus, Eingabeempfindlichkeit von Hand einstellen.":
        "In Discord under Voice & Video: noise suppression “None”, echo cancellation off, set input sensitivity manually.",
    "Mikrofon": "Microphone", "KI-Rauschfilter": "AI noise filter", "Entfernt Tastatur, Lüfter und Klicken":
        "Removes keyboard, fans and clicks", "Stärke des Filters": "Filter strength",
    "Stille zwischen Sätzen": "Silence between sentences", "Dämpft Geräusche, wenn du nicht sprichst":
        "Mutes noise while you're not talking",
    "Audio-Geräte": "Audio devices", "Ich höre über": "I listen through",
    "Folgt automatisch, wenn du in Windows wechselst": "Follows automatically when you switch in Windows",
    "Neu laden": "Reload", "Geräte neu laden": "Reload devices",
    "Clips & Aufnahme": "Clips & recording", "Clip-Länge": "Clip length",
    "So viel wird beim Clippen rückwirkend gespeichert": "How much is saved backwards when you clip",
    "Apps nie aufnehmen": "Never record these apps", "Diese Apps tauchen nirgends auf": "These apps never show up",
    "z. B. spotify.exe, chrome.exe": "e.g. spotify.exe, chrome.exe", "Speicherort": "Storage location",
    "Ordner öffnen": "Open folder", "Datenordner öffnen": "Open data folder",
    "Wenn ein Sound nochmal gedrückt wird": "When a sound is pressed again", "Neu starten": "Restart",
    "Stoppen": "Stop", "Überlagern": "Overlap", "Sound startet von vorne": "Sound starts over",
    "Sound stoppt (an/aus)": "Sound stops (toggle)", "Sound wird nochmal drübergelegt": "Sound plays again on top",
    "Hotkeys": "Hotkeys", "funktionieren auch im Spiel": "work in games too",
    "Sound-Hotkeys legst du im Soundboard fest (Rechtsklick auf einen Sound).":
        "Sound hotkeys are set in the soundboard (right click a sound).",
    "Läuft ein Spiel als Administrator, Potato Clips auch als Administrator starten.":
        "If a game runs as administrator, start Potato Clips as administrator too.",
    "Über Potato Clips": "About Potato Clips", "Nach Updates suchen": "Check for updates",
    "Version {v} · Open Source (MIT) · alles bleibt auf deinem PC": "Version {v} · open source (MIT) · everything stays on your PC",
    "Alles wird sofort gespeichert.": "Everything is saved instantly.",
    "Neustart nötig": "Restart needed",
    "Potato Clips startet kurz neu, damit das neue Aussehen bzw. die neue Sprache überall greift. Jetzt neu starten?":
        "Potato Clips will restart briefly so the new look or language applies everywhere. Restart now?",
    "Auf 100 % stellen": "Set to 100 %", "Windows-Standard": "Windows default",
    "Windows-Standard (folgt automatisch)": "Windows default (follows automatically)", "Automatisch": "Automatic",
    "Aus (nur ich höre die Sounds)": "Off (only I hear the sounds)", "kein virtuelles Kabel gefunden": "no virtual cable found",
    "empfohlen": "recommended", "Aus – Sounds hörst nur du.": "Off – only you hear the sounds.",
    "Wähle oben <b>CABLE Input</b>, damit deine Freunde die Sounds hören.":
        "Pick <b>CABLE Input</b> above so your friends hear the sounds.",
    "nicht verbunden": "not connected",
    "In <b>Discord → Einstellungen → Sprache &amp; Video → Eingabegerät</b> auswählen:":
        "In <b>Discord → Settings → Voice &amp; Video → Input device</b> select:",
    "Ausgabegerät in Discord bleibt dein Kopfhörer/Lautsprecher – <b>nicht</b> das Kabel.":
        "Discord's output device stays your headphones/speakers – <b>not</b> the cable.",
    "In Discord als Eingabegerät das <b>Output</b>-Ende des gewählten Kabels wählen:":
        "In Discord choose the <b>Output</b> end of the selected cable as input device:",
    "Virtuelles Mikro nicht verbunden – oben CABLE Input wählen": "Virtual mic not connected – pick CABLE Input above",
    "Mikro wird nach der laufenden Aufnahme gewechselt": "The mic will switch after the current recording",
    "Kopfhörer-Ausgabe": "Headphone output", "Virtuelles Mikro": "Virtual mic",
    "Kein virtuelles Mikro aktiv – bitte oben auswählen": "No virtual mic active – please select one above",
    "KI-Rauschfilter nicht gefunden (bin\\rnnoise.dll fehlt)": "AI noise filter not found (bin\\rnnoise.dll missing)",
    "Lautstärke des virtuellen Kabels auf 100 % gestellt": "Virtual cable volume set to 100 %",
    "Test-Sound an Discord gesendet": "Test sound sent to Discord", "Autostart eingeschaltet": "Autostart on",
    "Autostart ausgeschaltet": "Autostart off", "stumm": "muted",
    # Soundboard
    "Sound bearbeiten": "Edit sound", "Farbe wählen": "Choose color", "Hotkey": "Hotkey", "Lautstärke": "Volume",
    "Farbe": "Color", "Tipp: Hotkeys funktionieren global – auch im Spiel.": "Tip: hotkeys work everywhere – even in games.",
    "Sounds hinzufügen": "Add sounds", "Alle stoppen": "Stop all", "Ich höre die Sounds": "I hear the sounds",
    "Freunde hören die Sounds": "Friends hear the sounds", "Gesamt-Lautstärke": "Master volume", "Suchen": "Search",
    "Noch keine Sounds.\n\nZieh Audiodateien (WAV, MP3, OGG, FLAC) hier rein,\nklick auf „+ Sounds hinzufügen“ oder speichere einen Clip als Sound.":
        "No sounds yet.\n\nDrop audio files (WAV, MP3, OGG, FLAC) here,\nclick “+ Add sounds” or save a clip as a sound.",
    "Nur für mich vorhören": "Preview just for me", "Name, Hotkey, Lautstärke, Farbe": "Name, hotkey, volume, color",
    "Im Clip-Editor bearbeiten (Schneiden/Effekte)": "Edit in clip editor (trim/effects)", "Nach vorne": "Move forward",
    "Nach hinten": "Move back", "Im Explorer zeigen": "Show in Explorer", "Abspielen": "Play", "kein Hotkey": "no hotkey",
    "Kein virtuelles Mikro – deine Freunde hören die Sounds nicht (siehe Einstellungen)":
        "No virtual mic – your friends can't hear the sounds (see settings)",
    "Freunde über:": "Friends via:", "Diese Dateien konnten nicht gelesen werden:": "These files could not be read:",
    # Quellen
    "Läuft im Hintergrund mit und landet in Clips": "Runs in the background and ends up in clips",
    "Bei Aufnahme": "When recording", "Wird vom Aufnahme-Hotkey mit aufgenommen (nichts angehakt = alle)":
        "Included by the record hotkey (nothing ticked = all)",
    "Nur diese Quelle aufnehmen (nochmal klicken = stopp)": "Record only this source (click again = stop)",
    "Diese App ausblenden (Einstellungen → Apps ignorieren)": "Hide this app (Settings → ignore apps)",
    "Alles, was hier läuft, wird im Hintergrund mitgeschnitten. Beim Bearbeiten eines Clips wählst du aus, welche Quellen zu hören sein sollen.":
        "Everything running here is captured in the background. When editing a clip you choose which sources are heard.",
    "Alles mitschneiden": "Capture everything", "Nur ausgewählte": "Selected only",
    "Gesamter Systemsound als Extra-Spur": "Whole system sound as an extra track",
    "Diese App zusätzlich ins virtuelle Mikro schicken – deine Freunde hören sie mit":
        "Also send this app into the virtual mic – your friends hear it too",
    "Lautstärke für Discord": "Volume for Discord",
    "Während einer Aufnahme kann die Clip-Länge nicht geändert werden": "The clip length can't change during a recording",
    "Kein virtuelles Mikro verbunden – Einstellungen → Discord / Freunde":
        "No virtual mic connected – Settings → Discord & friends",
    "aus – „Clippen“ einschalten, um mitzuschneiden": "off – turn on “Clip” to capture", "nimmt auf": "recording",
    "läuft": "running", "Fehler": "Error", "spielt gerade Ton": "playing audio", "läuft – wartet auf Ton": "running – waiting for audio",
    "Clippen": "Clip", "Ausblenden": "Hide", "Mikrofon · ": "Microphone · ", "System (alles zusammen)": "System (everything)",
    "startet": "starting", "beendet": "stopped",
    # Stimme
    "Billiges Kartoffel-Mikro": "Cheap potato microphone", "Viel zu laut eingestellt": "Way too loud",
    "Maximal übersteuert": "Distortion maxed out", "Hohe Quietschstimme": "High squeaky voice",
    "Tief und brummig": "Low and rumbly", "Tief, dreckig, mit Hall": "Deep, dirty, with reverb",
    "Riesig und dröhnend": "Huge and booming", "Metallisch wie ein Bot": "Metallic like a bot",
    "Außerirdisch schwebend": "Floating and otherworldly", "Hallig und unheimlich": "Echoey and eerie",
    "Alter Telefonhörer": "Old phone handset", "Walkie-Talkie mit Rauschen": "Walkie-talkie with static",
    "Durch eine Flüstertüte": "Through a megaphone", "Aus dem Handy-Lautsprecher": "From a phone speaker",
    "Ansage im Stadion": "Stadium announcement", "Blubbernd unter Wasser": "Bubbling under water",
    "Leiernde Kassette": "Wobbly cassette", "Retro-Game-Konsole": "Retro game console",
    "In einer riesigen Kirche": "In a huge cathedral", "Rufen in den Bergen": "Shouting in the mountains",
    "Wie mehrere Leute": "Like several people", "Zitternde Stimme": "Trembling voice",
    "Klick: einschalten / ausschalten · Rechtsklick: Hotkey": "Click: on / off · right click: hotkey",
    "Hotkey festlegen": "Set hotkey", "Einmal drücken = Effekt an, nochmal drücken = aus.":
        "Press once = effect on, press again = off.",
    "Stimme live verändern": "Change your voice live",
    "Dein Mikrofon wird in Echtzeit verändert – deine Freunde in Discord hören es sofort. Klick auf einen Effekt zum Einschalten, nochmal klicken zum Ausschalten.":
        "Your microphone is changed in real time – your friends in Discord hear it instantly. Click an effect to turn it on, click again to turn it off.",
    "Stimmeffekt an": "Voice effect on", "Wie stark der aktuelle Effekt ist – wird pro Effekt gemerkt":
        "How strong the current effect is – remembered per effect", "Mikro": "Mic", "Mit Effekt": "With effect",
    "An Discord schicken": "Send to Discord", "Mikro sauber": "Clean mic",
    "KI-Rauschfilter: entfernt Lüfter, Tastatur und Rauschen aus deiner Stimme":
        "AI noise filter: removes fans, keyboard and hiss from your voice",
    "Mich selbst hören (Kopfhörer!)": "Hear myself (headphones!)", "Einstellungen öffnen": "Open settings",
    "Hotkey entfernen": "Remove hotkey", "Einschalten": "Turn on", "aus": "off",
    "Tipp: Rechtsklick auf einen Effekt = eigener Hotkey nur für diesen Effekt. „Stärker/Schwächer“ ändert den gerade aktiven Effekt in 10-%-Schritten.":
        "Tip: right click an effect = its own hotkey. “Stronger/Weaker” changes the active effect in 10 % steps.",
    "Mithören an – bitte Kopfhörer nutzen, sonst gibt es Rückkopplung": "Monitoring on – use headphones or you'll get feedback",
    "Effekt an/aus": "Effect on/off", "Nächster Effekt": "Next effect", "Stärker (+10 %)": "Stronger (+10 %)",
    "Schwächer (−10 %)": "Weaker (−10 %)", "Nur Mithören aktiv – Discord bekommt nichts.":
        "Monitoring only – Discord gets nothing.",
    "Hier klicken und Tastenkombination drücken": "Click here and press a key combination",
    "Klicken und Tasten drücken": "Click and press keys", "Kein Audio ausgewählt": "No audio selected",
    "Auswahl: {a}s von {b}s": "Selection: {a}s of {b}s",
    # Controller / Hotkeys
    "Clip speichern (letzte X Sekunden)": "Save clip (last X seconds)", "Aufnahme starten/stoppen": "Start/stop recording",
    "Stimme an Discord ein/aus": "Voice to Discord on/off", "Stimmeffekt ein/aus": "Voice effect on/off",
    "Nächster Stimmeffekt": "Next voice effect", "Stimmeffekt stärker": "Voice effect stronger",
    "Stimmeffekt schwächer": "Voice effect weaker", "Alle Sounds gestoppt": "All sounds stopped", "alle Quellen": "all sources",
    "Keine Audio-Ausgabe aktiv – siehe Einstellungen": "No audio output active – see settings",
    "Aufnahme verworfen (nur Stille)": "Recording discarded (silence only)", "Stimmeffekt aus": "Voice effect off",
    "Clip: in den letzten Sekunden war alles still": "Clip: everything was silent in the last seconds",
    "Mikro-Durchleitung AN": "Mic passthrough ON", "Mikro-Durchleitung AUS": "Mic passthrough OFF",
    "Vorschau": "Preview", "Potato Clips – Fehler": "Potato Clips – error",
    # Effekte
    "Potato Mic": "Potato Mic", "Übersteuertes Mikro": "Overdriven mic", "Earrape (sehr laut!)": "Earrape (very loud!)",
    "Chipmunk / Helium": "Chipmunk / Helium", "Tiefe Stimme": "Deep voice", "Dämon": "Demon", "Riese": "Giant",
    "Roboter": "Robot", "Alien": "Alien", "Geist": "Ghost", "Telefon": "Telephone", "Funkgerät": "Walkie-talkie",
    "Megafon": "Megaphone", "Handy-Lautsprecher": "Phone speaker", "Stadion-Durchsage": "Stadium announcer",
    "Unter Wasser": "Under water", "Lo-Fi Kassette": "Lo-fi cassette", "8-Bit": "8-bit", "Bass-Boost": "Bass boost",
    "Hall / Kathedrale": "Reverb / cathedral", "Echo": "Echo", "Chor / Doppelt": "Choir / double",
    "Jet / Flanger": "Jet / flanger", "Wackelstimme": "Wobble voice", "Schneller abspielen": "Play faster",
    "Zeitlupe": "Slow motion", "Rückwärts": "Reverse", "Stotter": "Stutter", "Glitch / Kaputte CD": "Glitch / broken CD",
    "Ein-/Ausblenden": "Fade in/out", "Lauter machen (Normalisieren)": "Make louder (normalize)",
    # Neue Funktionen
    "Als MP3 in die Zwischenablage – in Discord mit Strg+V einfügen": "As MP3 to the clipboard – paste in Discord with Ctrl+V",
    "Für Discord kopieren": "Copy for Discord", "Update verfügbar": "Update available",
    "Update wird geladen …": "Downloading update …", "Abbrechen": "Cancel",
    "Neue Clips sofort kopieren": "Copy new clips right away",
    "Nach dem Clippen liegt der Clip als MP3 in der Zwischenablage – in Discord Strg+V":
        "After clipping, the clip is on the clipboard as MP3 – Ctrl+V in Discord",
    "Andere Apps leiser, wenn ein Sound läuft": "Lower other apps while a sound plays",
    "Spiel und Musik werden kurz leiser, damit du den Sound gut hörst": "Game and music get quieter so you hear the sound",
    "So laut bleiben die anderen Apps": "Other apps stay this loud", "Auch Discord leiser machen": "Lower Discord too",
    "Aus = deine Freunde bleiben immer gleich laut": "Off = your friends always stay at the same volume",
    "Automatisch nach Updates schauen": "Check for updates automatically",
    "Einmal am Tag, nur eine kurze Anfrage an GitHub": "Once a day, just a short request to GitHub",
    "Einrichtung starten": "Start setup", "Einrichtungs-Assistent": "Setup assistant",
    "VB-Cable, Discord und Mikro Schritt für Schritt": "VB-Cable, Discord and mic step by step",
    "Suche nach Updates": "Checking for updates", "Sound-Packs": "Sound packs",
    "Sounds als eine Datei an Freunde schicken oder ein Pack von Freunden laden":
        "Send sounds to friends as one file or load a pack from friends",
    "Alle Sounds als Pack speichern": "Save all sounds as a pack", "Sound-Pack importieren": "Import sound pack",
    "Sound-Pack speichern": "Save sound pack", "Potato Clips Sound-Pack (*.potatopack)": "Potato Clips sound pack (*.potatopack)",
    "Als Sound-Pack teilen": "Share as sound pack", "Noch keine Sounds zum Teilen": "No sounds to share yet",
    "Vorlesen": "Read aloud", "Text eingeben – wird in Discord vorgelesen": "Type text – it gets read out in Discord",
    "mit Stimmeffekt": "with voice effect", "Als Sound speichern": "Save as sound", "Windows-Stimme": "Windows voice",
    "Wird vorgelesen": "Reading aloud", "Eigener Effekt": "Custom effect", "Eigener Effekt bearbeiten": "Edit custom effect",
    "Eigenen Effekt bearbeiten": "Edit custom effect", "Eigenen Effekt löschen": "Delete custom effect",
    "Name, z. B. Roboter im Keller": "Name, e.g. robot in the basement",
    "Wähle bis zu 4 Effekte, sie werden der Reihe nach auf deine Stimme gelegt.":
        "Pick up to 4 effects, they are applied to your voice in order.",
    "Mehrere Effekte zu deinem eigenen Stimmeffekt mixen": "Mix several effects into your own voice effect",
    "Mindestens einen Effekt auswählen": "Pick at least one effect", "Nur solange gedrückt": "Only while held",
    "Stimmeffekt nur solange gedrückt": "Voice effect only while held",
    "Potato Clips einrichten": "Set up Potato Clips", "Zurück": "Back", "Weiter": "Next", "Überspringen": "Skip",
    "Willkommen bei Potato Clips": "Welcome to Potato Clips",
    "In vier kurzen Schritten ist alles bereit: Aussehen, virtuelles Mikro für Discord, Discord-Einstellungen und dein Mikrofon.":
        "Four quick steps and you're ready: look, virtual mic for Discord, Discord settings and your microphone.",
    "Wie soll Potato Clips aussehen?": "How should Potato Clips look?", "Sprache / Language": "Language / Sprache",
    "Virtuelles Mikro (VB-Cable)": "Virtual mic (VB-Cable)",
    "Damit deine Freunde in Discord deine Sounds und Stimmeffekte hören, braucht Windows ein virtuelles Mikrofon. Dafür gibt es das kostenlose VB-Cable.":
        "For your friends in Discord to hear your sounds and voice effects, Windows needs a virtual microphone. The free VB-Cable does that.",
    "VB-Cable herunterladen": "Download VB-Cable", "Nochmal prüfen": "Check again",
    "Nach der Installation von VB-Cable den PC einmal neu starten. Du kannst auch ohne weitermachen – dann hörst nur du die Sounds.":
        "Restart your PC once after installing VB-Cable. You can also continue without it – then only you hear the sounds.",
    "Discord einstellen": "Set up Discord",
    "Öffne in Discord: Einstellungen → Sprache & Video. Stell dort Folgendes ein:":
        "In Discord open: Settings → Voice & Video. Set the following:",
    "Der Balken zeigt, was Discord gerade von Potato Clips bekommt.": "The meter shows what Discord gets from Potato Clips right now.",
    "Dein Mikrofon": "Your microphone", "Sag kurz etwas – der Balken sollte ausschlagen.": "Say something – the meter should move.",
    "KI-Rauschfilter (Tastatur, Lüfter und Klicken raus)": "AI noise filter (removes keyboard, fans and clicks)",
    "Fertig!": "Done!", "Potato Clips läuft jetzt im Hintergrund. Die wichtigsten Tasten:":
        "Potato Clips now runs in the background. The most important keys:",
    "Sounds legst du im Soundboard an (einfach Dateien reinziehen). Alles andere findest du in den Einstellungen.":
        "Add sounds in the soundboard (just drop files in). Everything else is in the settings.",
    "Los geht's": "Let's go", "Noch kein VB-Cable installiert": "VB-Cable is not installed yet",
    "Clip ist größer als 10 MB – Discord nimmt ihn evtl. nicht": "Clip is larger than 10 MB – Discord may not accept it",
    "Clip kopiert – in Discord mit Strg+V einfügen": "Clip copied – paste in Discord with Ctrl+V",
    "Du hast die neueste Version": "You have the latest version",
    "Update-Prüfung fehlgeschlagen (offline?)": "Update check failed (offline?)",
    # Geraete-Fehler
    "Gerät wird gerade von einer anderen App exklusiv benutzt": "Device is in exclusive use by another app",
    "Gerät wurde entfernt oder deaktiviert": "Device was removed or disabled",
    "Format wird vom Gerät nicht unterstützt": "Format not supported by the device", "Gerät nicht gefunden": "Device not found",
    "kein virtuelles Mikro gewählt": "no virtual mic selected", "Ausgabe beendet": "Output stopped",
}

# Texte mit Zahlen/Namen darin: (Regex auf Deutsch, englische Vorlage)
EN_PATTERNS: list[tuple[re.Pattern, str]] = [(re.compile(a), b) for a, b in [
    (r"^(\d+) Quellen laufen$", r"\1 sources running"),
    (r"^Puffer: letzte (\d+) s$", r"Buffer: last \1 s"),
    (r"^Clip-Hotkey: (.+)$", r"Clip hotkey: \1"),
    (r"^Potato Clips · (\d+) Quelle\(n\) · Clip (\d+)s(.*)$", r"Potato Clips · \1 source(s) · clip \2s\3"),
    (r"^Stimme: (.+) · (\d+) %$", r"Voice: \1 · \2 %"),
    (r"^Stimme: (.+) \((\d+) %\)(.*)$", r"Voice: \1 (\2 %)\3"),
    (r"^(.+) · (\d+) Quelle\(n\) · (.+)$", r"\1 · \2 source(s) · \3"),
    (r"^„(.+)“ ist jetzt im Soundboard – Rechtsklick drauf für Hotkey$", r"“\1” is now on the soundboard – right click it for a hotkey"),
    (r"^„(.+)“ wirklich löschen\?$", r"Really delete “\1”?"),
    (r"^(\d+) Sound\(s\) hinzugefügt$", r"\1 sound(s) added"),
    (r"^Fehler: (.+)$", r"Error: \1"),
    (r"^Clip-Länge: (\d+) Sekunden \(Puffer startet neu\)$", r"Clip length: \1 seconds (buffer restarts)"),
    (r"^„(.+)“ ausblenden und nicht mehr mitschneiden\?\n\nRückgängig: Einstellungen → Apps ignorieren\.$",
     r"Hide “\1” and stop capturing it?\n\nUndo: Settings → never record these apps."),
    (r"^Aufnahme läuft: (.+)$", r"Recording: \1"),
    (r"^Hotkeys: Aufnahme (.*)  ·  Clip (.*)$", r"Hotkeys: record \1  ·  clip \2"),
    (r"^Discord: (.+) wird jetzt an deine Freunde geschickt$", r"Discord: \1 is now sent to your friends"),
    (r"^(.+)\nKlick: einschalten / ausschalten · Rechtsklick: Hotkey$", r"\1\nClick: on / off · right click: hotkey"),
    (r"^(.+)\nLinksklick: abspielen · Rechtsklick: Optionen$", r"\1\nLeft click: play · right click: options"),
    (r"^Hotkey für <b>(.+)</b>$", r"Hotkey for <b>\1</b>"),
    (r"^Clip gespeichert \((\d+)s\): (.+)$", r"Clip saved (\1s): \2"),
    (r"^Aufnahme läuft: (.+)$", r"Recording: \1"),
    (r"^Aufnahme gespeichert \((\d+)s\)$", r"Recording saved (\1s)"),
    (r"^„(.+)“ kann nicht geladen werden: (.+)$", r"“\1” can't be loaded: \2"),
    (r"^Clip fehlgeschlagen: (.+)$", r"Clip failed: \1"),
    (r"^(.+): Stärke (\d+) %$", r"\1: strength \2 %"),
    (r"^Hotkey-Problem: (.+)$", r"Hotkey problem: \1"),
    (r"^Autostart fehlgeschlagen: (.+)$", r"Autostart failed: \1"),
    (r"^Audio-Ausgabe: (.+)$", r"Audio output: \1"),
    (r"^Exportiert: (.+)$", r"Exported: \1"),
    (r"^Potato Clips (.+) ist da\. Jetzt aktualisieren\?$", r"Potato Clips \1 is out. Update now?"),
    (r"^Update fehlgeschlagen: (.+)$", r"Update failed: \1"),
    (r"^(\d+) Sound\(s\) aus dem Pack hinzugefügt$", r"\1 sound(s) added from the pack"),
    (r"^Sound-Pack mit (\d+) Sound\(s\) gespeichert – einfach an Freunde schicken$",
     r"Sound pack with \1 sound(s) saved – just send it to friends"),
    (r"^Vorlesen fehlgeschlagen: (.+)$", r"Read aloud failed: \1"),
    (r"^Gefunden: (.+)$", r"Found: \1"),
    (r"^Mikrofon · (.+)$", r"Microphone · \1"),
    (r"^Automatisch – (.+)$", r"Automatic – \1"),
    (r"^Kopfhörer-Ausgabe: (.+)$", r"Headphone output: \1"),
    (r"^Virtuelles Mikro: (.+)$", r"Virtual mic: \1"),
    (r"^„(.+)“ nicht gefunden – nutze Windows-Standard$", r"“\1” not found – using Windows default"),
    (r"^„(.+)“ nicht gefunden$", r"“\1” not found"),
    (r"^Version (.+) · Open Source \(MIT\) · alles bleibt auf deinem PC$",
     r"Version \1 · open source (MIT) · everything stays on your PC"),
    (r"^Clip (\d\d\.\d\d\. \d\d:\d\d(:\d\d)?)$", r"Clip \1"),
    (r"^Aufnahme (\d\d\.\d\d\. \d\d:\d\d(:\d\d)?)$", r"Recording \1"),
]]

# Laengere Saetze in Rich-Text (mit Farben drumherum): Teilstuecke ersetzen
EN_FRAGMENTS: list[tuple[str, str]] = [
    ("spielt gerade ebenfalls ins virtuelle Kabel – das hören deine Freunde in Discord mit. Stell in dieser App das "
     "Ausgabegerät auf deinen Kopfhörer/Lautsprecher um.",
     "is also playing into the virtual cable – your friends in Discord hear it too. Switch that app's output to your "
     "headphones/speakers."),
    ("Das <i>Ausgabegerät</i> in Discord muss dein Kopfhörer sein, nur das <i>Eingabegerät</i> ist CABLE Output – sonst "
     "hören deine Freunde sich selbst als Echo.",
     "Discord's <i>output device</i> must be your headphones, only the <i>input device</i> is CABLE Output – otherwise "
     "your friends hear themselves as an echo."),
    ("● Verbunden:</span> Sounds gehen an", "● Connected:</span> sounds go to"),
    ("● Fehler:</span>", "● Error:</span>"),
    ("Freunde über:", "Friends via:"),
    ("1.  Eingabegerät:", "1.  Input device:"), ("2.  Ausgabegerät: dein Kopfhörer (<b>nicht</b> das Kabel)",
     "2.  Output device: your headphones (<b>not</b> the cable)"),
    ("3.  Rauschunterdrückung: <b>Keine</b> · Echoentfernung: <b>aus</b>",
     "3.  Noise suppression: <b>None</b> · echo cancellation: <b>off</b>"),
    ("4.  Eingabeempfindlichkeit von Hand einstellen (Regler weit links)",
     "4.  Set input sensitivity manually (slider far left)"),
    ("✓</span> Gefunden:", "✓</span> Found:"), ("✕</span> Noch kein VB-Cable installiert", "✕</span> VB-Cable is not installed yet"),
    ("Wähle <b>CABLE Input (VB-Audio Virtual Cable)</b>.", "Pick <b>CABLE Input (VB-Audio Virtual Cable)</b>."),
    ("In Windows zu leise eingestellt: ", "Set too quiet in Windows: "),
    (" – deine Freunde hören dich dann kaum.", " – your friends will barely hear you."),
    ("Deine Stimme geht gerade nirgendwo hin – schalte <b>„An Discord schicken“</b> ein.",
     "Your voice isn't going anywhere – turn on <b>“Send to Discord”</b>."),
    ("Kein virtuelles Mikro verbunden – in den Einstellungen <b>CABLE Input</b> wählen.",
     "No virtual mic connected – pick <b>CABLE Input</b> in the settings."),
    ("Bereit – in Discord muss das Eingabegerät <b>CABLE Output</b> sein.",
     "Ready – Discord's input device must be <b>CABLE Output</b>."),
    ("Dein Mikrofon liefert gerade nur Stille – ist es stummgeschaltet? (Windows-Einstellungen → Sound → Eingabe, oder "
     "Mute-Taste am Mikro/Webcam)",
     "Your microphone only delivers silence – is it muted? (Windows settings → Sound → Input, or the mute button on "
     "your mic/webcam)"),
    ("Tipps für Discord: Rauschunterdrückung (Krisp) und Echo-Unterdrückung ausschalten, sonst werden Sounds weggefiltert. "
     "Mit Push-to-Talk kommen Sounds nur durch, solange die PTT-Taste gedrückt ist – besser „Sprachaktivierung“ nutzen.",
     "Discord tips: turn off noise suppression (Krisp) and echo cancellation, otherwise sounds get filtered. With "
     "push-to-talk sounds only get through while the PTT key is held – voice activity works better."),
    (" – Achtung: „Stimme an Discord“ ist aus", " – note: “voice to Discord” is off"),
]

# ---------------------------------------------------------------- Potato-Modus (Texte ueber der Sprache)
POT_DE: dict[str, str] = {
    "Soundboard": "Knöpfe", "Stimme verändern": "Stimme kaputtmachen", "Clips && Editor": "Beweise", "Clips & Editor": "Beweise",
    "Quellen && Aufnahme": "Abhören", "Einstellungen": "Knöpfchen", "Soundboard & Clips": "für Leute ohne Hobbys",
    "Clip speichern": "Beweis sichern", "Aufnahme starten": "Heimlich mitschneiden", "Aufnahme stoppen": "Genug gehört",
    "Alle Sounds stoppen": "PANIKKNOPF", "Alle stoppen": "PANIKKNOPF", "Stimme live verändern": "STIMME KAPUTTMACHEN",
    "Clips & Aufnahmen": "BEWEISMITTEL", "Quellen & Aufnahme": "Abhören",
    "Ich höre die Sounds": "Ich hör's", "Freunde hören die Sounds": "Freunde hören's auch (sorry)",
    "Gesamt-Lautstärke": "Vernunft ↔ Chaos", "Sounds hinzufügen": "MEHR LÄRM", "kein Hotkey": "keine Taste",
    "Stärke": "Wie schlimm?", "An Discord schicken": "An Discord (Freunde leiden mit)",
    "Mikro sauber": "Tastatur rausfiltern", "Mich selbst hören (Kopfhörer!)": "Selbst hören (auf eigene Gefahr)",
    "Stimmeffekt an": "EFFEKT AN", "Mikro": "Gebrüll", "Mit Effekt": "Ergebnis",
    "schwach": "bisschen", "stark": "Polizei",
    "Billiges Kartoffel-Mikro": "Klingt wie aus einer Kartoffel", "Viel zu laut eingestellt": "Mikro auf 300 %",
    "Maximal übersteuert": "Nur für Feinde", "Hohe Quietschstimme": "Ballon zum Frühstück",
    "Tief und brummig": "Morgens vor dem Kaffee", "Tief, dreckig, mit Hall": "Mitternacht im Keller",
    "Riesig und dröhnend": "Tritt gleich durch die Decke", "Metallisch wie ein Bot": "Beep. Boop. Hallo.",
    "Außerirdisch schwebend": "Kommt in Frieden. Vielleicht.", "Hallig und unheimlich": "Wohnt in deinem Lautsprecher",
    "Alter Telefonhörer": "Oma ruft an", "Walkie-Talkie mit Rauschen": "Over. Over. OVER.",
    "Durch eine Flüstertüte": "Für Leute, die eh schon laut sind", "Aus dem Handy-Lautsprecher": "Bus-Musik",
    "Ansage im Stadion": "Der nächste Zug fällt aus", "Blubbernd unter Wasser": "Blub.",
    "Leiernde Kassette": "Omas Walkman", "Retro-Game-Konsole": "Piep piep, Highscore",
    "In einer riesigen Kirche": "Sehr heilig, sehr hallig", "Rufen in den Bergen": "Hallo-o-o",
    "Wie mehrere Leute": "Du, aber dreimal", "Zitternde Stimme": "Zu viel Kaffee",
    "Allgemein": "Allgemeines Gedöns", "Discord & Freunde": "Discord-Kram", "Mikrofon": "Mikro-Putz",
    "Audio-Geräte": "Woher, wohin", "Clips & Aufnahme": "Beweissicherung", "Hotkeys": "Tasten",
    "Über Potato Clips": "Wer war das?", "Profi": "Profi (für Erwachsene)", "Potato-Modus": "Potato-Modus (für dich)",
    "Mit Windows starten": "Mit Windows aufwachen", "Startet unsichtbar im Hintergrund": "Die Kartoffel wacht mit dir auf",
    "Beim Schließen im Hintergrund weiterlaufen": "Schließen = weiterlaufen",
    "Clips und Hotkeys funktionieren weiter, Symbol unten rechts": "Sie geht nie wirklich weg",
    "Stille zwischen Sätzen": "Atmen ist privat", "Test-Sound senden": "TESTGERÄUSCH ABFEUERN",
    "Nach Updates suchen": "Gibt's was Neues?", "Alles wird sofort gespeichert.": "Speichert von selbst. Magie.",
    "Wenn ein Sound nochmal gedrückt wird": "Wenn du denselben Knopf nochmal drückst …",
    "Überlagern": "Noch einer drüber (Chaos)", "Neu starten": "Von vorne", "Stoppen": "Ruhe",
    "Jetzt clippen": "BEWEIS SICHERN", "Ins Soundboard": "Ab aufs Knopfbrett",
    "Vorlesen": "Vorquatschen", "Sound-Packs": "Lärm-Pakete", "Eigener Effekt": "Eigene Katastrophe",
    "Andere Apps leiser, wenn ein Sound läuft": "Alle anderen: Klappe, wenn ich drücke",
    "Für Discord kopieren": "Ab in den Chat damit", "Nur solange gedrückt": "Nur solange ich drücke",
}
POT_EN: dict[str, str] = {
    "Soundboard": "Buttons", "Voice changer": "Wreck your voice", "Clips && Editor": "Evidence",
    "Clips & Editor": "Evidence", "Sources && Recording": "Snooping", "Settings": "Knobs", "Soundboard & Clips": "for people with no hobbies",
    "Save clip": "Save evidence", "Start recording": "Start snooping", "Stop recording": "Heard enough",
    "Stop all sounds": "PANIC BUTTON", "Stop all": "PANIC BUTTON", "Change your voice live": "WRECK YOUR VOICE",
    "Clips & recordings": "EVIDENCE LOCKER", "Sources & Recording": "Snooping",
    "I hear the sounds": "I hear it", "Friends hear the sounds": "Friends hear it too (sorry)",
    "Master volume": "Reason ↔ Chaos", "Add sounds": "MORE NOISE", "no hotkey": "no key",
    "Strength": "How bad?", "Send to Discord": "To Discord (friends suffer too)", "Clean mic": "Filter out keyboard",
    "Hear myself (headphones!)": "Hear yourself (at your own risk)", "Voice effect on": "EFFECT ON",
    "Mic": "Yelling", "With effect": "Result", "weak": "a little", "strong": "cops",
    "Cheap potato microphone": "Sounds like it lives in a potato", "Way too loud": "Mic set to 300 %",
    "Distortion maxed out": "Enemies only", "High squeaky voice": "Had a balloon for breakfast",
    "Low and rumbly": "Before the first coffee", "Deep, dirty, with reverb": "Midnight in the basement",
    "Huge and booming": "About to step through the ceiling", "Metallic like a bot": "Beep. Boop. Hello.",
    "Floating and otherworldly": "Comes in peace. Probably.", "Echoey and eerie": "Lives in your speakers",
    "Old phone handset": "Grandma is calling", "Walkie-talkie with static": "Over. Over. OVER.",
    "Through a megaphone": "For people who are loud anyway", "From a phone speaker": "Music on the bus",
    "Stadium announcement": "The next train is cancelled", "Bubbling under water": "Blub.",
    "Wobbly cassette": "Grandma's walkman", "Retro game console": "Beep beep, high score",
    "In a huge cathedral": "Very holy, very echoey", "Shouting in the mountains": "Hello-o-o",
    "Like several people": "You, but three times", "Trembling voice": "Too much coffee",
    "General": "General stuff", "Discord & friends": "Discord things", "Microphone": "Mic cleanup",
    "Audio devices": "From where, to where", "Clips & recording": "Evidence", "Hotkeys": "Keys",
    "About Potato Clips": "Who did this?", "Pro": "Pro (for grown-ups)", "Potato mode": "Potato mode (for you)",
    "Start with Windows": "Wake up with Windows", "Starts quietly in the background": "The potato wakes up with you",
    "Keep running in the background when closed": "Closing = keeps running",
    "Clips and hotkeys keep working, icon in the tray": "It never really leaves",
    "Silence between sentences": "Breathing is private", "Send test sound": "FIRE TEST NOISE",
    "Check for updates": "Anything new?", "Everything is saved instantly.": "Saves by itself. Magic.",
    "When a sound is pressed again": "When you press the same button again …",
    "Overlap": "Another one on top (chaos)", "Restart": "From the top", "Stop": "Silence",
    "Clip now": "SAVE EVIDENCE", "Add to soundboard": "Onto the button board",
    "Read aloud": "Yap for me", "Sound packs": "Noise packs", "Custom effect": "Custom disaster",
    "Lower other apps while a sound plays": "Everyone else shut up when I press",
    "Copy for Discord": "Throw it in the chat", "Only while held": "Only while I hold it",
}

# Dekorative Emoji/Symbole am Anfang, die im Profi-Design wegfallen (funktionale Zeichen bleiben)
_PREFIX_RE = re.compile(r"^([^\w„\"“<(\[{]*)(.*?)([\s:…—]*)$", re.S)
_KEEP = set("●■▶←→⚠+−✕×♪—–·✓")


def _en(core: str) -> str:
    v = EN.get(core)
    if v is not None:
        return v
    for rx, rep in EN_PATTERNS:
        m = rx.match(core)
        if m:
            out = m.expand(rep)
            # Teile mit Namen, die selbst uebersetzbar sind (z. B. Effektname)
            return out
    return core


def _translate_core(core: str) -> str:
    if "&&" in core:          # Qt-Maskierung von & (z. B. in Knoepfen)
        return _translate_core(core.replace("&&", "&")).replace("&", "&&")
    out = core
    if LANG == "en":
        out = _en(core)
        if out == core and ("<" in core or len(core) > 40):
            for a, b in EN_FRAGMENTS:
                if a in out:
                    out = out.replace(a, b)
    if MODE == "potato":
        out = (POT_EN if LANG == "en" else POT_DE).get(out, out)
    return out


def tr(s):
    """Text in die eingestellte Sprache / den Modus bringen (idempotent)."""
    if not isinstance(s, str) or not s or (LANG == "de" and MODE == "pro" and not _has_deco(s)):
        return s
    out = _tr_one(s)
    if out == s and "\n" in s:
        out = "\n".join(_tr_one(line) for line in s.split("\n"))
    return out


def _tr_one(line: str) -> str:
    m = _PREFIX_RE.match(line)
    pre, core, suf = (m.group(1), m.group(2), m.group(3)) if m else ("", line, "")
    if not core:
        return line
    t = _translate_core(core)
    if t == core and LANG == "en" and (pre or suf):
        t2 = _translate_core(line)          # z. B. Rich-Text, der mit einem Zeichen beginnt
        if t2 != line:
            return t2
    if t.endswith("?") and suf.startswith(":"):
        suf = suf[1:]
    return _deco(pre, t) + suf


def _has_deco(s: str) -> bool:
    m = _PREFIX_RE.match(s)
    return bool(m and m.group(1) and any(ch not in _KEEP and not ch.isspace() for ch in m.group(1)))


def _deco(pre: str, s: str) -> str:
    if MODE == "pro":
        kept = "".join(ch for ch in pre if ch in _KEEP)
        return (kept + " " + s) if kept else s
    return pre + s


# ---------------------------------------------------------------- an Qt anhaengen
_installed = False


def install(app) -> None:
    """tr() in die ueblichen Qt-Text-Setter einhaengen und neue Widgets beim ersten Anzeigen uebersetzen."""
    global _installed
    if _installed:
        return
    _installed = True
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (QAbstractButton, QComboBox, QFileDialog, QGroupBox, QInputDialog, QLabel, QLineEdit,
                                   QMenu, QMessageBox, QSystemTrayIcon, QWidget)

    def wrap(cls, name, idxs=(0,)):
        orig = getattr(cls, name)

        def f(self, *a, **k):
            if a:
                a = list(a)
                for i in idxs:
                    if i < len(a) and isinstance(a[i], str):
                        a[i] = tr(a[i])
            return orig(self, *a, **k)
        setattr(cls, name, f)

    def wrap_static(cls, name, idxs):
        orig = getattr(cls, name)

        def f(*a, **k):
            a = list(a)
            for i in idxs:
                if i < len(a) and isinstance(a[i], str):
                    a[i] = tr(a[i])
            return orig(*a, **k)
        setattr(cls, name, staticmethod(f))

    wrap(QLabel, "setText")
    wrap(QAbstractButton, "setText")
    wrap(QAction, "setText")
    wrap(QGroupBox, "setTitle")
    wrap(QWidget, "setToolTip")
    wrap(QWidget, "setWindowTitle")
    wrap(QLineEdit, "setPlaceholderText")
    wrap(QComboBox, "addItem", (0, 1))
    wrap(QComboBox, "setItemText", (1,))
    wrap(QMenu, "addAction", (0, 1))
    wrap(QMenu, "setTitle")
    wrap(QSystemTrayIcon, "showMessage", (0, 1))
    wrap(QSystemTrayIcon, "setToolTip")
    for n in ("question", "information", "warning", "critical"):
        wrap_static(QMessageBox, n, (1, 2))
    wrap_static(QInputDialog, "getText", (1, 2))
    for n in ("getOpenFileNames", "getOpenFileName", "getSaveFileName", "getExistingDirectory"):
        wrap_static(QFileDialog, n, (1,))

    class Polisher(QObject):
        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.Polish and isinstance(obj, QWidget) and not obj.property("_tr"):
                obj.setProperty("_tr", True)
                try:
                    translate_widget(obj)
                except Exception:
                    pass
            return False

    app._tr_polisher = Polisher(app)
    app.installEventFilter(app._tr_polisher)


def translate_widget(w) -> None:
    """Texte, die beim Erzeugen gesetzt wurden (Konstruktor), nachtraeglich uebersetzen."""
    from PySide6.QtWidgets import QAbstractButton, QComboBox, QGroupBox, QLabel, QLineEdit, QMenu
    if isinstance(w, QLabel):
        t = w.text()
        if t:
            w.setText(t)
    elif isinstance(w, QAbstractButton):
        t = w.text()
        if t:
            w.setText(t)
    elif isinstance(w, QGroupBox):
        w.setTitle(w.title())
    elif isinstance(w, QLineEdit):
        if w.placeholderText():
            w.setPlaceholderText(w.placeholderText())
    elif isinstance(w, QComboBox):
        for i in range(w.count()):
            w.setItemText(i, w.itemText(i))
    if isinstance(w, QMenu):
        for a in w.actions():
            if a.text():
                a.setText(a.text())
    if w.toolTip():
        w.setToolTip(w.toolTip())
    if w.isWindow() and w.windowTitle():
        w.setWindowTitle(w.windowTitle())
