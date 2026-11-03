@echo off
setlocal
cd /d "%~dp0"
if not exist .venv-windows\Scripts\python.exe (
    py -3.12 -m venv .venv-windows
    if errorlevel 1 py -3.11 -m venv .venv-windows
)
if not exist .venv-windows\Scripts\python.exe (
    echo Python 3.11 ou 3.12 64 bits est requis.
    exit /b 1
)
.venv-windows\Scripts\python.exe -m pip install -r requirements-tracker.txt || exit /b 1
.venv-windows\Scripts\python.exe -m unittest discover -s tests_tracker -v || exit /b 1
.venv-windows\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name RouletteTracker tracker_main.py || exit /b 1
start "Test de demarrage" /wait "dist\RouletteTracker\RouletteTracker.exe" --smoke-test
if errorlevel 1 exit /b 1
echo Executable : dist\RouletteTracker\RouletteTracker.exe
echo Distribuer tout le dossier dist\RouletteTracker.
