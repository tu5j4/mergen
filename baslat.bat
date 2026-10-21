@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    set "MERGEN_DATA_DIR=%~dp0.data"
    set "PYTHONHOME="
    set "PYTHONPATH="
    set "PYTHONNOUSERSITE=1"
    start "" ".venv\Scripts\pythonw.exe" -m app.next_main
    exit /b
)
if exist "Mergen.exe" (start "" "Mergen.exe" & exit /b)
if exist "dist\Mergen\Mergen.exe" (start "" "dist\Mergen\Mergen.exe" & exit /b)
if exist "%LOCALAPPDATA%\Programs\mergen\Mergen.exe" (start "" "%LOCALAPPDATA%\Programs\mergen\Mergen.exe" & exit /b)
echo uygulama veya gelistirme ortami bulunamadi.
echo once bu klasordeki kurulum.bat dosyasini calistirin.
pause
exit /b 1
