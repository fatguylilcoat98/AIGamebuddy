# One double-click. An installed package (runtime\python.exe) opens the wizard until Play,
# then starts Buddy. A source checkout still uses .venv and backend.launcher.
# A startup failure is shown and written to %LOCALAPPDATA%\Buddy\logs. It does not
# download or run the installer again.
$ErrorActionPreference = "Stop"

$logDir = Join-Path $env:LOCALAPPDATA "Buddy\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "startup.log"

function Write-StartupError([string]$Message) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $text = "$stamp`r`n$Message"
    Add-Content -Path $logFile -Value $text -Encoding utf8
    Write-Host $Message
    Write-Host "Wrote $logFile"
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "$Message`r`n`r`nThis was written to:`r`n$logFile",
            "Buddy did not start",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    } catch {
        Write-Host "Could not show a dialog: $_"
    }
}

Set-Location $PSScriptRoot

$embedded = Join-Path $PSScriptRoot "runtime\python.exe"
if (Test-Path $embedded) {
    $output = & $embedded -m backend.wizard_app 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        $detail = (($output | Out-String).Trim())
        if (-not $detail) { $detail = "runtime\python.exe exited with code $code" }
        Write-StartupError $detail
        exit $code
    }
    exit 0
}

$requirements = Join-Path $PSScriptRoot "backend\requirements.txt"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$stamp = Join-Path $PSScriptRoot ".venv\requirements.sha256"

if (-not (Test-Path $requirements)) {
    Write-StartupError "backend\requirements.txt is missing, so Buddy cannot install."
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
        Write-StartupError "Install did not finish, so Buddy did not start. Exit code $LASTEXITCODE."
        exit $LASTEXITCODE
    }
}

$output = & $python -m backend.launcher 2>&1
$code = $LASTEXITCODE
if ($code -ne 0) {
    $detail = (($output | Out-String).Trim())
    if (-not $detail) { $detail = "python.exe exited with code $code" }
    Write-StartupError $detail
    exit $code
}
exit 0
