@echo off
rem Baut audiocap.exe mit Visual Studio 2022 (C++ Build Tools)
setlocal
set VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat
if not exist "%VCVARS%" (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -property installationPath`) do set VCVARS=%%i\VC\Auxiliary\Build\vcvars64.bat
)
call "%VCVARS%" >nul || exit /b 1
cd /d "%~dp0"
if exist "..\assets\potato_clips.ico" (
  copy /y "..\assets\potato_clips.ico" "app.ico" >nul
) else if exist "..\data\potato_clips.ico" (
  copy /y "..\data\potato_clips.ico" "app.ico" >nul
)
set RES=
if exist "app.ico" (
  rc /nologo /fo "%TEMP%\audiocap.res" audiocap.rc && set RES="%TEMP%\audiocap.res"
)
rem in eine neue Datei bauen und dann austauschen (die alte koennte noch laufen)
cl /nologo /O2 /EHsc /std:c++17 /W3 /utf-8 audiocap.cpp %RES% /Fe:..\bin\audiocap_new.exe /Fo:%TEMP%\audiocap.obj /link /SUBSYSTEM:CONSOLE || exit /b 1
if exist "..\bin\audiocap.exe" del /f /q "..\bin\audiocap.exe" 2>nul
if exist "..\bin\audiocap.exe" (
  echo bin\audiocap.exe ist noch in Benutzung - bitte Potato Clips beenden und nochmal bauen.
  exit /b 2
)
move /y "..\bin\audiocap_new.exe" "..\bin\audiocap.exe" >nul
exit /b 0
