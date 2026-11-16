# PyInstaller-Spezifikation fuer Potato Clips (Ordner-Build, ohne Konsole).
# Bauen: packaging\build.ps1  (oder: python -m PyInstaller packaging\potato_clips.spec)
import os
import re

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
with open(os.path.join(ROOT, "soundclip", "__init__.py"), encoding="utf-8") as f:
    VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', f.read()).group(1)

# Versionsinfo fuer die EXE (Eigenschaften -> Details)
v = tuple(int(x) for x in (VERSION.split(".") + ["0", "0", "0"])[:4])
version_file = os.path.join(workpath, "version_info.txt")
os.makedirs(workpath, exist_ok=True)
with open(version_file, "w", encoding="utf-8") as f:
    f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040704b0', [
      StringStruct('CompanyName', 'Potato Clips'),
      StringStruct('FileDescription', 'Potato Clips'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', 'PotatoClips'),
      StringStruct('OriginalFilename', 'PotatoClips.exe'),
      StringStruct('ProductName', 'Potato Clips'),
      StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1031, 1200])])])
""")

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    binaries=[
        (os.path.join(ROOT, "bin", "audiocap.exe"), "bin"),
        (os.path.join(ROOT, "bin", "rnnoise.dll"), "bin"),
    ],
    datas=[(os.path.join(ROOT, "assets"), "assets"),
           (os.path.join(ROOT, "soundclip", "ui", "assets"), os.path.join("soundclip", "ui", "assets"))],
    hiddenimports=["soundclip.fxworker"],
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "sounddevice", "pyrnnoise",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.Qt3DCore", "PySide6.QtCharts",
              "PySide6.QtMultimedia", "PySide6.QtDataVisualization"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PotatoClips",
    console=False,
    icon=os.path.join(ROOT, "assets", "potato_clips.ico"),
    version=version_file,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PotatoClips")
