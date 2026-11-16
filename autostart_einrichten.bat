@echo off
rem Legt eine Verknuepfung in den Autostart, damit Potato Clips beim Windows-Start minimiert im Tray startet.
cd /d "%~dp0"
set TARGET=%~dp0.venv\Scripts\pythonw.exe
set LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Potato Clips.lnk
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%'); $s.TargetPath='%TARGET%'; $s.Arguments='app.py --minimized'; $s.WorkingDirectory='%~dp0'; $s.Save()"
echo Autostart eingerichtet: %LNK%
echo (Zum Entfernen die Datei Potato Clips.lnk im Autostart-Ordner loeschen.)
pause
