param([ValidateSet('install','menu','scan')][string]$Mode = 'install',
      [string]$Components = '', [switch]$AcceptInstall)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

function Find-Python311 {
    $ErrorActionPreference = 'Continue'
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidate = & py -3.11 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0) { $candidates += $candidate }
    }
    $candidates += (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $candidates += (Get-Command python).Source
    }
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        if ($candidate -match '\\WindowsApps\\') { continue }
        & $candidate -c 'import sys; sys.exit(0 if sys.version_info[:2]==(3,11) and sys.maxsize>2**32 and sys.prefix==sys.base_prefix else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return $candidate }
    }
    return $null
}

try {
    if ($AcceptInstall -and (-not $Components -or $Mode -ne 'install')) { throw 'otomatik onay yalniz acik bilesen listesiyle kullanilabilir.' }
    if ($Components -and -not $AcceptInstall) { throw 'bilesen listesiyle otomatik kurulum icin -AcceptInstall gereklidir.' }
    $pythonExe = Find-Python311
    if (-not $pythonExe) {
        Write-Host 'mergen icin python 3.11 (64 bit) gerekiyor.'
        if ($Mode -eq 'scan') { exit 1 }
        Write-Host 'python sisteminize kurulur; uygulama paketleri ayri sanal ortamda tutulur.'
        Write-Host 'python 3.11 kurulmasina izin veriyor musunuz? (winget veya imzali python.org paketi) [e/h]'
        $answer = if ($AcceptInstall) { 'e' } else { Read-Host 'seciminiz' }
        if ($answer -ne 'e') { Write-Host 'kurulum iptal edildi.'; exit 1 }
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            $downloadRoot = Join-Path $projectRoot '.installer-downloads'
            New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
            $pythonPackage = Join-Path $downloadRoot 'python-3.11.9-amd64.exe'
            $ProgressPreference = 'SilentlyContinue'
            Write-Host 'resmi python paketi indiriliyor ve imzasi kontrol ediliyor...'
            Invoke-WebRequest -UseBasicParsing -TimeoutSec 180 -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile $pythonPackage
            $signature = Get-AuthenticodeSignature -LiteralPath $pythonPackage
            if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Python Software Foundation') {
                throw 'python kurulum imzasi dogrulanamadi.'
            }
            Write-Host 'python kuruluyor; windows installer bu adimda birkac dakika bekleyebilir...'
            $installation = Start-Process -FilePath $pythonPackage -WindowStyle Hidden -PassThru -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=0','Include_test=0','Include_launcher=0','Include_doc=0','Include_dev=0','Include_tools=0','Include_tcltk=0','Shortcuts=0'
            while (-not $installation.WaitForExit(30000)) { Write-Host 'python kurulumu devam ediyor...' }
            if ($installation.ExitCode -notin @(0,3010)) { throw "python kurulumu basarisiz: $($installation.ExitCode)" }
        } else {
            & winget install --id Python.Python.3.11 --exact --scope user --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { throw 'python kurulumu basarisiz.' }
        }
        $pythonExe = Find-Python311
        if (-not $pythonExe) { throw 'python bulunamadi; bu pencereyi kapatip kurulum.bat dosyasini tekrar acin.' }
    }
    if ($AcceptInstall) {
        & $pythonExe (Join-Path $PSScriptRoot 'manager.py') --install ($Components -split ',') --yes
    } else {
        & $pythonExe (Join-Path $PSScriptRoot 'manager.py') --mode $Mode
    }
    exit $LASTEXITCODE
} catch {
    Write-Host "hata: $_"
    exit 1
}
