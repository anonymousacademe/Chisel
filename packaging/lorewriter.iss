; Inno Setup script for the Chisel Windows installer (per-user, no admin).
; Built by packaging/build.py, which passes: AppVersion, SourceDir (the PyInstaller
; onedir), OutputDir, IconFile, LicenseFile.
#ifndef AppVersion
  #error AppVersion is required (build through packaging/build.py)
#endif

[Setup]
AppId={{6F1B7C1E-52A4-4C0D-9B58-3E7A1D0A4B21}
AppName=Chisel
AppVersion={#AppVersion}
AppVerName=Chisel {#AppVersion}
AppPublisher=Mishkin
AppPublisherURL=https://github.com/anonymousacademe/lorewriter
AppSupportURL=https://github.com/anonymousacademe/lorewriter/issues
DefaultDirName={autopf}\Chisel
DefaultGroupName=Chisel
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=Chisel-{#AppVersion}-windows-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\Chisel.exe
LicenseFile={#LicenseFile}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
VersionInfoVersion={#AppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Chisel"; Filename: "{app}\Chisel.exe"
Name: "{autoprograms}\Chisel (terminal)"; Filename: "{app}\lorewrite.exe"
Name: "{autodesktop}\Chisel"; Filename: "{app}\Chisel.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Chisel.exe"; Description: "Start Chisel"; Flags: nowait postinstall skipifsilent
