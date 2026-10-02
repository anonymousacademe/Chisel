; Inno Setup script for the LoreWriter Windows installer (per-user, no admin).
; Built by packaging/build.py, which passes: AppVersion, SourceDir (the PyInstaller
; onedir), OutputDir, IconFile, LicenseFile.
#ifndef AppVersion
  #error AppVersion is required (build through packaging/build.py)
#endif

[Setup]
AppId={{6F1B7C1E-52A4-4C0D-9B58-3E7A1D0A4B21}
AppName=LoreWriter
AppVersion={#AppVersion}
AppVerName=LoreWriter {#AppVersion}
AppPublisher=Mishkin
AppPublisherURL=https://github.com/anonymousacademe/lorewriter
AppSupportURL=https://github.com/anonymousacademe/lorewriter/issues
DefaultDirName={autopf}\LoreWriter
DefaultGroupName=LoreWriter
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=LoreWriter-{#AppVersion}-windows-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\LoreWriter.exe
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
Name: "{autoprograms}\LoreWriter"; Filename: "{app}\LoreWriter.exe"
Name: "{autoprograms}\LoreWriter (terminal)"; Filename: "{app}\lorewrite.exe"
Name: "{autodesktop}\LoreWriter"; Filename: "{app}\LoreWriter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LoreWriter.exe"; Description: "Start LoreWriter"; Flags: nowait postinstall skipifsilent
