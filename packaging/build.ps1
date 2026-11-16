# Baut den Windows-Installer: dist\PotatoClips-Setup-<version>.exe
#  1. bin\audiocap.exe (C++-Helfer)    -> helper\build.bat   (falls nicht vorhanden)
#  2. bin\rnnoise.dll                  -> aus dem pip-Paket pyrnnoise (falls nicht vorhanden)
#  3. PyInstaller-Ordner               -> dist\PotatoClips
#  4. Inno Setup                       -> dist\PotatoClips-Setup-<version>.exe
param([string]$Python = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not $Python) {
    $Python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
}
$version = (& $Python -c "import soundclip; print(soundclip.__version__)").Trim()
Write-Host "Potato Clips $version"

New-Item -ItemType Directory -Force bin | Out-Null
if (-not (Test-Path "bin\audiocap.exe")) {
    cmd /c helper\build.bat
    if ($LASTEXITCODE -ne 0) { throw "Helfer bauen fehlgeschlagen" }
}
if (-not (Test-Path "bin\rnnoise.dll")) {
    $dll = (& $Python -c "import importlib.util, pathlib; s = importlib.util.find_spec('pyrnnoise'); print(pathlib.Path(s.origin).parent / 'rnnoise.dll')").Trim()
    Copy-Item $dll bin\rnnoise.dll
}

& $Python -m PyInstaller packaging\potato_clips.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fehlgeschlagen" }

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 nicht gefunden (winget install JRSoftware.InnoSetup)" }
& $iscc "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup fehlgeschlagen" }
Write-Host "Fertig: dist\PotatoClips-Setup-$version.exe"
