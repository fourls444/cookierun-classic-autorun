@echo off
setlocal
cd /d "%~dp0" || goto :failed

if exist ".venv\Scripts\python.exe" if exist ".venv\Scripts\pythonw.exe" (
    ".venv\Scripts\python.exe" -B -c "import tkinter, numpy, cv2" >nul 2>&1
    if not errorlevel 1 goto :open
)

echo Setting up cookierun-classic-autorun...
if not exist ".venv\Scripts\python.exe" (
    py -3.13 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
    if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -B -c "import tkinter, numpy, cv2"
if errorlevel 1 goto :failed
if not exist ".venv\Scripts\pythonw.exe" goto :failed

:open
where adb.exe >nul 2>&1
if errorlevel 1 (
    echo ADB was not found. Add Android SDK Platform-Tools to your Windows PATH.
    goto :failed
)
start "" ".venv\Scripts\pythonw.exe" -B "desktop_ui.py"
if errorlevel 1 goto :failed
exit /b 0

:failed
echo Could not open the app. Check the setup steps in README.md.
pause
exit /b 1
