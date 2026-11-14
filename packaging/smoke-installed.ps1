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

function Install-BuddySetup([string]$Path) {
    $installLog = Join-Path $env:TEMP "buddy-install-smoke.log"
    if (Test-Path $installLog) { Remove-Item $installLog -Force }
    Write-Host "Installing $Path"
    $installer = Start-Process -FilePath $Path -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=$installLog"
    ) -Wait -PassThru
    if ($installer.ExitCode -ne 0) {
        if (Test-Path $installLog) { Get-Content $installLog -Tail 40 }
        throw "BuddySetup.exe exited $($installer.ExitCode)"
    }
}

function Stop-BuddyProcesses {
    Get-CimInstance Win32_Process | Where-Object {
        $exe = [string]$_.ExecutablePath
        $cmd = [string]$_.CommandLine
        ($exe -like "*\Buddy\*") -or ($cmd -match "backend\.(launcher|wizard_app|overlay_app)") -or ($_.Name -eq "retroarch.exe")
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

# Install the previous prerelease first, leave its data in place, then install this build over it.
$pre10 = Join-Path $env:TEMP "BuddySetup-pre10.exe"
Write-Host "Downloading pre10"
$pre10Url = "https://github.com/fatguylilcoat98/AIGamebuddy/releases/download/buddy-v0.1.0-pre10/BuddySetup.exe"
& curl.exe -L --fail --retry 8 --retry-all-errors --retry-delay 5 -o $pre10 $pre10Url
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $pre10)) { throw "Could not download the pre10 installer" }
Install-BuddySetup $pre10
$staleDir = Join-Path $env:LOCALAPPDATA "VideoGameWingman"
New-Item -ItemType Directory -Force -Path $staleDir | Out-Null
# The old build remembered a Genesis frame. This file is what an upgrade has to replace.
'{"theme":"genesis","theme_mode":"genesis","volume":70}' | Set-Content -Path (Join-Path $staleDir "ui-state.json") -Encoding ascii
$stamp = Join-Path $staleDir "frame-revision.txt"
if (Test-Path $stamp) { Remove-Item $stamp -Force }
Stop-BuddyProcesses

$setup = Join-Path (Split-Path -Parent $PSScriptRoot) "dist\BuddySetup.exe"
if (-not (Test-Path $setup)) {
    throw "dist\BuddySetup.exe is missing. This smoke test only runs the installer that ships."
}
$setup = (Resolve-Path $setup).Path

