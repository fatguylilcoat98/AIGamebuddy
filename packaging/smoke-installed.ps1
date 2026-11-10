# Install the BuddySetup.exe this build just produced, then start it the way a
# desktop shortcut does, from a working directory that is not the app folder.
# Fails unless the setup wizard process and its window actually appear.
$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class BuddyScreen {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    public struct DEVMODE {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmDeviceName;
        public short dmSpecVersion;
        public short dmDriverVersion;
        public short dmSize;
        public short dmDriverExtra;
        public int dmFields;
        public int dmPositionX;
        public int dmPositionY;
        public int dmDisplayOrientation;
        public int dmDisplayFixedOutput;
        public short dmColor;
        public short dmDuplex;
        public short dmYResolution;
        public short dmTTOption;
        public short dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmFormName;
        public short dmLogPixels;
        public int dmBitsPerPel;
        public int dmPelsWidth;
        public int dmPelsHeight;
        public int dmDisplayFlags;
        public int dmDisplayFrequency;
    }
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern int ChangeDisplaySettings(ref DEVMODE devMode, int flags);
}
"@
$mode = New-Object BuddyScreen+DEVMODE
$mode.dmSize = [Runtime.InteropServices.Marshal]::SizeOf($mode)
$mode.dmPelsWidth = 1920
$mode.dmPelsHeight = 1080
$mode.dmBitsPerPel = 32
$mode.dmFields = 0x1C0000
$displayCode = [BuddyScreen]::ChangeDisplaySettings([ref]$mode, 0)
Write-Host "ChangeDisplaySettings 1920x1080 -> $displayCode"
Add-Type -AssemblyName System.Windows.Forms
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
Write-Host "Primary screen $($bounds.Width)x$($bounds.Height)"
if ($bounds.Width -lt 1600 -or $bounds.Height -lt 900) {
    throw "The runner display is $($bounds.Width)x$($bounds.Height). Buddy's pixel check needs about 1920x1080."
}

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
$pythonw = Join-Path $app "runtime\pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "Installed copy has no runtime\pythonw.exe" }
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
    $found = Get-CimInstance Win32_Process |
        Where-Object {
            $_.ExecutablePath -like "*\Buddy\runtime\pythonw.exe" -or
            ($_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -match "backend\.wizard_app")
        }
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
$smokePy = Join-Path $PSScriptRoot "smoke_windows.py"
$env:BUDDY_SHOT = $shot
$env:BUDDY_WINDOW_TITLE = "Buddy Setup"
$env:BUDDY_WINDOW_TIMEOUT = "20"
& $python $smokePy window
if ($LASTEXITCODE -ne 0) { throw "Wizard window did not appear" }
if (-not (Test-Path $shot)) { throw "Wizard screenshot was not written" }
Write-Host "Wizard screenshot $shot"
Copy-Item $shot (Join-Path $shotDir "wizard-first.jpg") -Force

$env:BUDDY_WINDOW_TITLE = "Buddy Setup"
& $python $smokePy close
$closeDeadline = (Get-Date).AddSeconds(15)
while ((Get-Date) -lt $closeDeadline) {
    $still = Get-CimInstance Win32_Process |
        Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -match "backend\.wizard_app" }
    if (-not $still) { break }
    Start-Sleep -Milliseconds 400
}
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "backend\.wizard_app" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

function Save-Screen([string]$Path) {
    $env:BUDDY_SHOT = $Path
    & $python $smokePy grab
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
$play = Start-Process -FilePath $pythonw -ArgumentList @("-m", "backend.wizard_app", "--wizard") -WorkingDirectory $elsewhere -WindowStyle Hidden -PassThru
$playShot = Join-Path $shotDir "wizard-play.jpg"
$env:BUDDY_SHOT = $playShot
$env:BUDDY_WINDOW_TITLE = "Buddy Setup"
$env:BUDDY_WINDOW_TIMEOUT = "18"
& $python $smokePy window
if ($LASTEXITCODE -ne 0) { throw "Play screen did not appear" }
Write-Host "Play screenshot $playShot"

$deadline = (Get-Date).AddSeconds(90)
$ra = $null
while ((Get-Date) -lt $deadline) {
    $ra = Get-Process -Name "retroarch" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ra) { break }
    Start-Sleep -Seconds 1
}
function Write-BuddyLogs {
    foreach ($log in @(
        (Join-Path $env:LOCALAPPDATA "Buddy\logs\buddy.log"),
        (Join-Path $env:LOCALAPPDATA "Buddy\logs\startup.log"),
        (Join-Path $env:LOCALAPPDATA "VideoGameWingman\buddy.log")
    )) {
        if (Test-Path $log) {
            Write-Host "---- $log ----"
            Get-Content $log -Tail 50
        }
    }
}
if (-not $ra) {
    Write-BuddyLogs
    throw "RetroArch did not start with the Super NES test ROM"
}
Start-Sleep -Seconds 12
$env:BUDDY_FRAME_SHOT = "1"
$gameShot = Join-Path $shotDir "snes-frame-retroarch.jpg"
Save-Screen $gameShot
Write-Host "Frame screenshot $gameShot"
$env:BUDDY_SHOT = $gameShot
$env:BUDDY_MENU_OPEN = "0"
$env:BUDDY_EXPECT_GAME = "1"
& $python $smokePy prove
$env:BUDDY_EXPECT_GAME = "0"
if ($LASTEXITCODE -ne 0) {
    Write-BuddyLogs
    throw "The SNES frame, Buddy, or the hamburger is not on screen"
}

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

