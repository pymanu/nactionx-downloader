; Instalador de NactionX Downloader para Windows (Inno Setup 6)
; Instala la distribución sobre Python oficial firmado (runtime\ + app\), compatible con Smart App Control.
; Uso: ISCC.exe /DAppVersion=1.0.0 /DSourceDir="...\portable\NactionX Downloader" /DOutputDir="...\releases" installer.iss

#define AppName "NactionX Downloader"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\build\portable\NactionX Downloader"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\releases"
#endif

[Setup]
AppId={{8F3B6C1E-5D2A-4B7E-9C41-6A0D2E7F3B55}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=NactionX
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
; Instalación por usuario: no pide permisos de administrador
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=NactionX-Downloader-{#AppVersion}-Windows-x64-Setup
SetupIconFile=..\icons\icon.ico
UninstallDisplayIcon={app}\app\nactionx\web\icon.ico
UninstallDisplayName={#AppName}
; ultra64 reserva diccionarios de >1 GB y agota la memoria del compilador; max comprime casi igual
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "*.cmd,LEEME.txt"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-m nactionx"; WorkingDir: "{app}\app"; IconFilename: "{app}\app\nactionx\web\icon.ico"; AppUserModelID: "NactionX.Downloader"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-m nactionx"; WorkingDir: "{app}\app"; IconFilename: "{app}\app\nactionx\web\icon.ico"; Tasks: desktopicon; AppUserModelID: "NactionX.Downloader"

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-m nactionx"; WorkingDir: "{app}\app"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
