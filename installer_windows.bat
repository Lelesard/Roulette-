@echo off
setlocal
cd /d "%~dp0"
if not exist .venv-windows\Scripts\python.exe (
    py -3.12 -m venv .venv-windows
    if errorlevel 1 py -3.11 -m venv .venv-windows
)
if not exist .venv-windows\Scripts\python.exe (
    echo Installez Python 3.11 ou 3.12 64 bits avec le lanceur py.
    pause
    exit /b 1
)
.venv-windows\Scripts\python.exe -m pip install -r requirements-tracker.txt || exit /b 1
echo Installation terminee. Lancez lancer_tracker.bat.
pause
