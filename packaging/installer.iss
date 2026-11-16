; Inno-Setup-Skript fuer Potato Clips
; Bauen: packaging\build.ps1  (braucht vorher den PyInstaller-Ordner dist\PotatoClips)
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Potato Clips"
#define AppExe "PotatoClips.exe"

[Setup]
AppId={{8C3E7B52-5A1F-4C3B-9E2D-6F0A1B2C3D4E}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Potato Clips
AppPublisherURL=https://github.com/swulfen13/potato-clips
AppSupportURL=https://github.com/swulfen13/potato-clips/issues
DefaultDirName={localappdata}\Programs\Potato Clips
DefaultGroupName=Potato Clips
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=PotatoClips-Setup-{#AppVersion}
SetupIconFile=..\assets\potato_clips.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no
LicenseFile=..\LICENSE

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop"; GroupDescription: "Zusätzlich:"
Name: "autostart"; Description: "Mit Windows starten (läuft unauffällig im Hintergrund)"; GroupDescription: "Zusätzlich:"

[Files]
Source: "..\dist\PotatoClips\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; alte Programmdateien vor einem Update entfernen (Einstellungen/Sounds liegen woanders und bleiben)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--minimized"; Tasks: autostart

[Run]
Filename: "https://vb-audio.com/Cable/"; Description: "VB-Cable herunterladen (damit Freunde in Discord deine Sounds hören)"; Flags: shellexec postinstall skipifsilent nowait unchecked; Check: not CableInstalled
Filename: "{app}\{#AppExe}"; Description: "Potato Clips jetzt starten"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#AppExe}"; Flags: runhidden; RunOnceId: "KillApp"
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im audiocap.exe"; Flags: runhidden; RunOnceId: "KillHelper"

[UninstallDelete]
Type: files; Name: "{userstartup}\{#AppName}.lnk"

[Code]
function CableInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{sys}\drivers\vbaudio_cable64_win10.sys')) or
            FileExists(ExpandConstant('{sys}\drivers\vbaudio_cable64_win7.sys')) or
            FileExists(ExpandConstant('{sys}\drivers\vbaudio_cable64arm_win10.sys'));
end;
