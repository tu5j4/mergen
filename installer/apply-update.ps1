param([Parameter(Mandatory=$true)][string]$Installer,
      [Parameter(Mandatory=$true)][string]$Sha256,
      [Parameter(Mandatory=$true)][string]$AppDirectory,
      [int]$WaitPid,
      [string]$PackageManifest,
      [string]$ManifestSha256)
$ErrorActionPreference='Stop'
try {
    if ($Sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid package hash' }
    if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ne $Sha256) { throw 'Package hash mismatch' }
    if ($ManifestSha256 -notmatch '^[a-fA-F0-9]{64}$' -or (Get-FileHash -LiteralPath $PackageManifest -Algorithm SHA256).Hash -ne $ManifestSha256) { throw 'Package manifest hash mismatch' }
    $packageDirectory=Split-Path -Parent $Installer
    foreach ($entry in (Get-Content -LiteralPath $PackageManifest -Raw -Encoding utf8 | ConvertFrom-Json)) {
        if ($entry.name -notmatch '^[a-zA-Z0-9_.-]+$' -or $entry.sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Invalid package entry' }
        if ((Get-FileHash -LiteralPath (Join-Path $packageDirectory $entry.name) -Algorithm SHA256).Hash -ne $entry.sha256) { throw 'Package part hash mismatch' }
    }
    if ($WaitPid) { Wait-Process -Id $WaitPid -Timeout 180 -ErrorAction SilentlyContinue }
    if ($WaitPid -and (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue)) { throw 'Application did not close' }
    $arguments=@('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/DIR="'+$AppDirectory+'"'))
    $setup=Start-Process -FilePath $Installer -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($setup.ExitCode -ne 0) { throw "Installer failed: $($setup.ExitCode)" }
    Start-Process -FilePath (Join-Path $AppDirectory 'Mergen.exe') -WindowStyle Hidden
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("Guncelleme tamamlanamadi: $_",'mergen') | Out-Null
}
