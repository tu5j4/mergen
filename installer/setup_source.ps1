param([switch]$Plan)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$dataRoot = Join-Path $projectRoot '.data'
$runtimeRoot = Join-Path $dataRoot 'python'
$runtimePython = Join-Path $runtimeRoot 'python.exe'
$venvRoot = Join-Path $projectRoot '.venv'
$guiPython = Join-Path $venvRoot 'Scripts\python.exe'
$runtimeUrl = 'https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.12.15%2B20261013-x86_64-pc-windows-msvc-install_only.tar.gz'
$runtimeHash = 'bbc902d4d187ac4914915bf538196a064b49109a33a104965b5164ced5b80a1e'
$transcribing = $false

function Assert-LocalPath([string]$Path) {
    $resolved = [IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'kurulum hedefi proje klasorunun disinda.'
    }
    $cursor = $resolved
    while ($cursor -ne $projectRoot) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'kurulum hedefinde baglanti bulundu; normal bir klasor kullanin.'
            }
        }
        $cursor = Split-Path -Parent $cursor
    }
}

function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "islem basarisiz (kod $LASTEXITCODE): $Executable" }
}

try {
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') {
        throw 'bu kurulum windows x64 icindir.'
    }
    Assert-LocalPath $runtimeRoot
    Assert-LocalPath $venvRoot
    if ($Plan) {
        Write-Output 'yalniz arayuz ortami kurulacak; modeller uygulama icinden indirilir.'
        Write-Output "python: $runtimeRoot"
        Write-Output "arayuz: $venvRoot"
        Write-Output "paketler: $(Join-Path $PSScriptRoot 'requirements-ui.txt')"
        exit 0
    }
    Set-Location -LiteralPath $projectRoot
    $env:PYTHONUTF8 = '1'
    $env:PYTHONNOUSERSITE = '1'
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    $env:MERGEN_DATA_DIR = $dataRoot
    $env:PIP_CACHE_DIR = Join-Path $dataRoot 'cache\pip'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $logRoot = Join-Path $dataRoot 'logs'
    Assert-LocalPath $logRoot
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    Start-Transcript -Path (Join-Path $logRoot 'source-setup.log') -Append | Out-Null
    $transcribing = $true
    Write-Host 'mergen kaynak kurulumu basliyor; sistem python ve ekran karti suruculeri degistirilmez.'
    if (-not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) {
        if (Test-Path -LiteralPath $runtimeRoot) {
            throw '.data\python eksik veya bozuk. klasoru yedekleyip yeniden deneyin.'
        }
        $downloads = Join-Path $dataRoot 'downloads'
        Assert-LocalPath $downloads
        New-Item -ItemType Directory -Path $downloads -Force | Out-Null
        $archive = Join-Path $downloads 'python-3.12.15.tar.gz'
        Assert-LocalPath $archive
        if (-not (Test-Path -LiteralPath $archive)) {
            Write-Host 'uygulamaya ozel python indiriliyor...'
            $ProgressPreference = 'SilentlyContinue'
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $partial = $archive + '.part'
            Assert-LocalPath $partial
            Invoke-WebRequest -UseBasicParsing -Uri $runtimeUrl -OutFile $partial -TimeoutSec 300
            if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $runtimeHash) {
                throw 'python indirmesinin sha256 ozeti uyusmuyor; tekrar deneyin.'
            }
            Move-Item -LiteralPath $partial -Destination $archive
        }
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $runtimeHash) {
            throw 'python indirmesinin sha256 ozeti uyusmuyor. .data\downloads altindaki arsivi kaldirip tekrar deneyin.'
        }
        $tar = (Get-Command tar.exe -ErrorAction Stop).Source
        $stage = Join-Path $downloads ('extract-' + [Guid]::NewGuid().ToString('N'))
        Assert-LocalPath $stage
        New-Item -ItemType Directory -Path $stage | Out-Null
        Invoke-Checked $tar @('-xzf', $archive, '-C', $stage)
        $extracted = Join-Path $stage 'python'
        Assert-LocalPath $extracted
        Invoke-Checked (Join-Path $extracted 'python.exe') @('-I', '-c', 'import sys,venv,ensurepip; assert sys.version_info[:2]==(3,12) and sys.maxsize>2**32')
        Assert-LocalPath $runtimeRoot
        Move-Item -LiteralPath $extracted -Destination $runtimeRoot
    }
    Invoke-Checked $runtimePython @('-I', '-c', 'import sys,venv,ensurepip; assert sys.version_info[:2]==(3,12) and sys.maxsize>2**32')
    if (-not (Test-Path -LiteralPath $guiPython)) {
        if (Test-Path -LiteralPath $venvRoot) { throw '.venv eksik veya bozuk. klasoru yedekleyip yeniden deneyin.' }
        Write-Host 'arayuz icin ayri python ortami olusturuluyor...'
        Invoke-Checked $runtimePython @('-I', '-m', 'venv', $venvRoot)
    }
    Invoke-Checked $guiPython @('-I', '-c', 'import sys; assert sys.prefix!=sys.base_prefix and sys.version_info[:2] in ((3,11),(3,12)) and sys.maxsize>2**32')
    Write-Host 'yalniz arayuz kutuphaneleri kuruluyor...'
    Invoke-Checked $guiPython @('-m', 'pip', '--isolated', '--cache-dir', $env:PIP_CACHE_DIR, 'install', '--upgrade', 'pip')
    Invoke-Checked $guiPython @('-m', 'pip', '--isolated', '--cache-dir', $env:PIP_CACHE_DIR, 'install', '-r', (Join-Path $PSScriptRoot 'requirements-ui.txt'))
    Invoke-Checked $guiPython @('-m', 'pip', '--isolated', 'check')
    Invoke-Checked $guiPython @('-c', 'import PySide6.QtQuick,cv2,numpy,PIL,psutil,mss,pynput,cryptography; print(''arayuz kutuphaneleri hazir'')')
    Write-Host 'guncel arayuz acilis testi calistiriliyor...'
    Invoke-Checked $guiPython @('-m', 'app.next_main', '--smoke-test')
    Write-Host 'kurulum tamamlandi. baslat.bat ile acabilirsiniz.'
    Write-Host 'cpu / nvidia / intel / amd kutuphanelerini ve modelleri uygulamanin modeller sayfasindan kurun.'
    exit 0
} catch {
    Write-Host "hata: $_"
    Write-Host 'kurulum tamamlanmadi. internet baglantisini ve .data\logs\source-setup.log dosyasini kontrol edin.'
    exit 1
} finally {
    if ($transcribing) { Stop-Transcript | Out-Null }
}
