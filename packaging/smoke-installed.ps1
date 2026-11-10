# Install the BuddySetup.exe this build just produced, then start it the way a
# desktop shortcut does, from a working directory that is not the app folder.
# Fails unless the setup wizard process and its window actually appear.
$ErrorActionPreference = "Stop"

$setup = Join-Path (Split-Path -Parent $PSScriptRoot) "dist\BuddySetup.exe"
if (-not (Test-Path $setup)) {
    throw "dist\BuddySetup.exe is missing. This smoke test only runs the installer that ships."
}
$setup = (Resolve-Path $setup).Path

$installLog = Join-Path $env:TEMP "buddy-install-smoke.log"
if (Test-Path $installLog) { Remove-Item $installLog -Force }
Write-Host "Installing $setup"
$installer = Start-Process -FilePath $setup -ArgumentList @(
    "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=$installLog"
) -Wait -PassThru
if ($installer.ExitCode -ne 0) {
    if (Test-Path $installLog) { Get-Content $installLog -Tail 40 }
    throw "BuddySetup.exe exited $($installer.ExitCode)"
}

$app = Join-Path $env:LOCALAPPDATA "Buddy"
$bat = Join-Path $app "Start-Buddy.bat"
$python = Join-Path $app "runtime\python.exe"
if (-not (Test-Path $bat)) { throw "Installed copy has no Start-Buddy.bat at $bat" }
if (-not (Test-Path $python)) { throw "Installed copy has no runtime\python.exe" }
if (Test-Path (Join-Path $app "Buddy.exe")) {
    throw "Installed copy contains Buddy.exe. The shipped package starts runtime\python.exe, not that bundle."
}

$pth = Get-ChildItem (Join-Path $app "runtime") -Filter "python*._pth" | Select-Object -First 1
if (-not $pth) { throw "No python*._pth next to the embedded interpreter" }
$pthText = Get-Content -Raw -Path $pth.FullName
Write-Host "---- $($pth.Name) ----"
Write-Host $pthText
if ($pthText -notmatch '(?m)^\.\.\r?$') {
    throw "python ._pth does not list .. so backend cannot be imported"
}

$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "Buddy.lnk"
if (-not (Test-Path $lnkPath)) { throw "Desktop shortcut was not created at $lnkPath" }
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
Write-Host "Shortcut target $($lnk.TargetPath)"
if ($lnk.TargetPath -notlike "*Start-Buddy.bat") {
    throw "Desktop shortcut does not launch Start-Buddy.bat. It launches $($lnk.TargetPath)"
}

$elsewhere = Join-Path $env:TEMP "buddy-launch-not-the-app"
New-Item -ItemType Directory -Force -Path $elsewhere | Out-Null
Push-Location $elsewhere
try {
    & $python -c "import backend.wizard_app, backend.launcher; print('imports-ok')"
    if ($LASTEXITCODE -ne 0) { throw "import backend failed when cwd is $elsewhere" }
} finally {
    Pop-Location
}

Write-Host "Launching $bat from $elsewhere"
$proc = Start-Process -FilePath $bat -WorkingDirectory $elsewhere -PassThru
$deadline = (Get-Date).AddSeconds(45)
$pythonPid = $null
while ((Get-Date) -lt $deadline) {
    $found = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -match "backend\.wizard_app" }
    if ($found) {
        $pythonPid = @($found)[0].ProcessId
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $pythonPid) {
    $startup = Join-Path $env:LOCALAPPDATA "Buddy\logs\startup.log"
    Write-Host "---- startup.log ----"
    if (Test-Path $startup) { Get-Content $startup }
    throw "Start-Buddy.bat did not leave backend.wizard_app running"
}
Write-Host "wizard python pid $pythonPid"

$shotDir = Join-Path (Split-Path -Parent $PSScriptRoot) "dist\screenshots"
New-Item -ItemType Directory -Force -Path $shotDir | Out-Null
$shot = Join-Path $shotDir "wizard-after-install.jpg"
$env:BUDDY_WIZARD_SHOT = $shot
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
& python -c @'
import os, time, ctypes
from pathlib import Path
from PIL import ImageGrab
user32 = ctypes.windll.user32
deadline = time.time() + 20
hwnd = 0
while time.time() < deadline:
    hwnd = user32.FindWindowW(None, "Buddy Setup")
    if hwnd:
        break
    time.sleep(0.5)
if not hwnd:
    raise SystemExit("Buddy Setup window was not found")
user32.ShowWindow(hwnd, 9)
user32.SetForegroundWindow(hwnd)
time.sleep(1)
image = ImageGrab.grab()
path = Path(os.environ["BUDDY_WIZARD_SHOT"])
image.convert("RGB").save(path, quality=90)
print(f"wizard-window hwnd={hwnd} shot={path} size={image.size}")
'@
if ($LASTEXITCODE -ne 0) { throw "Wizard window did not appear" }
if (-not (Test-Path $shot)) { throw "Wizard screenshot was not written" }
Write-Host "Wizard screenshot $shot"

Stop-Process -Id $pythonPid -Force -ErrorAction SilentlyContinue
if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "Installed launch smoke passed"
