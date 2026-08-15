# Safe to pipe: irm .../bootstrap.ps1 | iex
# Keep $Repo in sync with tile_reader/meta.py
$Repo = "hoeslovevid/Tiles-R-Us"
$SetupName = "TilesRUs-Setup.exe"

Write-Host "Downloading the Tiles R Us installer from GitHub ($Repo)..."

try {
    $headers = @{
        "User-Agent" = "TilesRUs"
        "Accept"     = "application/vnd.github+json"
    }
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers $headers
    $asset = $release.assets | Where-Object { $_.name -eq $SetupName } | Select-Object -First 1
    if (-not $asset) { throw "No $SetupName on the latest release." }
    $setup = Join-Path $env:TEMP $SetupName
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $setup -UseBasicParsing
    Unblock-File -Path $setup -ErrorAction SilentlyContinue
    Write-Host "Starting the installer wizard..."
    $proc = Start-Process -FilePath $setup -Wait -PassThru
    if ($proc.ExitCode -gt 1) { throw "$SetupName exited with code $($proc.ExitCode)." }
    if ($proc.ExitCode -eq 1) {
        Write-Host "Installer was cancelled."
    } else {
        Write-Host "Tiles R Us is installed. Open it from the Start Menu, the desktop shortcut, or tilesrus."
    }
} catch {
    Write-Host $_.Exception.Message
    Write-Host "Falling back to the script installer..."
    $script = Join-Path $env:TEMP "TilesRUs-install.ps1"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/$Repo/main/scripts/install.ps1" -OutFile $script -UseBasicParsing
    & $script @args
}
