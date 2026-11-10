; Buddy Overlay installer. Per-user, no admin.
; Build it with packaging\build-windows.ps1, which produces dist\payload first.
;
; Code signing is not active. When a certificate exists, the build script
; calls signtool. Do not commit the certificate.
; A license key is not built. This script does not ask for one.

#define MyAppName "Buddy Overlay"
#define MyAppVersion "0.9.0"
#define MyAppPublisher "Buddy"
#define MyAppExe "Start-Buddy.bat"

[Setup]
AppId={{B7E4C1A2-6F0D-4E58-9A11-2C8F5D0B7E64}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Buddy
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Buddy-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName={#MyAppName}
SetupLogging=yes

[Files]
Source: "..\dist\payload\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Buddy"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\Buddy"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{autoprograms}\Repair Buddy"; Filename: "{srcexe}"

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Set up Buddy"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: files; Name: "{localappdata}\Buddy\logs\install.log"

[Code]
function LicenseKeyHook: Boolean;
begin
  { License key check is not built yet. Always allow install. }
  Result := True;
end;

procedure WriteInstallLog(const Line: String);
var
  Folder: String;
begin
  Folder := ExpandConstant('{localappdata}\Buddy\logs');
  ForceDirectories(Folder);
  SaveStringToFile(Folder + '\install.log', Line + #13#10, True);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    WriteInstallLog('Installing Buddy Overlay {#MyAppVersion}');
  if CurStep = ssPostInstall then
    WriteInstallLog('Install finished. Repair by running Buddy-Setup.exe again.');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    WriteInstallLog('Uninstall started.');
end;
