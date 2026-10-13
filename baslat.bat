@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Once kurulum.bat dosyasini calistirin.
    pause
    exit /b 1
)
rem Konsol penceresi gorev cubugunda kalmasin; yalnizca mergen gorunsun.
start "" /D "%~dp0" "%~dp0.venv\Scripts\pythonw.exe" -m app.launch_gui
