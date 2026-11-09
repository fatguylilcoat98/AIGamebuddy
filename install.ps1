# Install Buddy on Windows. Double-click install.bat if you do not use PowerShell.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$launcher = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $launcher = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $launcher = "python"
} else {
    Write-Host "Python 3.11 or newer is not installed."
    Write-Host "Install it from https://www.python.org/downloads/windows/ and check Add python.exe to PATH."
    exit 1
}

if ($launcher -eq "py") {
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) { Write-Host "Buddy needs Python 3.11 or newer."; exit 1 }
    py -3 -m venv .venv
} else {
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) { Write-Host "Buddy needs Python 3.11 or newer."; exit 1 }
    python -m venv .venv
}

$venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $venv -m pip install --upgrade pip
& $venv -m pip install -r (Join-Path $PSScriptRoot "backend\requirements.txt")
$config = Join-Path $PSScriptRoot "config\buddy.config.json"
if (-not (Test-Path $config)) {
    Copy-Item (Join-Path $PSScriptRoot "config\buddy.config.sample.json") $config
    Write-Host "Created config\buddy.config.json from the sample."
}
Write-Host ""
Write-Host "Installed."
Write-Host "1. Edit config\buddy.config.json if you want Ollama or your emulator paths."
Write-Host "2. Put API keys in Windows environment variables, not in the config file."
Write-Host "3. Double-click Start-Buddy.bat"
