@echo off
setlocal
chcp 65001 >nul
title mergen - bagimliliklar
cd /d "%~dp0program\"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0program\installer\bootstrap.ps1" -Mode menu
set "result=%errorlevel%"
if not "%result%"=="0" echo islem tamamlanamadi. yukaridaki hata mesajini kontrol edin.
pause
exit /b %result%
