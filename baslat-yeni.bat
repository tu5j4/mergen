@echo off
cd /d "%~dp0"
if exist "Mergen.exe" (start "" "Mergen.exe" & exit /b)
if exist "dist\Mergen\Mergen.exe" (start "" "dist\Mergen\Mergen.exe" & exit /b)
if exist "%LOCALAPPDATA%\Programs\mergen\Mergen.exe" (start "" "%LOCALAPPDATA%\Programs\mergen\Mergen.exe" & exit /b)
if exist ".venv\Scripts\pythonw.exe" (start "" ".venv\Scripts\pythonw.exe" main.py & exit /b)
echo mergen kurulu degil. kurulum.bat dosyasini ac veya github releases uzerinden exe dosyasini indir.
pause
