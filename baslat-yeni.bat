@echo off
cd /d "%~dp0"
if exist "Mergen.exe" (start "" "Mergen.exe" & exit /b)
if exist "dist\Mergen\Mergen.exe" (start "" "dist\Mergen\Mergen.exe" & exit /b)
if exist ".venv\Scripts\pythonw.exe" (start "" ".venv\Scripts\pythonw.exe" -m app.next_main & exit /b)
echo Gelistirme icin Python ortami gerekli. Kurulum programini kullanin.
pause
