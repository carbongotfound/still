#ifndef AppSource
  #define AppSource "..\artifacts\Still"
#endif
#ifndef OutputRoot
  #define OutputRoot "..\artifacts"
#endif
#ifndef Bootstrapper
  #define Bootstrapper "..\tools\MicrosoftEdgeWebview2Setup.exe"
#endif
[Setup]
AppId={{B734FE19-F6F3-4536-B1C8-250A22AF1A34}
AppName=Still
AppVersion=0.0.0
AppPublisher=Carbon
DefaultDirName={localappdata}\Programs\Still
DefaultGroupName=Still
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
OutputDir={#OutputRoot}
OutputBaseFilename=Still-Setup-0.0-x64
SetupIconFile={#AppSource}\Assets\still.ico
UninstallDisplayIcon={app}\Still.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=Still
VersionInfoVersion=0.0.0.0
VersionInfoDescription=Still browser setup
VersionInfoProductName=Still

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Bootstrapper}"; Flags: dontcopy

[Icons]
Name: "{group}\Still"; Filename: "{app}\Still.exe"
Name: "{group}\Uninstall Still"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Still"; Filename: "{app}\Still.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Still.exe"; Description: "Open Still"; Flags: nowait postinstall skipifsilent

[Code]
const
  RuntimeKey = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
function RuntimeInstalled: Boolean;
var Version: String;
begin
  Result := RegQueryStringValue(HKLM32, RuntimeKey, 'pv', Version) and
    (Version <> '') and (Version <> '0.0.0.0');
  if not Result then Result := RegQueryStringValue(HKCU, RuntimeKey, 'pv', Version) and
    (Version <> '') and (Version <> '0.0.0.0');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ExitCode: Integer;
begin
  Result := '';
  if RuntimeInstalled then exit;
  if WizardSilent then begin
    Result := 'Install Microsoft Edge WebView2 Evergreen Runtime, then run Still Setup again.';
    exit;
  end;
  if MsgBox('Still needs Microsoft Edge WebView2 Runtime. Continue to download and install it from Microsoft? An internet connection is required.', mbConfirmation, MB_YESNO) <> IDYES then begin
    Result := 'WebView2 installation was cancelled. No browser data has been changed.';
    exit;
  end;
  ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
  if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
    Result := 'Could not start the Microsoft runtime installer.'
  else if not RuntimeInstalled then
    Result := 'WebView2 Runtime could not be installed. Install it from Microsoft and retry Still Setup.';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var Value: String;
begin
  if CurUninstallStep = usUninstall then begin
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Still', Value) and
      (Value = '"' + ExpandConstant('{app}\Still.exe') + '" --startup') then
      RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Still');
    // Browser data and the shared WebView2 runtime are deliberately preserved.
  end;
end;