Send-Smoke "pose-talk"
Start-Sleep -Seconds 2
$talkShot = Join-Path $shotDir "buddy-talk.jpg"
Save-Screen $talkShot
Write-Host "Talk pose screenshot $talkShot"
Send-Smoke "pose-rest"
Start-Sleep -Seconds 1

Send-Smoke "open-menu"
Start-Sleep -Seconds 2
$menuShot = Join-Path $shotDir "menu-open.jpg"
Save-Screen $menuShot
Write-Host "Menu screenshot $menuShot"
$env:BUDDY_SHOT = $menuShot
$env:BUDDY_MENU_OPEN = "1"
& $python $smokePy prove
if ($LASTEXITCODE -ne 0) {
    Write-BuddyLogs
    throw "The menu panel is not visible over the SNES frame"
}

Send-Smoke "scroll-menu"
Start-Sleep -Seconds 1
$bottomShot = Join-Path $shotDir "menu-bottom.jpg"
Save-Screen $bottomShot
Write-Host "Menu bottom screenshot $bottomShot"
$env:BUDDY_SHOT = $bottomShot
$env:BUDDY_MENU_OPEN = "0"
$env:BUDDY_MENU_BOTTOM = "1"
& $python $smokePy prove
if ($LASTEXITCODE -ne 0) {
    Write-BuddyLogs
    throw "The menu does not reach Exit to desktop"
}

Send-Smoke "retroarch-menu"
Start-Sleep -Seconds 4
$raShot = Join-Path $shotDir "retroarch-menu.jpg"
Save-Screen $raShot
Write-Host "RetroArch menu screenshot $raShot"

$env:BUDDY_GAME_SHOT = $gameShot
$env:BUDDY_MENU_SHOT = $raShot
& $python $smokePy compare
if ($LASTEXITCODE -ne 0) {
    Write-BuddyLogs
    throw "RetroArch menu was not visible in the opening"
}

Send-Smoke "exit"
$limit = (Get-Date).AddSeconds(25)
$left = @()
do {
    Start-Sleep -Seconds 1
    $left = @(Get-CimInstance Win32_Process | Where-Object {
        $exe = [string]$_.ExecutablePath
        $cmd = [string]$_.CommandLine
        ($exe -like "*\Buddy\runtime\python.exe") -or
        ($exe -like "*\Buddy\runtime\pythonw.exe") -or
        ($cmd -match "backend\.(launcher|wizard_app|overlay_app)") -or
        ($_.Name -eq "retroarch.exe")
    })
    if ($left.Count -eq 0) { break }
} while ((Get-Date) -lt $limit)
if ($left.Count -ne 0) {
    $left | ForEach-Object { Write-Host "still running $($_.Name) $($_.ProcessId) $($_.CommandLine)" }
    throw "Exit to desktop left Buddy or RetroArch running"
}
$proof = Join-Path $shotDir "exit-no-processes.txt"
@(
    "Exit to desktop left no Buddy python process and no retroarch.exe."
    "Checked: runtime\python.exe, backend.launcher, backend.wizard_app, backend.overlay_app, retroarch.exe."
    (Get-Date).ToUniversalTime().ToString("o")
) | Set-Content -Path $proof -Encoding utf8
Write-Host "Exit to desktop left no Buddy or RetroArch process"
Write-Host "Installed launch smoke passed"
