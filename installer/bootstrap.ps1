# Compatibility entry point; kurulum.bat owns source installation.
param([ValidateSet('install','menu','scan')][string]$Mode = 'install',
      [string]$Components = '', [switch]$AcceptInstall)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    if ($Components -or $AcceptInstall -or $Mode -ne 'install') {
        throw 'eski bilesen yoneticisi kaldirildi. kaynak kurulumu icin kurulum.bat dosyasini acin; bilesenleri uygulamanin bagimliliklar ekranindan yonetin.'
    }
    Write-Host 'kaynak kurulumu kurulum.bat ile ayni kurulum yoluna yonlendiriliyor...'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'setup_source.ps1')
    exit $LASTEXITCODE
} catch {
    Write-Host "hata: $_"
    exit 1
}