; One-click per-user installer built from the PyInstaller bundle.
; GitHub Actions compiles this into dist\BuddySetup.exe.

#define MyAppName "Buddy Overlay"
#define MyAppVersion "0.9.0"
#define MyAppPublisher "Buddy"
#define MyAppExe "Buddy.exe"

[Setup]
AppId={{8F3A91C0-4D27-4B6E-9C18-5E2A7F11B0D3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Buddy
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=BuddySetup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName={#MyAppName}
SetupLogging=yes
DisableWelcomePage=no

[Files]
Source: "..\dist\Buddy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Buddy"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\Buddy"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch Buddy"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
