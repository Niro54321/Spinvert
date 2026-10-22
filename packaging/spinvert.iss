; Spinvert installer for Inno Setup 6, built by packaging/build.py.
; Installs for the current user only (no admin prompt), into
; %LOCALAPPDATA%\Programs\Spinvert.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{231392C8-5C07-4DC4-B4B9-5705767AFA81}
AppName=Spinvert
AppVersion={#AppVersion}
AppVerName=Spinvert {#AppVersion}
AppPublisher=Niro54321
AppPublisherURL=https://github.com/Niro54321/Spinvert
AppSupportURL=https://github.com/Niro54321/Spinvert/issues
AppUpdatesURL=https://github.com/Niro54321/Spinvert/releases
DefaultDirName={autopf}\Spinvert
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=Spinvert-Setup-{#AppVersion}
SetupIconFile=..\build\spinvert.ico
UninstallDisplayIcon={app}\Spinvert.exe
UninstallDisplayName=Spinvert
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "startup"; Description: "Start Spinvert when Windows starts (it waits in the tray)"
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "ffmpeg"; Description: "Download FFmpeg with winget, for audio and video (about 100 MB)"; Check: NeedsFFmpeg

[Files]
Source: "..\dist\Spinvert\*"; DestDir: "{app}"; Excludes: "spinvert-selftest.exe"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Spinvert"; Filename: "{app}\Spinvert.exe"
Name: "{autodesktop}\Spinvert"; Filename: "{app}\Spinvert.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Spinvert"; ValueData: """{app}\Spinvert.exe"" --background"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "winget.exe"; Parameters: "install --id Gyan.FFmpeg --exact --source winget --silent --accept-package-agreements --accept-source-agreements"; StatusMsg: "Downloading FFmpeg for audio and video..."; Tasks: ffmpeg; Flags: runhidden waituntilterminated
Filename: "{app}\Spinvert.exe"; Description: "Start Spinvert now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Spinvert.exe /F"; Flags: runhidden; RunOnceId: "StopSpinvert"

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';

function NeedsFFmpeg: Boolean;
begin
  Result := (FileSearch('ffmpeg.exe', GetEnv('PATH')) = '')
    and not FileExists(ExpandConstant('{localappdata}\Microsoft\WinGet\Links\ffmpeg.exe'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { An older Spinvert may be running from the tray; close it so its files can be replaced. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM Spinvert.exe /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Value: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { Spinvert's own settings can also add these; remove them only if they point here. }
    if RegQueryStringValue(HKCU, RunKey, 'Spinvert', Value) and
       (Pos(Lowercase(ExpandConstant('{app}')), Lowercase(Value)) > 0) then
      RegDeleteValue(HKCU, RunKey, 'Spinvert');
    DeleteFile(ExpandConstant('{usersendto}\Spinvert.lnk'));
  end;
end;
