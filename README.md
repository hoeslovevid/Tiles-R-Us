# Tiles R Us

Warframe overlay that reads the current Disruption or Survival layout and grades it against a local catalog of known rooms.

## Install

**Easiest:** download [TilesRUs-Setup.exe](https://github.com/hoeslovevid/Tiles-R-Us/releases/latest) and double-click it. That wizard puts **Tiles R Us** in the Start Menu and on the desktop, then offers to open the app.

From this folder, double-click **Install Tiles R Us.cmd**. It downloads that same wizard.

From PowerShell:

```powershell
irm https://raw.githubusercontent.com/hoeslovevid/Tiles-R-Us/main/scripts/bootstrap.ps1 | iex
```

After setup, open the app from:

- Start Menu → **Tiles R Us**
- The desktop shortcut
- `tilesrus` in a new terminal

A local/source install (no Setup.exe) is: `.\scripts\install.cmd -FromSource`

## Uninstall

- **Apps & Features** → Tiles R Us → Uninstall
- Or run `scripts\uninstall.cmd` from this repo
- Or, after a GitHub install: `%LocalAppData%\TilesRUs\uninstall.ps1`

Add `-KeepConfig` to leave `config.json` behind.

## Launch from the console

From this folder:

```bat
tilesrus
```

or:

```bat
python -m tile_reader
```

`tilesrus --help` and `tilesrus --version` work too. After install, `tilesrus` is on your PATH — open a **new** terminal and run it from anywhere.

## Run from source (no install)

1. Install [Python 3.11+](https://www.python.org/downloads/) with **tcl/tk**.
2. Start Warframe first (the log file is recreated on launch).
3. Double-click `run.bat`, or run `tilesrus` / `python -m tile_reader`.

No pip packages are required to run from source.

## Report a bug

In the app: **Help → Report a bug…** or the **Report a bug** button. That opens a GitHub issue with diagnostics (mission, rooms, grade, OS). It copies the full report to the clipboard and **does not** attach `EE.log` — that file can contain your email and IP.

## How it works

The app tails `%LocalAppData%\Warframe\EE.log`. It still reads mission type, node, tileset, seed, and Disruption round events from that log.

Tile *names* were hidden by Digital Extremes in Update 37. If the log no longer dumps rooms, use one of these:

- **Mark rooms you see** in the right-hand picker (Kappa, Ur, Apollo, Olympus, Armatus, Ophelia, Zabala, Assur, Persto, Terrorem).
- Take an in-game **F6** screenshot. If the JPEG still embeds the current tile path, the app picks it up from `Pictures\Warframe`.
- Click **Demo: Disruption** / **Demo: Survival** to see a graded layout without loading a mission.

Toggle **Reject** on rooms you personally abort. Those choices are saved in `config.json`.

## Grading

| Mode | What gets graded |
|---|---|
| Disruption | The two main combat rooms (Kappa/Ur numbers, Apollo names, Olympus camp rooms, Armatus lab landmarks), plus optional known pairs like Four+Six |
| Survival | Must-have farm rooms: Botany Lab (Ophelia / polymer), Infested Reactor (Zabala / nanospores), Connector Four (Assur). Persto uses Albrecht landmarks; Terrorem uses Derelict landmarks — mark the room you spawned. |

Catalogs live in `data/catalogs/`. Edit scores, add rooms, or add `known_layouts` there. Newly seen tile names are appended to `discovered_tiles.json`.

## Overlay

Drag the small overlay anywhere. **Lock overlay** makes it click-through so it will not steal game clicks.

## Safety

This only reads the engine log and your own screenshots. It does not inject into Warframe or read process memory. `EE.log` can contain account identifiers — keep it local.
