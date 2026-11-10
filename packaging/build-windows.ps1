# Build Buddy-Setup.exe on Windows.
# Needs: this repo, PowerShell, and Inno Setup 6 (ISCC.exe on PATH or in Program Files).
# The first run downloads pinned files, records checksums, and refuses to continue
# if a previously pinned checksum does not match.
#
# Code signing (not active until Chris has a certificate):
#   $env:BUDDY_SIGNTOOL = "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe"
#   $env:BUDDY_SIGN_PFX = "C:\path\buddy.pfx"
#   $env:BUDDY_SIGN_PASSWORD = "..."   # do not commit this
#
# License keys are not checked. See LICENSES.md.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$payload = Join-Path $PSScriptRoot "..\dist\payload"
$cache = Join-Path $PSScriptRoot "..\dist\cache"
$bundled = Join-Path $payload "bundled\RetroArch"
New-Item -ItemType Directory -Force -Path $payload, $cache, $bundled | Out-Null

function Get-Pinned([string]$Id) {
    $path = Join-Path $PSScriptRoot "checksums.pinned.json"
    if (-not (Test-Path $path)) { return "" }
    $json = Get-Content -Raw -Path $path | ConvertFrom-Json
    $value = $json.$Id
    if ($null -eq $value) { return "" }
    return [string]$value
}

function Save-Pin([string]$Id, [string]$Hash) {
    $path = Join-Path $PSScriptRoot "checksums.pinned.json"
    $json = @{}
    if (Test-Path $path) {
        $existing = Get-Content -Raw -Path $path | ConvertFrom-Json
        $existing.PSObject.Properties | ForEach-Object { $json[$_.Name] = $_.Value }
    }
    $json[$Id] = $Hash
    ($json | ConvertTo-Json) | Set-Content -Path $path -Encoding utf8
    Write-Host "Pinned $Id $Hash"
}

function Fetch-Checked([string]$Id, [string]$Url, [string]$FileName) {
    $dest = Join-Path $cache $FileName
    if (-not (Test-Path $dest)) {
        Write-Host "Downloading $Url"
        Invoke-WebRequest -Uri $Url -OutFile $dest
    }
    $hash = (Get-FileHash -Algorithm SHA256 -Path $dest).Hash.ToLower()
    $pinned = (Get-Pinned $Id).ToLower()
    if (-not $pinned) {
        Save-Pin $Id $hash
        Write-Host "First pin for $Id. Run the build again after you commit checksums.pinned.json if this machine is the one Chris trusts."
    } elseif ($pinned -ne $hash) {
        Write-Host "Checksum mismatch for $Id."
        Write-Host "Expected $pinned"
        Write-Host "Actual   $hash"
        Write-Host "Buddy did not package this file."
        exit 1
    } else {
        Write-Host "$Id checksum matches $pinned"
    }
    return $dest
}

$retro = Fetch-Checked "retroarch" "https://buildbot.libretro.com/stable/1.22.1/windows/x86_64/RetroArch.7z" "RetroArch-1.22.1.7z"
$coresArchive = Fetch-Checked "cores" "https://buildbot.libretro.com/stable/1.22.1/windows/x86_64/RetroArch_cores.7z" "RetroArch_cores-1.22.1.7z"
$pythonZip = Fetch-Checked "python" "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip" "python-3.12.8-embed-amd64.zip"
$vc = Fetch-Checked "vcredist" "https://aka.ms/vs/17/release/vc_redist.x64.exe" "vc_redist.x64.exe"

$seven = Get-Command 7z -ErrorAction SilentlyContinue
if (-not $seven) {
    $sevenPath = "C:\Program Files\7-Zip\7z.exe"
    if (Test-Path $sevenPath) { $seven = $sevenPath } else { $seven = $null }
}
if (-not $seven) {
    Write-Host "7-Zip is not installed, so RetroArch was not unpacked. Install 7-Zip and run this again."
    exit 1
}
$sevenExe = if ($seven -is [string]) { $seven } else { $seven.Source }
& $sevenExe x $retro "-o$bundled" -y | Out-Host
$nested = Get-ChildItem -Path $bundled -Filter retroarch.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($nested -and $nested.DirectoryName -ne (Resolve-Path $bundled).Path) {
    Write-Host "Moving RetroArch up from $($nested.DirectoryName)"
    Copy-Item (Join-Path $nested.DirectoryName "*") $bundled -Recurse -Force
}

