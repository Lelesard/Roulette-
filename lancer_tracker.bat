@echo off
setlocal
cd /d "%~dp0"
if not exist .venv-windows\Scripts\python.exe (
    echo Installation requise. Lancez installer_windows.bat.
    pause
    exit /b 1
)
.venv-windows\Scripts\python.exe tracker_main.py %*
if errorlevel 1 pause
