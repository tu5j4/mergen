@echo off
setlocal
chcp 65001 >nul
title mergen - kurulum
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\bootstrap.ps1" -Mode install %*
set "result=%errorlevel%"
if not "%result%"=="0" echo kurulum tamamlanamadi. yukaridaki hata mesajini kontrol edin.
pause
exit /b %result%
