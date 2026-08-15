# Keep $Repo in sync with tile_reader/meta.py
param(
    [switch]$FromSource,
    [switch]$NoDesktopShortcut,
    [switch]$NoLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repo = "hoeslovevid/Tiles-R-Us"
$AppName = "Tiles R Us"
$SetupName = "TilesRUs-Setup.exe"

function Write-Step([string]$Message) {
    Write-Host ">> $Message" -ForegroundColor Cyan
}

function Install-FromSource {
    $local = Join-Path $PSScriptRoot "install.ps1"
    if (-not (Test-Path $local)) {
        throw "install.ps1 was not found next to install-setup.ps1."
    }
    $installArgs = @()
    if ($FromSource) { $installArgs += "-FromSource" }
    if ($NoDesktopShortcut) { $installArgs += "-NoDesktopShortcut" }
    & $local @installArgs
}

function Install-FromSetupExe {
    Write-Step "Downloading the $AppName installer from GitHub"
    $headers = @{
        "User-Agent" = "TilesRUs"
        "Accept"     = "application/vnd.github+json"
    }
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers $headers
    $asset = $release.assets | Where-Object { $_.name -eq $SetupName } | Select-Object -First 1
    if (-not $asset) {
        throw "Latest GitHub release does not include $SetupName."
    }
    $setup = Join-Path $env:TEMP $SetupName
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $setup -UseBasicParsing
    Unblock-File -Path $setup -ErrorAction SilentlyContinue
    Write-Step "Starting the installer wizard"
    $proc = Start-Process -FilePath $setup -Wait -PassThru
    if ($proc.ExitCode -gt 1) {
        throw "$SetupName exited with code $($proc.ExitCode)."
    }
    if ($proc.ExitCode -eq 1) {
        Write-Host "Installer was cancelled."
        return 1
    }
    Write-Host "OK  $AppName is installed. Open it from the Start Menu, the desktop shortcut, or tilesrus." -ForegroundColor Green
    return 0
}

Write-Host ""
Write-Host "$AppName installer" -ForegroundColor Yellow
Write-Host ""

if ($FromSource) {
    Install-FromSource
    exit 0
}

try {
    $code = Install-FromSetupExe
    exit $code
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    Write-Step "Falling back to a local/source install"
    Install-FromSource
}
