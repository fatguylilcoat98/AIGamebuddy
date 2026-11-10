@echo off
cd /d "%~dp0"
rem The window the user sees is Buddy, not a console.
start "" powershell -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Buddy.ps1"
exit /b 0
