$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$downloadDir = Join-Path $projectRoot '.installer-downloads'
New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
$packagePath = Join-Path $downloadDir 'vc_redist.x64.exe'
$ProgressPreference = 'SilentlyContinue'
Invoke-WebRequest -UseBasicParsing -TimeoutSec 180 -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $packagePath
$signature = Get-AuthenticodeSignature -LiteralPath $packagePath
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
    throw 'microsoft imzasi dogrulanamadi; kurulum durduruldu.'
}
$process = Start-Process -FilePath $packagePath -ArgumentList '/install','/passive','/norestart' -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -notin @(0,3010,1638)) { throw "vc++ kurulum hatasi: $($process.ExitCode)" }
if ($process.ExitCode -eq 3010) { Write-Host 'windows yeniden baslatma istiyor.' }
