from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Bundled files (PyInstaller extract dir, or the project folder)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def runtime_root() -> Path:
    """Writable install / project directory."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def project_root() -> Path:
    return runtime_root()


def data_dir() -> Path:
    return resource_root() / "data"


def catalog_dir() -> Path:
    return data_dir() / "catalogs"


def sample_dir() -> Path:
    return data_dir() / "samples"


def default_ee_log() -> Path:
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        return Path(local) / "Warframe" / "EE.log"
    return Path.home() / "AppData" / "Local" / "Warframe" / "EE.log"


def default_screenshot_dir() -> Path:
    return Path.home() / "Pictures" / "Warframe"


def user_config_path() -> Path:
    return runtime_root() / "config.json"


def discovered_tiles_path() -> Path:
    return runtime_root() / "discovered_tiles.json"


def assets_dir() -> Path:
    return resource_root() / "assets"


def app_icon_path() -> Path:
    ico = assets_dir() / "app.ico"
    if ico.exists():
        return ico
    return assets_dir() / "logo-icon.png"


def wordmark_path() -> Path:
    return assets_dir() / "logo-wordmark.png"
