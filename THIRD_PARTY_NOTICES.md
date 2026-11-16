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
| PyInstaller-Bootloader | GPL-2.0 mit Ausnahme für gebündelte Programme | https://pyinstaller.org |

Qt/PySide6 und libsndfile werden als eigene DLLs mitgeliefert (dynamisch gelinkt) und können im
Installationsordner unter `_internal\` durch eigene Versionen ersetzt werden, wie es die LGPL vorsieht.
Die Lizenztexte liegen den jeweiligen Paketen bei.

**VB-Cable** (VB-Audio Software) wird **nicht** mitgeliefert. Es ist kostenlos (Donationware) und
wird von https://vb-audio.com/Cable/ heruntergeladen.
