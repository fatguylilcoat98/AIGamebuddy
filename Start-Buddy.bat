@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Buddy.ps1"
if errorlevel 1 (
  echo.
  echo Buddy did not start. Read the message above.
  pause
)
