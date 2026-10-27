#define AppVersion "0.4.0"
#ifndef ModelPayload
  #define ModelPayload "..\model-payload"
#endif
#ifndef PackedPayload
  #error PackedPayload is required
#endif
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
SolidCompression=no
DiskSpanning=no
ExtraDiskSpaceRequired=6000000000
LZMANumBlockThreads=2
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
[Languages]
Name: "turkish"; MessagesFile: "..\build-tools\turkish-lowercase.isl"
[Tasks]
Name: "desktopicon"; Description: "masaüstünde kısayol oluştur"; Flags: unchecked
[Files]
Source: "..\dist\Mergen\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build-tools\python\*"; DestDir: "{localappdata}\mergen-next\python"; Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall
Source: "..\dist\Mergen\_internal\MSVCP140*.dll"; DestDir: "{localappdata}\mergen-next\python"; Flags: ignoreversion uninsneveruninstall
Source: "..\dist\Mergen\_internal\VCRUNTIME140*.dll"; DestDir: "{localappdata}\mergen-next\python"; Flags: ignoreversion uninsneveruninstall
Source: "..\dist\Mergen\_internal\vcomp140.dll"; DestDir: "{localappdata}\mergen-next\python"; Flags: ignoreversion uninsneveruninstall
Source: "{#ModelPayload}\models\*"; Excludes: "\nllb-200-distilled-600M-hf\pytorch_model.bin,\nllb-1.3b-baglam-v3\base-bf16\model.safetensors,\manga\pytorch_model.bin,\nllb-1.3b-baglam-v3\adapter-masked\adapter_model.safetensors"; DestDir: "{localappdata}\mergen-next\models"; Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall
Source: "{#PackedPayload}\*.xz"; DestDir: "{localappdata}\mergen-next\model-archives"; Flags: ignoreversion nocompression uninsneveruninstall
[Icons]
Name: "{group}\mergen"; Filename: "{app}\Mergen.exe"
Name: "{group}\mergen uygulamasını kaldır"; Filename: "{uninstallexe}"
Name: "{autodesktop}\mergen"; Filename: "{app}\Mergen.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\Mergen.exe"; Parameters: "--configure-hardware"; Description: "mergen'i aç ve donanıma uygun çalışma kütüphanelerini kur"; Flags: nowait postinstall skipifsilent
[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Args: String;
begin
  if CurStep = ssPostInstall then begin
    WizardForm.StatusLabel.Caption := 'paketteki model dosyaları hazırlanıyor ve doğrulanıyor';
    Args := '"' + ExpandConstant('{app}\_internal\scripts\restore_packed_models.py') + '" --data-root "' + ExpandConstant('{localappdata}\mergen-next') + '" --manifest "' + ExpandConstant('{app}\_internal\assets\packed-models.json') + '"';
    if not Exec(ExpandConstant('{localappdata}\mergen-next\python\python.exe'), Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      RaiseException('model dosyaları hazırlanamadı. kurulum paketini yeniden çalıştırın.');
    if ResultCode <> 0 then
      RaiseException('model doğrulaması tamamlanamadı. ayrıntılar: model-restore.log');
  end;
end;
