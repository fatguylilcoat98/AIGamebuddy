Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Buddy is not installed yet. Run install.bat first."
    exit 1
}
& $python -m backend.launcher
exit $LASTEXITCODE
