@echo off
rem Startet Potato Clips mit sichtbarer Konsole (zeigt Fehlermeldungen)
cd /d "%~dp0"
".venv\Scripts\python.exe" app.py %*
pause