Install-BuddySetup $setup

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
Write-Host "Shortcut target $($lnk.TargetPath) $($lnk.Arguments)"
if ($lnk.TargetPath -notlike "*pythonw.exe") {
    throw "Desktop shortcut does not launch pythonw.exe. It launches $($lnk.TargetPath)"
}
if ($lnk.Arguments -notmatch "backend\.wizard_app") {
    throw "Desktop shortcut does not start the wizard. Arguments: $($lnk.Arguments)"
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

Write-Host "Launching shortcut target $($lnk.TargetPath) $($lnk.Arguments) from $elsewhere"
$shortcutArgs = @()
if ($lnk.Arguments) { $shortcutArgs = $lnk.Arguments -split '\s+' }
$proc = Start-Process -FilePath $lnk.TargetPath -ArgumentList $shortcutArgs -WorkingDirectory $elsewhere -PassThru
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
    throw "pythonw did not leave backend.wizard_app running"
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
$env:BUDDY_LOOK_SECONDS = "5"
$env:BUDDY_SMOKE_CHATTY = "1"
$env:BUDDY_FRAME_SCRIPT = Join-Path $PSScriptRoot "follow-frames.txt"
$env:BUDDY_SAVE_LOG = Join-Path $shotDir "save-roundtrip.txt"
if (Test-Path $cmdFile) { Remove-Item $cmdFile -Force }
if (Test-Path $ackFile) { Remove-Item $ackFile -Force }

# An upgraded PC keeps yesterday's config. A missing device name must not crash Buddy.
$oldCfg = Join-Path $app "config\buddy.config.json"
New-Item -ItemType Directory -Force -Path (Split-Path $oldCfg) | Out-Null
@'
{
  "character_name": "Buddy",
  "personality": "sassy",
  "commentary": {"frequency": "chatty", "look_interval_seconds": 5, "cooldown_seconds": 8},
  "voice": {"enabled": true, "volume": 70, "rate": 0, "output_device": "Speakers (Realtek Audio)", "mute": false},
  "vision": {"enabled": false, "provider": "none"},
  "wake_word": true,
  "provider": "offline"
}
'@ | Set-Content -Path $oldCfg -Encoding ascii
Write-Host "Planted an old config at $oldCfg"
$repo = Split-Path $PSScriptRoot -Parent
$brainPortFile = Join-Path $shotDir "brain-port.txt"
$brainReport = Join-Path $shotDir "brain-report.txt"
if (Test-Path $brainPortFile) { Remove-Item $brainPortFile -Force }
if (Test-Path $brainReport) { Remove-Item $brainReport -Force }
$brainProc = Start-Process -FilePath $pythonw -ArgumentList @("-m", "backend.fake_brain", "--port-file", $brainPortFile, "--report", $brainReport) -WorkingDirectory $repo -WindowStyle Hidden -PassThru
$brainWait = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $brainWait -and -not (Test-Path $brainPortFile)) { Start-Sleep -Milliseconds 200 }
if (-not (Test-Path $brainPortFile)) { throw "The fake brain did not start" }
$brainPort = (Get-Content -Raw $brainPortFile).Trim()
$roamingBrain = Join-Path $env:APPDATA "Buddy"
New-Item -ItemType Directory -Force -Path $roamingBrain | Out-Null
@"
{
  "url": "ws://127.0.0.1:$brainPort",
  "token": "ci-buddy-token"
}
"@ | Set-Content -Path (Join-Path $roamingBrain "brain.json") -Encoding ascii
Write-Host "Fake brain is on port $brainPort"
$spokenEarly = Join-Path $env:LOCALAPPDATA "VideoGameWingman\spoken.log"
if (Test-Path $spokenEarly) { Remove-Item $spokenEarly -Force }

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
    if (Test-Path $spokenEarly) {
        $early = Get-Content -Raw $spokenEarly
        if ($early -and $early.Trim().Length -gt 0) {
            throw "Buddy spoke before the game was visible: $early"
        }
    }
    Start-Sleep -Seconds 1
}
function Write-BuddyLogs {
    foreach ($log in @(
        (Join-Path $env:LOCALAPPDATA "Buddy\logs\buddy.log"),
        (Join-Path $env:LOCALAPPDATA "Buddy\logs\crash.log"),
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

Send-Smoke "snap"
Start-Sleep -Seconds 1
$env:BUDDY_FRAME_SHOT = "1"
$gameShot = Join-Path $shotDir "snes-frame-retroarch.jpg"
Save-Screen $gameShot
Copy-Item $gameShot (Join-Path $shotDir "upgrade-first-launch.jpg") -Force
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

Write-Host "Listening for three minutes of frame comments"
$consoleHits = New-Object System.Collections.Generic.List[string]
$listenUntil = (Get-Date).AddSeconds(185)
while ((Get-Date) -lt $listenUntil) {
    & $python $smokePy consoles
    if ($LASTEXITCODE -ne 0) { $consoleHits.Add("console") }
    Start-Sleep -Seconds 5
}
if ($consoleHits.Count -gt 0) {
    throw "A Buddy console window appeared during play"
}
$launcherAlive = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "backend\.launcher" }
if (-not $launcherAlive) { throw "Buddy's launcher is not running after three minutes" }
$startupLog = Join-Path $env:LOCALAPPDATA "Buddy\logs\startup.log"
if ((Test-Path $startupLog) -and (Select-String -Path $startupLog -Pattern "-1073741819" -Quiet)) {
    throw "pythonw crashed with an access violation during the three minutes"
}
$buddyLog = Join-Path $env:LOCALAPPDATA "Buddy\logs\buddy.log"
$crashLog = Join-Path $env:LOCALAPPDATA "Buddy\logs\crash.log"
if (-not (Test-Path $buddyLog)) { throw "buddy.log was not written" }
if (-not (Test-Path $crashLog)) { throw "crash.log was not written" }
if (Select-String -Path $crashLog -Pattern "access violation" -Quiet) {
    Get-Content $crashLog -Tail 40
    throw "crash.log has an access violation"
}
if (-not (Select-String -Path $buddyLog -Pattern "startup:" -Quiet)) {
    throw "buddy.log has no startup record"
}
$spoken = Join-Path $env:LOCALAPPDATA "VideoGameWingman\spoken.log"
if (-not (Test-Path $spoken)) { New-Item -ItemType File -Path $spoken -Force | Out-Null }
if (Select-String -Path $spoken -Pattern "missed that screen" -Quiet) {
    Get-Content $spoken
    throw "The missed-screen fallback was spoken"
}
$linesFile = Join-Path $shotDir "buddy-lines.txt"
Copy-Item $spoken $linesFile -Force
if ((Get-Item $linesFile).Length -lt 1) {
    Set-Content -Path $linesFile -Value "silent: local speech stayed quiet" -Encoding ascii
}
if (Select-String -Path $buddyLog -Pattern "WNDCLASSW" -Quiet) {
    throw "The blue backing failed: WNDCLASSW is in buddy.log"
}
if (Select-String -Path $buddyLog -Pattern "Game fit: wide" -Quiet) {
    Write-Host "Wide layout skips the blue backing"
} elseif (-not (Select-String -Path $buddyLog -Pattern "Blue backing is up" -Quiet)) {
    throw "The blue backing was not created"
}
$launches = @(Select-String -Path $buddyLog -Pattern "Launching RetroArch:").Count
if ($launches -gt 1) { throw "RetroArch was launched $launches times" }
$misses = @(Select-String -Path $buddyLog -Pattern "GET_STATUS got no reply").Count
if ($misses -gt 6) { throw "GET_STATUS is still logging every poll ($misses)" }
if (-not (Select-String -Path $buddyLog -Pattern "Brain connected" -Quiet)) {
    throw "The fake brain never connected"
}
if (-not (Select-String -Path $buddyLog -Pattern "Queued reply audio" -Quiet)) {
    throw "Reply audio was not queued"
}
if (-not (Select-String -Path $buddyLog -Pattern "Brain barge-in" -Quiet)) {
    throw "Barge-in was not exercised"
}
if (-not (Select-String -Path $buddyLog -Pattern "Play on seq=" -Quiet)) {
    throw "Buddy did not report playback starting"
}
if (-not (Test-Path $brainReport)) { throw "The fake brain wrote no report" }
$report = Get-Content -Raw $brainReport | ConvertFrom-Json
if ($report.images -lt 1 -or $report.clips -lt 3 -or -not $report.barge -or -not $report.resumed) {
    throw "The fake brain did not finish the audio path: $report"
}
$env:BUDDY_EXPECT_SILENT = "1"
$env:BUDDY_LINES = Join-Path $shotDir "buddy-lines.txt"
& $python $smokePy lines
if ($LASTEXITCODE -ne 0) {
    Get-Content (Join-Path $shotDir "buddy-lines.txt")
    throw "Buddy spoke on his own during the fake-brain run"
}
$env:BUDDY_REPEAT_OUT = Join-Path $shotDir "repetition.txt"
& $python $smokePy repeats
if ($LASTEXITCODE -ne 0) {
    Get-Content (Join-Path $shotDir "buddy-lines.txt")
    throw "Buddy repeated himself"
}
$env:BUDDY_ATTITUDES = Join-Path $shotDir "attitudes.txt"
& $python $smokePy attitudes
if ($LASTEXITCODE -ne 0) { throw "The three attitudes did not sound different" }

Send-Smoke "snap"
Start-Sleep -Milliseconds 500
Send-Smoke "pose-talk"
Start-Sleep -Seconds 2
$talkShot = Join-Path $shotDir "buddy-talk.jpg"
Save-Screen $talkShot
Write-Host "Talk pose screenshot $talkShot"
$env:BUDDY_SHOT = $talkShot
$env:BUDDY_MENU_OPEN = "0"
$env:BUDDY_MENU_BOTTOM = "0"
$env:BUDDY_EXPECT_GAME = "1"
& $python $smokePy prove
$env:BUDDY_EXPECT_GAME = "0"
if ($LASTEXITCODE -ne 0) {
    Write-BuddyLogs
    throw "The talking pose still shows a menu bar, wallpaper, or a flat menu button"
}
Send-Smoke "pose-rest"
Start-Sleep -Seconds 1

Send-Smoke "snap"
Start-Sleep -Milliseconds 500
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

Send-Smoke "scroll-scan"
Start-Sleep -Seconds 1
$scanShot = Join-Path $shotDir "menu-scan.jpg"
Save-Screen $scanShot
Write-Host "Scan timer screenshot $scanShot"
$env:BUDDY_SHOT = $scanShot
$env:BUDDY_MENU_OPEN = "1"
$env:BUDDY_MENU_BOTTOM = "0"
& $python $smokePy prove
if ($LASTEXITCODE -ne 0) {
    Write-BuddyLogs
    throw "How often Buddy looks is not on screen, or the opening has a menu bar or wallpaper"
}

Send-Smoke "scroll-saves"
Start-Sleep -Seconds 1
$savesShot = Join-Path $shotDir "menu-saves.jpg"
Save-Screen $savesShot
Write-Host "Save menu screenshot $savesShot"
$env:BUDDY_SHOT = $savesShot
$env:BUDDY_MENU_OPEN = "1"
$env:BUDDY_MENU_BOTTOM = "0"
& $python $smokePy prove
if ($LASTEXITCODE -ne 0) {
    Write-BuddyLogs
    throw "Save my spot is not on screen, or the opening has a menu bar or wallpaper"
}

Send-Smoke "save-load"
Start-Sleep -Seconds 1
$toastShot = Join-Path $shotDir "save-toast.jpg"
Save-Screen $toastShot
Write-Host "Save toast screenshot $toastShot"
$roundtrip = Join-Path $shotDir "save-roundtrip.txt"
if (-not (Test-Path $roundtrip)) { throw "save-roundtrip.txt was not written" }
$roundtripText = Get-Content -Raw $roundtrip
Write-Host $roundtripText
if ($roundtripText -notmatch "save_ok=True" -or $roundtripText -notmatch "load_ok=True") {
    throw "Save and load did not both succeed"
}
$env:BUDDY_SHOT = $toastShot
$env:BUDDY_MENU_OPEN = "0"
& $python $smokePy prove
if ($LASTEXITCODE -ne 0) {
    Write-BuddyLogs
    throw "The save toast shot still has a menu bar, wallpaper, or a flat menu button"
}

Send-Smoke "scroll-menu"
Start-Sleep -Seconds 2
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

# A higher mode and a 150% pass are recorded. Neither one fails the build.
$dpiLog = New-Object System.Collections.Generic.List[string]
function Set-BuddyMode([int]$Width, [int]$Height) {
    $mode.dmPelsWidth = $Width
    $mode.dmPelsHeight = $Height
    $mode.dmBitsPerPel = 32
    $mode.dmFields = 0x1C0000
    $code = [BuddyScreen]::ChangeDisplaySettings([ref]$mode, 0)
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    Write-Host "ChangeDisplaySettings ${Width}x${Height} -> $code now $($bounds.Width)x$($bounds.Height)"
    return ($bounds.Width -eq $Width -and $bounds.Height -eq $Height)
}
function Start-BuddyFrameShot([string]$Path) {
    Stop-BuddyProcesses
    Start-Sleep -Seconds 2
    if (Test-Path $cmdFile) { Remove-Item $cmdFile -Force }
    if (Test-Path $ackFile) { Remove-Item $ackFile -Force }
    Start-Process -FilePath $pythonw -ArgumentList @("-m", "backend.wizard_app", "--wizard") -WorkingDirectory $elsewhere -WindowStyle Hidden | Out-Null
    $deadline = (Get-Date).AddSeconds(120)
    $ra = $null
    while ((Get-Date) -lt $deadline) {
        $ra = Get-Process -Name "retroarch" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($ra) { break }
        Start-Sleep -Seconds 1
    }
    if (-not $ra) { throw "RetroArch did not start for $Path" }
    Start-Sleep -Seconds 12
    Send-Smoke "snap"
    Start-Sleep -Seconds 1
    Save-Screen $Path
    Send-Smoke "exit"
}

try {
    $vddZip = Join-Path $env:TEMP "usbmmidd_v2.zip"
    $vddRoot = Join-Path $env:TEMP "usbmmidd"
    New-Item -ItemType Directory -Force -Path $vddRoot | Out-Null
    & curl.exe -L --fail --retry 3 --retry-all-errors --retry-delay 2 -o $vddZip "https://amyuni.com/downloads/usbmmidd_v2.zip"
    if ($LASTEXITCODE -eq 0) {
        Expand-Archive -Path $vddZip -DestinationPath $vddRoot -Force
        $vddInstaller = Get-ChildItem $vddRoot -Recurse -Filter "deviceinstaller64.exe" | Select-Object -First 1
        $vddInf = Get-ChildItem $vddRoot -Recurse -Filter "usbmmidd.inf" | Select-Object -First 1
        if ($vddInstaller -and $vddInf) {
            & $vddInstaller.FullName install $vddInf.FullName usbmmidd
            & $vddInstaller.FullName enableidd 1
            Start-Sleep -Seconds 3
            $dpiLog.Add("virtual_display=installed")
        } else {
            $dpiLog.Add("virtual_display=archive_missing_installer")
        }
    } else {
        $dpiLog.Add("virtual_display=download_failed")
    }
} catch {
    $dpiLog.Add("virtual_display=skipped $($_.Exception.Message)")
}

$high = $null
foreach ($candidate in @(@(3840, 2160), @(2560, 1440), @(2560, 1600), @(1920, 1200))) {
    if (Set-BuddyMode $candidate[0] $candidate[1]) {
        $high = $candidate
        break
    }
}
if ($high) {
    try {
        $shot = Join-Path $shotDir "snes-frame-4k.jpg"
        Start-BuddyFrameShot $shot
        $dpiLog.Add("high_mode=$($high[0])x$($high[1])")
        $dpiLog.Add("high_mode_shot=snes-frame-4k.jpg")
    } catch {
        $dpiLog.Add("high_mode=$($high[0])x$($high[1]) shot_skipped $($_.Exception.Message)")
    }
} else {
    $dpiLog.Add("high_mode=skipped")
}

try {
    Set-BuddyMode 1920 1080 | Out-Null
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class BuddyDpi {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool SystemParametersInfo(uint uiAction, uint uiParam, System.IntPtr pvParam, uint fWinIni);
}
"@
    $dpiOk = [BuddyDpi]::SystemParametersInfo(0x009F, 0, [System.IntPtr]1, 3)
    New-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name LogPixels -Value 144 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name Win8DpiScaling -Value 1 -PropertyType DWord -Force | Out-Null
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $shot = Join-Path $shotDir "snes-frame-1080-150.jpg"
    Start-BuddyFrameShot $shot
    $dpiLog.Add("dpi_150_at_1920=ran")
    $dpiLog.Add("dpi_150_api=$dpiOk")
    $dpiLog.Add("dpi_150_screen=$($bounds.Width)x$($bounds.Height)")
    $dpiLog.Add("dpi_150_shot=snes-frame-1080-150.jpg")
    $dpiLog.Add("LogPixels=144")
} catch {
    $dpiLog.Add("dpi_150_at_1920=skipped $($_.Exception.Message)")
}
if (-not ($dpiLog -match "^high_mode=(?!skipped)") -and -not ($dpiLog -match "^dpi_150_at_1920=ran")) {
    $dpiLog.Add("result=skipped")
} else {
    $dpiLog.Add("result=ran")
}
$dpiLog | Set-Content -Path (Join-Path $shotDir "dpi-4k.txt") -Encoding utf8
Get-Content (Join-Path $shotDir "dpi-4k.txt")
Write-Host "Installed launch smoke passed"
