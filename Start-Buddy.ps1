# One double-click. Installs when .venv is missing or requirements.txt changed, then starts Buddy.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$requirements = Join-Path $PSScriptRoot "backend\requirements.txt"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$stamp = Join-Path $PSScriptRoot ".venv\requirements.sha256"

if (-not (Test-Path $requirements)) {
    Write-Host "backend\requirements.txt is missing, so Buddy cannot install."
    exit 1
}

$current = (Get-FileHash -Algorithm SHA256 -Path $requirements).Hash
$saved = ""
if (Test-Path $stamp) {
    $saved = (Get-Content -Raw -Path $stamp).Trim()
}

$needsInstall = (-not (Test-Path $python)) -or ($current -ne $saved)
if ($needsInstall) {
    if (-not (Test-Path $python)) {
        Write-Host "No install yet. Setting up Buddy..."
    } else {
        Write-Host "backend\requirements.txt changed. Updating Buddy..."
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "install.ps1")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Install did not finish, so Buddy did not start."
        exit $LASTEXITCODE
    }
}

& $python -m backend.launcher
exit $LASTEXITCODE
