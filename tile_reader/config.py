from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .paths import user_config_path


DEFAULT_CONFIG: dict[str, Any] = {
    "ee_log_path": "",
    "screenshot_dir": "",
    "read_from_end": True,
    "always_on_top": False,
    "overlay": {
        "visible": True,
        "locked": False,
        "x": 48,
        "y": 48,
        "font_size": 16,
        "opacity": 0.92,
    },
    "rejected_tiles": {
        "grineer_galleon_disruption": [],
        "orokin_moon_disruption": [],
        "grineer_settlement_disruption": [],
        "grineer_sealab_survival": [],
        "infested_ship_survival": [],
        "grineer_galleon_survival": [],
    },
}


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg = deepcopy(DEFAULT_CONFIG)
    target = path or user_config_path()
    if target.exists():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            _deep_update(cfg, loaded)
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def save_config(cfg: dict[str, Any], path: Path | None = None) -> None:
    target = path or user_config_path()
    target.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _deep_update(base: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
