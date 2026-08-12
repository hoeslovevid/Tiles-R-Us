param(
    [switch]$Quiet,
    [switch]$KeepConfig
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$AppName = "Tiles R Us"
$AppId = "TilesRUs"

function Write-Step([string]$Message) {
    if (-not $Quiet) { Write-Host ">> $Message" -ForegroundColor Cyan }
}

$installDir = $PSScriptRoot
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId"
if (Test-Path $reg) {
    $registered = (Get-ItemProperty $reg -ErrorAction SilentlyContinue).InstallLocation
    if ($registered) { $installDir = $registered }
}

if (-not $Quiet) {
    $answer = Read-Host "Uninstall $AppName from '$installDir'? (Y/N)"
    if ($answer -notmatch '^[Yy]') {
        Write-Host "Cancelled."
        exit 0
    }
}

Write-Step "Removing shortcuts"
$shortcuts = @(
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk")
)
foreach ($link in $shortcuts) {
    if (Test-Path $link) { Remove-Item $link -Force }
}

Write-Step "Removing Apps & Features entry"
if (Test-Path $reg) { Remove-Item $reg -Recurse -Force }

$keep = @()
if ($KeepConfig) {
    $keep = @("config.json", "discovered_tiles.json")
}

Write-Step "Removing files"
if (Test-Path $installDir) {
    Get-ChildItem $installDir -Force | Where-Object { $keep -notcontains $_.Name } | Remove-Item -Recurse -Force
    $left = @(Get-ChildItem $installDir -Force -ErrorAction SilentlyContinue)
    if (-not $left) {
        Remove-Item $installDir -Force -ErrorAction SilentlyContinue
    }
}

if (-not $Quiet) {
    Write-Host "OK  $AppName removed." -ForegroundColor Green
}
