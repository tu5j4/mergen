param([string]$PythonExe = '')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$tools=Join-Path $projectRoot 'build-tools'
if (-not $PythonExe) { $PythonExe=Join-Path $projectRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonExe)) { $PythonExe=(Get-Command python -ErrorAction Stop).Source }
New-Item -ItemType Directory -Path $tools -Force | Out-Null
$ProgressPreference='SilentlyContinue'
function Fetch-Verified([string]$Url,[string]$Path,[string]$Hash) {
    if (-not (Test-Path -LiteralPath $Path)) { Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Path -TimeoutSec 300 }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Hash) { throw "Hash mismatch: $Path" }
}
Fetch-Verified 'https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.12.15%2B20261013-x86_64-pc-windows-msvc-install_only.tar.gz' (Join-Path $tools 'python-runtime.tar.gz') 'bbc902d4d187ac4914915bf538196a064b49109a33a104965b5164ced5b80a1e'
Fetch-Verified 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe' (Join-Path $tools 'innosetup.exe') '9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732'
& $PythonExe (Join-Path $PSScriptRoot 'extract_runtime.py') (Join-Path $tools 'python-runtime.tar.gz') $tools
if ($LASTEXITCODE -ne 0) { throw 'Runtime extraction failed' }
$compiler=Join-Path $tools 'inno\ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    $process=Start-Process -FilePath (Join-Path $tools 'innosetup.exe') -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS','/SP-',('/DIR="'+(Join-Path $tools 'inno')+'"')) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Compiler installation failed' }
}
& (Join-Path $tools 'python\python.exe') -c 'import sys,venv,ensurepip; print(sys.version)'
if ($LASTEXITCODE -ne 0) { throw 'Portable Python validation failed' }
Write-Output "Build dependencies verified: $tools"
