#define AppVersion "0.3.1"
[Setup]
AppId={{956D0D15-EA99-4888-B0B3-E9A0B6813B4F}
AppName=mergen
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\mergen
DefaultGroupName=mergen
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir=..\release
OutputBaseFilename=mergen-setup-{#AppVersion}
SetupIconFile=..\assets\mergen.ico
UninstallDisplayIcon={app}\Mergen.exe
UninstallDisplayName=mergen
Uninstallable=yes
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
[Languages]
Name: "turkish"; MessagesFile: "..\build-tools\turkish-lowercase.isl"
[Tasks]
Name: "desktopicon"; Description: "masaüstünde kısayol oluştur"; Flags: unchecked
Name: "pythonruntime"; Description: "bileşen indirmeleri için uygulamaya özel python 3.12 kur"; Flags: checkedonce
[Files]
Source: "..\dist\Mergen\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build-tools\python\*"; DestDir: "{localappdata}\mergen-next\python"; Flags: ignoreversion recursesubdirs createallsubdirs; Tasks: pythonruntime
Source: "..\dist\Mergen\_internal\MSVCP140*.dll"; DestDir: "{localappdata}\mergen-next\python"; Flags: ignoreversion; Tasks: pythonruntime
Source: "..\dist\Mergen\_internal\VCRUNTIME140*.dll"; DestDir: "{localappdata}\mergen-next\python"; Flags: ignoreversion; Tasks: pythonruntime
Source: "..\dist\Mergen\_internal\vcomp140.dll"; DestDir: "{localappdata}\mergen-next\python"; Flags: ignoreversion; Tasks: pythonruntime
[Icons]
Name: "{group}\mergen"; Filename: "{app}\Mergen.exe"
Name: "{group}\mergen uygulamasını kaldır"; Filename: "{uninstallexe}"
Name: "{autodesktop}\mergen"; Filename: "{app}\Mergen.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\Mergen.exe"; Description: "mergen uygulamasini ac"; Flags: nowait postinstall skipifsilent
[Code]
function NeedsPython: Boolean;
begin
  Result := not FileExists(ExpandConstant('{localappdata}\mergen-next\python\python.exe'));
end;
