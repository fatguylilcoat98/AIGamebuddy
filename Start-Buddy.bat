@echo off
cd /d "%~dp0"
rem pythonw has no console. Do not start a shell from this file.
if exist "%~dp0runtime\pythonw.exe" (
  start "" "%~dp0runtime\pythonw.exe" -m backend.wizard_app
  exit /b 0
)
start "" wscript //nologo //B "%~dp0Start-Buddy.vbs"
exit /b 0
