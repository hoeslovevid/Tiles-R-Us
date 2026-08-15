# Keep $Repo in sync with tile_reader/meta.py
param(
    [string]$Repo = "hoeslovevid/Tiles-R-Us",
    [string]$Version = "latest",
    [string]$InstallDir = "",
    [string]$SourceDir = "",
    [switch]$FromSource,
    [switch]$NoDesktopShortcut,
    [switch]$KeepConfig
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$AppName = "Tiles R Us"
$AppId = "TilesRUs"
$Publisher = "Tiles R Us"
$ExeName = "TilesRUs.exe"

function Write-Step([string]$Message) {
    Write-Host ">> $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "OK  $Message" -ForegroundColor Green
}

function Get-InstallDir {
    if ($InstallDir) { return [IO.Path]::GetFullPath($InstallDir) }
    return Join-Path $env:LOCALAPPDATA $AppId
}

function Get-Python {
    foreach ($cmd in @("pythonw", "python", "py")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    return $null
}

function Add-UserPath([string]$Dir) {
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $current) { $current = "" }
    $parts = @($current -split ';' | Where-Object { $_ })
    if ($parts -contains $Dir) { return }
    $updated = if ($current.Trim()) { "$current;$Dir" } else { $Dir }
    [Environment]::SetEnvironmentVariable("Path", $updated, "User")
    if ($env:Path -notlike "*$Dir*") {
        $env:Path = "$env:Path;$Dir"
    }
}

function New-Shortcut([string]$Path, [string]$Target, [string]$WorkingDir, [string]$Arguments = "") {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $Target
    $shortcut.WorkingDirectory = $WorkingDir
    if ($Arguments) { $shortcut.Arguments = $Arguments }
    $shortcut.WindowStyle = 1
    $shortcut.Save()
}

function Register-Uninstall([string]$Dir, [string]$DisplayVersion, [string]$UninstallFile) {
    $reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId"
    New-Item -Path $reg -Force | Out-Null
    $uninstall = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $UninstallFile
    Set-ItemProperty -Path $reg -Name "DisplayName" -Value $AppName
    Set-ItemProperty -Path $reg -Name "DisplayVersion" -Value $DisplayVersion
    Set-ItemProperty -Path $reg -Name "Publisher" -Value $Publisher
    Set-ItemProperty -Path $reg -Name "InstallLocation" -Value $Dir
    Set-ItemProperty -Path $reg -Name "UninstallString" -Value $uninstall
    Set-ItemProperty -Path $reg -Name "QuietUninstallString" -Value "$uninstall -Quiet"
    Set-ItemProperty -Path $reg -Name "NoModify" -Value 1 -Type DWord
    Set-ItemProperty -Path $reg -Name "NoRepair" -Value 1 -Type DWord
    $exe = Join-Path $Dir $ExeName
    if (Test-Path $exe) {
        Set-ItemProperty -Path $reg -Name "DisplayIcon" -Value $exe
    }
}

function Get-ReleaseAssetUrl([string]$RepoName, [string]$Tag) {
    $headers = @{
        "User-Agent" = $AppId
        "Accept"     = "application/vnd.github+json"
    }
    if ($Tag -eq "latest") {
        $api = "https://api.github.com/repos/$RepoName/releases/latest"
    } else {
        $api = "https://api.github.com/repos/$RepoName/releases/tags/$Tag"
    }
    try {
        $release = Invoke-RestMethod -Uri $api -Headers $headers
    } catch {
        return $null
    }
    $asset = $release.assets | Where-Object { $_.name -match "windows\.zip$|TilesRUs-windows" } | Select-Object -First 1
    if (-not $asset) {
        $asset = $release.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
    }
    if ($asset) {
        return [pscustomobject]@{ Url = $asset.browser_download_url; Version = $release.tag_name.TrimStart("v"); Name = $asset.name }
    }
    return $null
}

function Install-FromZip([string]$ZipPath, [string]$Dest) {
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("$AppId-" + [guid]::NewGuid().ToString("n"))
    New-Item -ItemType Directory -Path $temp | Out-Null
    try {
        Expand-Archive -Path $ZipPath -DestinationPath $temp -Force
        $payload = $temp
        $nested = Get-ChildItem $temp -Directory | Select-Object -First 1
        $hasExe = Get-ChildItem $temp -Filter $ExeName -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hasExe) {
            $payload = $hasExe.Directory.FullName
        } elseif ($nested) {
            $payload = $nested.FullName
        }
        Copy-Item -Path (Join-Path $payload "*") -Destination $Dest -Recurse -Force
    } finally {
        Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$dest = Get-InstallDir
Write-Host ""
Write-Host "$AppName installer" -ForegroundColor Yellow
Write-Host "Install folder: $dest"
Write-Host ""

if (-not $FromSource -and -not $SourceDir) {
    $here = $PSScriptRoot
    if ($here -and (Test-Path (Join-Path $here "..\main.py"))) {
        $FromSource = $true
        $SourceDir = (Resolve-Path (Join-Path $here "..")).Path
    }
}

New-Item -ItemType Directory -Path $dest -Force | Out-Null

$displayVersion = "1.2.0"
$installedKind = "source"

if ($FromSource -or $SourceDir) {
    if (-not $SourceDir) { $SourceDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
    Write-Step "Installing from source: $SourceDir"
    $copyNames = @("main.py", "run.bat", "README.md", "requirements.txt", "tile_reader", "data", "scripts", "tilesrus.cmd", "tiles-r-us.cmd")
    foreach ($name in $copyNames) {
        $from = Join-Path $SourceDir $name
        if (Test-Path $from) {
            Copy-Item $from (Join-Path $dest $name) -Recurse -Force
        }
    }
    $installedKind = "source"
} else {
    Write-Step "Downloading $Repo ($Version) from GitHub"
    $asset = Get-ReleaseAssetUrl -RepoName $Repo -Tag $Version
    $zip = Join-Path ([IO.Path]::GetTempPath()) "$AppId-download.zip"
    if ($asset) {
        Write-Step "Fetching $($asset.Name)"
        Invoke-WebRequest -Uri $asset.Url -OutFile $zip -UseBasicParsing
        $displayVersion = $asset.Version
        Install-FromZip -ZipPath $zip -Dest $dest
        $installedKind = "release"
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
    } else {
        Write-Step "No GitHub Release zip found - downloading source from main"
        $sourceUrl = "https://github.com/$Repo/archive/refs/heads/main.zip"
        Invoke-WebRequest -Uri $sourceUrl -OutFile $zip -UseBasicParsing
        Install-FromZip -ZipPath $zip -Dest $dest
        $installedKind = "source"
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
    }
}

$uninstallSrc = $null
if ($PSScriptRoot) {
    $candidate = Join-Path $PSScriptRoot "uninstall.ps1"
    if (Test-Path $candidate) { $uninstallSrc = $candidate }
}
if (-not $uninstallSrc) {
    $candidate = Join-Path $dest "scripts\uninstall.ps1"
    if (Test-Path $candidate) { $uninstallSrc = $candidate }
}
$uninstallDest = Join-Path $dest "uninstall.ps1"
if ($uninstallSrc) {
    Copy-Item $uninstallSrc $uninstallDest -Force
} elseif (-not (Test-Path $uninstallDest)) {
    Write-Step "Downloading uninstall.ps1 from GitHub"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/$Repo/main/scripts/uninstall.ps1" -OutFile $uninstallDest -UseBasicParsing
}

$exe = Join-Path $dest $ExeName
$python = Get-Python
$launcher = Join-Path $dest "tilesrus.cmd"
if (-not (Test-Path $launcher)) {
    $fromLauncher = Join-Path $PSScriptRoot "..\tilesrus.cmd"
    if ($PSScriptRoot -and (Test-Path $fromLauncher)) {
        Copy-Item $fromLauncher $launcher -Force
        Copy-Item (Join-Path $PSScriptRoot "..\tiles-r-us.cmd") (Join-Path $dest "tiles-r-us.cmd") -Force -ErrorAction SilentlyContinue
    }
}
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
New-Item -ItemType Directory -Path $startMenu -Force | Out-Null
$startShortcut = Join-Path $startMenu "$AppName.lnk"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk"

if (Test-Path $exe) {
    Write-Step "Creating shortcuts to $ExeName"
    New-Shortcut -Path $startShortcut -Target $exe -WorkingDir $dest
    if (-not $NoDesktopShortcut) {
        New-Shortcut -Path $desktopShortcut -Target $exe -WorkingDir $dest
    }
} elseif ($python) {
    $main = Join-Path $dest "main.py"
    if (-not (Test-Path $main)) { throw "Install did not contain main.py or $ExeName." }
    Write-Step "Creating shortcuts via tilesrus.cmd"
    if (-not (Test-Path $launcher)) { throw "tilesrus.cmd was missing from the install." }
    New-Shortcut -Path $startShortcut -Target $launcher -WorkingDir $dest
    if (-not $NoDesktopShortcut) {
        New-Shortcut -Path $desktopShortcut -Target $launcher -WorkingDir $dest
    }
} else {
    throw "Python was not found and this install has no $ExeName. Install Python 3.11+ (with tcl/tk) or use a GitHub Release."
}

Write-Step "Adding $dest to your user PATH"
Add-UserPath $dest

Register-Uninstall -Dir $dest -DisplayVersion $displayVersion -UninstallFile $uninstallDest
Write-Ok "Installed $AppName $displayVersion ($installedKind)"
Write-Host "Open it from the Start Menu, the desktop shortcut, or tilesrus."
Write-Host "Uninstall from Apps and Features or:"
Write-Host ('  powershell -ExecutionPolicy Bypass -File "{0}"' -f $uninstallDest)
Write-Host ""

$toLaunch = $null
if (Test-Path $exe) { $toLaunch = $exe }
elseif (Test-Path $launcher) { $toLaunch = $launcher }
if ($toLaunch) {
    Write-Step "Opening $AppName"
    Start-Process -FilePath $toLaunch -WorkingDirectory $dest
}
