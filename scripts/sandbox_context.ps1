param([string]$InputRoot = 'C:\mergen-input', [string]$ResultsRoot = 'C:\mergen-results')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$workRoot = Join-Path $env:USERPROFILE 'mergen-test'
New-Item -ItemType Directory -Path $workRoot,$ResultsRoot -Force | Out-Null
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:MERGEN_DATA_DIR = Join-Path $workRoot '.data'
$transcript = $false
function Invoke-TestStep([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "test adimi basarisiz: $Program (kod $LASTEXITCODE)" }
}
function Test-Status([string]$State, [string]$Phase, [string]$Detail = '') {
    @{state=$State;phase=$Phase;detail=$Detail;updated=(Get-Date).ToString('o')} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ResultsRoot 'status.json') -Encoding UTF8
}
try {
    Start-Transcript -Path (Join-Path $ResultsRoot 'sandbox.log') -Append | Out-Null
    $transcript = $true
    Test-Status 'running' 'kaynak kopyalaniyor'
    Copy-Item -LiteralPath (Join-Path $InputRoot 'source') -Destination (Join-Path $workRoot 'source') -Recurse
    $sourceRoot = Join-Path $workRoot 'source'
    Set-Location -LiteralPath $sourceRoot
    # Source setup owns its .data folder. Keep the test under that same root.
    $env:MERGEN_DATA_DIR = Join-Path $sourceRoot '.data'
    Test-Status 'running' 'python ve arayuz kuruluyor'
    Invoke-TestStep 'powershell.exe' @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $sourceRoot 'installer\setup_source.ps1'))
    $guiPython = Join-Path $sourceRoot '.venv\Scripts\python.exe'
    $basePython = Join-Path $sourceRoot '.data\python\python.exe'
    $evalRoot = Join-Path $sourceRoot '.data\envs\context-eval'
    Test-Status 'running' 'baglam testi icin ayri ortam kuruluyor'
    Invoke-TestStep $basePython @('-m','venv',$evalRoot)
    $evalPython = Join-Path $evalRoot 'Scripts\python.exe'
    Invoke-TestStep $evalPython @('-m','pip','install','--upgrade','pip')
    Invoke-TestStep $evalPython @('-m','pip','install','torch==2.11.0','--index-url','https://download.pytorch.org/whl/cpu')
    Invoke-TestStep $evalPython @('-m','pip','install','transformers==5.19.0','ctranslate2==4.8.2','sentencepiece==0.2.2','huggingface_hub','psutil','numpy')
    Invoke-TestStep $evalPython @('-m','pip','check')
    Test-Status 'running' 'guncel uygulama aciliyor'
    $env:QT_QUICK_BACKEND = 'software'
    # The real GUI is interactive; its ordinary model components remain managed
    # by its models page. The benchmark itself exercises translation without OCR.
    $gui = Start-Process -FilePath $guiPython -ArgumentList @('-m','app.next_main') -WorkingDirectory $sourceRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $ResultsRoot 'gui.log') -RedirectStandardError (Join-Path $ResultsRoot 'gui-error.log')
    Start-Sleep -Seconds 3
    if ($gui.HasExited) { throw 'uygulama acilamadi; gui-error.log dosyasina bakin.' }
    Test-Status 'running' 'qwen 0.6b ve nllb gercek cpu testi'
    Invoke-TestStep $evalPython @((Join-Path $sourceRoot 'scripts\benchmark_context.py'),(Join-Path $InputRoot 'cases.json'),$ResultsRoot)
    Test-Status 'complete' 'karsilastirma raporu hazir'
    # Shell association opens the requested interactive report in the sandbox.
    Invoke-Item -LiteralPath (Join-Path $ResultsRoot 'rapor.html')
} catch {
    Test-Status 'failed' 'test tamamlanamadi' ([string]$_)
    Write-Host "hata: $_"
} finally {
    if ($transcript) { Stop-Transcript | Out-Null }
}
