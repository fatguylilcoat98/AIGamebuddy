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

# The smoke test must not call a system Python. Drop those directories from PATH.
$env:PATH = ((
    $env:PATH -split ';' | Where-Object {
        $_ -and ($_ -notmatch '(?i)\\Python') -and ($_ -notmatch '(?i)Python3')
    }
) -join ';')
$elsewhere = Join-Path $env:TEMP "buddy-launch-not-the-app"
New-Item -ItemType Directory -Force -Path $elsewhere | Out-Null
$check = Join-Path $PSScriptRoot "installed_import_check.py"
Write-Host "Import check with $python from $elsewhere"
Push-Location $elsewhere
try {
    & $python $check
    if ($LASTEXITCODE -ne 0) { throw "runtime\python.exe could not import backend and tkinter from $elsewhere" }
} finally {
    Pop-Location
}

Write-Host "Launching shortcut target $($lnk.TargetPath) from $elsewhere"
$proc = Start-Process -FilePath $lnk.TargetPath -WorkingDirectory $elsewhere -PassThru
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
& $python -c @'
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
Copy-Item $shot (Join-Path $shotDir "wizard-first.jpg") -Force

Stop-Process -Id $pythonPid -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "backend\.wizard_app" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

function Save-Screen([string]$Path) {
    $env:BUDDY_SHOT = $Path
    & $python -c @'
import os
from pathlib import Path
from PIL import ImageGrab
image = ImageGrab.grab()
path = Path(os.environ["BUDDY_SHOT"])
image.convert("RGB").save(path, quality=90)
print(f"shot {path} {image.size}")
'@
    if ($LASTEXITCODE -ne 0) { throw "Could not save $Path" }
}

Write-Host "Preparing RetroArch, Snes9x, and the test ROM"
& $python (Join-Path $PSScriptRoot "snes_prepare.py")
if ($LASTEXITCODE -ne 0) { throw "RetroArch or Snes9x did not install" }
$core = Join-Path $env:LOCALAPPDATA "Buddy\RetroArch\cores\snes9x_libretro.dll"
if (-not (Test-Path $core)) { throw "snes9x_libretro.dll is missing after install" }

$cmdFile = Join-Path $env:LOCALAPPDATA "Buddy\smoke-cmd.txt"
$ackFile = Join-Path $env:LOCALAPPDATA "Buddy\smoke-ack.txt"
$env:BUDDY_SMOKE_CMD = $cmdFile
$env:BUDDY_SMOKE_PLAY = "1"
if (Test-Path $cmdFile) { Remove-Item $cmdFile -Force }
if (Test-Path $ackFile) { Remove-Item $ackFile -Force }

Write-Host "Opening the Play screen"
$play = Start-Process -FilePath $python -ArgumentList @("-m", "backend.wizard_app", "--wizard") -WorkingDirectory $elsewhere -PassThru
$playShot = Join-Path $shotDir "wizard-play.jpg"
$env:BUDDY_WIZARD_SHOT = $playShot
& $python -c @'
import os, time, ctypes
from pathlib import Path
from PIL import ImageGrab
user32 = ctypes.windll.user32
deadline = time.time() + 18
hwnd = 0
while time.time() < deadline:
    hwnd = user32.FindWindowW(None, "Buddy Setup")
    if hwnd:
        break
    time.sleep(0.4)
if not hwnd:
    raise SystemExit("Play screen was not found")
user32.ShowWindow(hwnd, 9)
time.sleep(0.8)
image = ImageGrab.grab()
path = Path(os.environ["BUDDY_WIZARD_SHOT"])
image.convert("RGB").save(path, quality=90)
print(f"play-window hwnd={hwnd} shot={path}")
'@
if ($LASTEXITCODE -ne 0) { throw "Play screen did not appear" }
Write-Host "Play screenshot $playShot"

$deadline = (Get-Date).AddSeconds(90)
$ra = $null
while ((Get-Date) -lt $deadline) {
    $ra = Get-Process -Name "retroarch" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ra) { break }
    Start-Sleep -Seconds 1
}
if (-not $ra) {
    $log = Join-Path $env:LOCALAPPDATA "Buddy\logs\buddy.log"
    if (Test-Path $log) { Get-Content $log -Tail 40 }
    throw "RetroArch did not start with the Super NES test ROM"
}
Start-Sleep -Seconds 8
$gameShot = Join-Path $shotDir "snes-frame-retroarch.jpg"
Save-Screen $gameShot
Write-Host "Frame screenshot $gameShot"

function Send-Smoke([string]$Command) {
    if (Test-Path $ackFile) { Remove-Item $ackFile -Force }
    Set-Content -Path $cmdFile -Value $Command -Encoding ascii
    $limit = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $limit) {
        if (Test-Path $ackFile) {
            $ack = (Get-Content -Raw $ackFile).Trim()
            if ($ack -eq $Command) { return }
        }
        Start-Sleep -Milliseconds 300
    }
    throw "Buddy did not acknowledge $Command"
}

Send-Smoke "open-menu"
Start-Sleep -Seconds 2
$menuShot = Join-Path $shotDir "menu-open.jpg"
Save-Screen $menuShot
Write-Host "Menu screenshot $menuShot"

Send-Smoke "retroarch-menu"
Start-Sleep -Seconds 4
$raShot = Join-Path $shotDir "retroarch-menu.jpg"
Save-Screen $raShot
Write-Host "RetroArch menu screenshot $raShot"

$env:BUDDY_GAME_SHOT = $gameShot
$env:BUDDY_MENU_SHOT = $raShot
& $python -c @'
import os
from PIL import Image
game = Image.open(os.environ["BUDDY_GAME_SHOT"]).convert("RGB")
menu = Image.open(os.environ["BUDDY_MENU_SHOT"]).convert("RGB")
x, y = game.size[0] // 2, game.size[1] // 2
a = game.getpixel((x, y))
b = menu.getpixel((x, y))
delta = sum(abs(a[i] - b[i]) for i in range(3))
print(f"center game={a} menu={b} delta={delta}")
if delta < 30:
    raise SystemExit("RetroArch menu did not change the picture in the Super NES opening")
'@
if ($LASTEXITCODE -ne 0) { throw "RetroArch menu was not visible in the opening" }

Send-Smoke "exit"
$limit = (Get-Date).AddSeconds(25)
$left = @()
do {
    Start-Sleep -Seconds 1
    $left = @(Get-CimInstance Win32_Process | Where-Object {
        $exe = [string]$_.ExecutablePath
        $cmd = [string]$_.CommandLine
        ($exe -like "*\Buddy\runtime\python.exe") -or
        ($cmd -match "backend\.(launcher|wizard_app|overlay_app)") -or
        ($_.Name -eq "retroarch.exe")
    })
    if ($left.Count -eq 0) { break }
} while ((Get-Date) -lt $limit)
if ($left.Count -ne 0) {
    $left | ForEach-Object { Write-Host "still running $($_.Name) $($_.ProcessId) $($_.CommandLine)" }
    throw "Exit to desktop left Buddy or RetroArch running"
}
Write-Host "Exit to desktop left no Buddy or RetroArch process"
Write-Host "Installed launch smoke passed"