$runtime = Join-Path $payload "runtime"
if (Test-Path $runtime) { Remove-Item -Recurse -Force $runtime }
Expand-Archive -Path $pythonZip -DestinationPath $runtime -Force
# The embeddable zip uses python312._pth as the whole module path. It ignores
# the current directory and PYTHONPATH. "." is the runtime folder, so backend
# (one level up, next to runtime) is invisible until ".." is listed.
Get-ChildItem $runtime -Filter "python*._pth" | ForEach-Object {
    $kept = @()
    foreach ($line in (Get-Content -Path $_.FullName)) {
        $trim = $line.Trim()
        if ($trim -eq "" -or $trim.StartsWith("#")) { continue }
        if ($trim -eq "import site" -or $trim -eq "..") { continue }
        $kept += $trim
    }
    if ($kept -notcontains ".") { $kept += "." }
    $final = New-Object System.Collections.Generic.List[string]
    $addedParent = $false
    foreach ($line in $kept) {
        $final.Add($line)
        if ($line -eq "." -and -not $addedParent) {
            $final.Add("..")
            $addedParent = $true
        }
    }
    if (-not $addedParent) { $final.Add("..") }
    $final.Add("import site")
    $ascii = New-Object System.Text.ASCIIEncoding
    $body = ($final -join "`r`n") + "`r`n"
    [System.IO.File]::WriteAllText($_.FullName, $body, $ascii)
}
$py = Join-Path $runtime "python.exe"
$getPip = Join-Path $cache "get-pip.py"
if (-not (Test-Path $getPip)) {
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
}
& $py $getPip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $py -m pip install -r (Join-Path $PSScriptRoot "..\backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Copy-Item (Join-Path $PSScriptRoot "..\vc_redist.x64.exe") -ErrorAction SilentlyContinue
Copy-Item $vc (Join-Path $payload "vc_redist.x64.exe") -Force

$include = @(
    "backend", "assets", "config", "data", "LICENSES.md", "README.md",
    "WINDOWS_FIRST_RUN.md", "Start-Buddy.bat", "Start-Buddy.ps1", "install.ps1", "install.bat"
)
foreach ($name in $include) {
    $source = Join-Path (Join-Path $PSScriptRoot "..") $name
    $dest = Join-Path $payload $name
    if (Test-Path $source) {
        Copy-Item $source $dest -Recurse -Force
    }
}

$exe = Join-Path $bundled "retroarch.exe"
if (-not (Test-Path $exe)) {
    Write-Host "retroarch.exe was not in the archive. The package was not finished."
    exit 1
}
$exeHash = (Get-FileHash -Algorithm SHA256 -Path $exe).Hash.ToLower()
$coreDir = Join-Path $bundled "cores"
New-Item -ItemType Directory -Force -Path $coreDir | Out-Null
$coreUnpack = Join-Path $cache "cores-unpack"
New-Item -ItemType Directory -Force -Path $coreUnpack | Out-Null
& $sevenExe x $coresArchive "-o$coreUnpack" -y | Out-Host
$wanted = @("fceumm_libretro.dll", "bsnes_libretro.dll", "blastem_libretro.dll")
$checksums = @{ "retroarch.exe" = $exeHash }
foreach ($dll in $wanted) {
    $found = Get-ChildItem -Path $bundled, $coreUnpack -Filter $dll -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $found) {
        Write-Host "Missing $dll in the RetroArch archive. Buddy did not package a substitute."
        exit 1
    }
    Copy-Item $found.FullName (Join-Path $coreDir $dll) -Force
    $checksums[$dll] = (Get-FileHash -Algorithm SHA256 -Path (Join-Path $coreDir $dll)).Hash.ToLower()
}
$checksums | ConvertTo-Json | Set-Content (Join-Path $payload "bundled\checksums.json") -Encoding utf8

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    foreach ($candidate in @(
        "C:\Program Files\Inno Setup 7\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )) {
        if (Test-Path $candidate) { $iscc = $candidate; break }
    }
}
if (-not $iscc) {
    Write-Host "Inno Setup is not installed. Payload is in dist\payload. Install Inno Setup and run this again to make BuddySetup.exe."
    exit 1
}
$isccExe = if ($iscc -is [string]) { $iscc } else { $iscc.Source }
& $isccExe (Join-Path $PSScriptRoot "Buddy.iss")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$setup = Join-Path $PSScriptRoot "..\dist\BuddySetup.exe"
if (-not (Test-Path $setup)) {
    $alt = Join-Path $PSScriptRoot "..\dist\Buddy-Setup.exe"
    if (Test-Path $alt) { Move-Item $alt $setup -Force }
}
if ($env:BUDDY_SIGNTOOL -and $env:BUDDY_SIGN_PFX) {
    Write-Host "Signing BuddySetup.exe"
    & $env:BUDDY_SIGNTOOL sign /fd SHA256 /f $env:BUDDY_SIGN_PFX $setup
} else {
    Write-Host "Not signed. Set BUDDY_SIGNTOOL and BUDDY_SIGN_PFX when the certificate is ready."
}
if (-not (Test-Path $setup)) {
    Write-Host "BuddySetup.exe was not produced."
    exit 1
}
Write-Host "Built $setup"
