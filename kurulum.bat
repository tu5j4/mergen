@echo off
setlocal
cd /d "%~dp0"
title mergen - kaynak kurulumu
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\setup_source.ps1" %*
set "result=%errorlevel%"
if not "%result%"=="0" echo kurulum tamamlanamadi. yukaridaki hata mesajini kontrol edin.
pause
exit /b %result%
