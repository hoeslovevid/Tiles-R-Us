# Safe to pipe: irm .../bootstrap.ps1 | iex
# Keep $Repo in sync with tile_reader/meta.py
$Repo = "hoeslovevid/Tiles-R-Us"
$script = Join-Path $env:TEMP "TilesRUs-install.ps1"
Write-Host "Downloading installer from GitHub ($Repo)..."
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/$Repo/main/scripts/install.ps1" -OutFile $script -UseBasicParsing
& $script @args
