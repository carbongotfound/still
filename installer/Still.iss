; Still installer: one Still.exe, installed per user (no admin), registered as a Windows app and web browser.
; Re-running a newer setup updates the same Still.exe in place; browsing data in %LOCALAPPDATA%\Still is kept.
#ifndef AppExe
  #define AppExe "..\artifacts\Still\Still.exe"
#endif
#ifndef OutputRoot
  #define OutputRoot "..\artifacts"
#endif
#ifndef Bootstrapper
  #define Bootstrapper "..\tools\MicrosoftEdgeWebview2Setup.exe"
#endif
#ifndef AppVersion
  #define AppVersion "1.5.0"
#endif

[Setup]
AppId={{B734FE19-F6F3-4536-B1C8-250A22AF1A34}
AppName=Still
AppVersion={#AppVersion}
AppVerName=Still {#AppVersion}
AppPublisher=Still
AppPublisherURL=https://github.com/carbongotfound/still
AppSupportURL=https://github.com/carbongotfound/still/issues
AppUpdatesURL=https://github.com/carbongotfound/still/releases
DefaultDirName={localappdata}\Programs\Still
DisableDirPage=auto
DefaultGroupName=Still
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputRoot}
OutputBaseFilename=Still-Setup-{#AppVersion}-x64
SetupIconFile=..\still\Assets\still.ico
UninstallDisplayIcon={app}\Still.exe
UninstallDisplayName=Still
LicenseFile=..\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
CloseApplicationsFilter=Still.exe
RestartApplications=yes
ChangesAssociations=yes
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription=Still browser setup
VersionInfoProductName=Still

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[InstallDelete]
; Older multi-file builds: remove their leftovers so only Still.exe remains.
Type: filesandordirs; Name: "{app}\*.dll"
Type: filesandordirs; Name: "{app}\Shell"
Type: filesandordirs; Name: "{app}\runtimes"
Type: filesandordirs; Name: "{app}\cs"
Type: filesandordirs; Name: "{app}\de"

[Files]
Source: "{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Bootstrapper}"; Flags: dontcopy

[Icons]
Name: "{autoprograms}\Still"; Filename: "{app}\Still.exe"; AppUserModelID: "Still.Browser"
Name: "{userdesktop}\Still"; Filename: "{app}\Still.exe"; Tasks: desktopicon

[Registry]
; Web browser registration (per user). Windows asks the user to confirm Still as the default.
Root: HKCU; Subkey: "Software\Classes\StillURL"; ValueType: string; ValueData: "Still URL"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\StillURL"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\StillURL\DefaultIcon"; ValueType: string; ValueData: """{app}\Still.exe"",0"
Root: HKCU; Subkey: "Software\Classes\StillURL\shell\open\command"; ValueType: string; ValueData: """{app}\Still.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\StillHTML"; ValueType: string; ValueData: "Still HTML Document"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\StillHTML\DefaultIcon"; ValueType: string; ValueData: """{app}\Still.exe"",0"
Root: HKCU; Subkey: "Software\Classes\StillHTML\shell\open\command"; ValueType: string; ValueData: """{app}\Still.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Still"; ValueType: string; ValueData: "Still"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Still\DefaultIcon"; ValueType: string; ValueData: """{app}\Still.exe"",0"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Still\shell\open\command"; ValueType: string; ValueData: """{app}\Still.exe"""
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Still\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Still"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Still\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "A quiet, pitch-black browser for Windows."
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Still\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: """{app}\Still.exe"",0"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Still\Capabilities\StartMenu"; ValueType: string; ValueName: "StartMenuInternet"; ValueData: "Still"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Still\Capabilities\URLAssociations"; ValueType: string; ValueName: "http"; ValueData: "StillURL"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Still\Capabilities\URLAssociations"; ValueType: string; ValueName: "https"; ValueData: "StillURL"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Still\Capabilities\FileAssociations"; ValueType: string; ValueName: ".html"; ValueData: "StillHTML"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Still\Capabilities\FileAssociations"; ValueType: string; ValueName: ".htm"; ValueData: "StillHTML"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Still\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "StillHTML"
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Still"; ValueData: "Software\Clients\StartMenuInternet\Still\Capabilities"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Still.exe"; Description: "Open Still"; Flags: nowait postinstall skipifsilent
Filename: "ms-settings:defaultapps?registeredAppUser=Still"; Description: "Make Still my default browser"; Flags: shellexec postinstall skipifsilent unchecked nowait

[Code]
const
  RuntimeKey = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
function RuntimeInstalled: Boolean;
var Version: String;
begin
  Result := RegQueryStringValue(HKLM32, RuntimeKey, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0');
  if not Result then Result := RegQueryStringValue(HKCU, RuntimeKey, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ExitCode: Integer;
begin
  Result := '';
  if RuntimeInstalled then exit;
  if WizardSilent then begin
    Result := 'Install Microsoft Edge WebView2 Runtime, then run Still Setup again.';
    exit;
  end;
  if MsgBox('Still needs Microsoft Edge WebView2 Runtime. Download and install it from Microsoft now? An internet connection is required.', mbConfirmation, MB_YESNO) <> IDYES then begin
    Result := 'WebView2 installation was cancelled. Nothing was changed.';
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
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\Applications\Still.exe');
    // Browser data (%LOCALAPPDATA%\Still) and the shared WebView2 runtime are deliberately kept.
  end;
end;
