# Verwendete Software von Dritten

Potato Clips selbst steht unter der MIT-Lizenz (siehe `LICENSE`). Der Installer enthält zusätzlich
diese Bibliotheken, jeweils unter ihrer eigenen Lizenz:

| Komponente | Lizenz | Projekt |
|---|---|---|
| Python | PSF License | https://www.python.org |
| Qt / PySide6 | LGPL-3.0 | https://www.qt.io, https://pyside.org |
| NumPy | BSD-3-Clause | https://numpy.org |
| SciPy | BSD-3-Clause | https://scipy.org |
| python-soundfile | BSD-3-Clause | https://github.com/bastibe/python-soundfile |
| libsndfile | LGPL-2.1 | https://libsndfile.github.io/libsndfile/ |
| keyboard | MIT | https://github.com/boppreh/keyboard |
| psutil | BSD-3-Clause | https://github.com/giampaolo/psutil |
| RNNoise (KI-Rauschfilter, `rnnoise.dll` aus dem Paket pyrnnoise) | BSD-3-Clause | https://github.com/xiph/rnnoise, https://github.com/pengzhendong/pyrnnoise |
| Schriftarten Inter, Bungee, Comic Neue (`assets/fonts`) | SIL Open Font License 1.1 | https://rsms.me/inter, https://github.com/djrpnt/bungee, https://comicneue.com |
| Vosk (Spracherkennung, `libvosk.dll`) | Apache-2.0 | https://github.com/alphacep/vosk-api |
| Vosk-Sprachmodelle (werden bei Bedarf geladen) | Apache-2.0 | https://alphacephei.com/vosk/models |
| ffmpeg (über imageio-ffmpeg, eigene `ffmpeg.exe`) | GPL (mit libx264) – Quellcode: https://ffmpeg.org | https://github.com/imageio/imageio-ffmpeg |
| imageio-ffmpeg | BSD-2-Clause | https://github.com/imageio/imageio-ffmpeg |
| qrcode | BSD-3-Clause | https://github.com/lincolnloop/python-qrcode |
| requests, srt, tqdm, websockets, cffi (von Vosk benötigt) | Apache-2.0 / MIT / MPL-2.0 / BSD-3-Clause / MIT | https://pypi.org |
| PyInstaller-Bootloader | GPL-2.0 mit Ausnahme für gebündelte Programme | https://pyinstaller.org |

Qt/PySide6 und libsndfile werden als eigene DLLs mitgeliefert (dynamisch gelinkt) und können im
Installationsordner unter `_internal\` durch eigene Versionen ersetzt werden, wie es die LGPL vorsieht.
Die Lizenztexte liegen den jeweiligen Paketen bei.

`ffmpeg.exe` ist ein eigenständiges Programm, das Potato Clips nur für den Video-Export aufruft; es steht unter der GPL.
Den Quellcode gibt es unter https://ffmpeg.org, die Build-Skripte unter https://github.com/imageio/imageio-binaries.

**VB-Cable** (VB-Audio Software) wird **nicht** mitgeliefert. Es ist kostenlos (Donationware) und
wird von https://vb-audio.com/Cable/ heruntergeladen.
