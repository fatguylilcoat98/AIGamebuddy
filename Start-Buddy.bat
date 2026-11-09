@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Buddy is not installed yet. Double-click install.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m backend.launcher
if errorlevel 1 (
  echo.
  echo Buddy stopped because of an error. The message above is the reason.
  pause
)
