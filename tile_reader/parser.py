from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from .catalog import short_tile_name, tileset_from_path
from .models import (
    MISSION_TYPE_MAP,
    Mission,
    MissionKind,
    Tile,
)


TIMESTAMP_RE = re.compile(r"^\s*(\d+\.\d+)\s+")
HOST_START_RE = re.compile(
    r"launching level for ([^\s(]+)\s*\(([^)]+)\)",
    re.I,
)
MISSION_NAME_RE = re.compile(r"Mission name:\s*(.+)$", re.I)
LAYOUT_SEGMENTS_RE = re.compile(r"generating layout with segments:\s*(\S+)", re.I)
TILE_ROLE_RE = re.compile(
    r"Sys \[Info\]:\s*(S|C|I|O|E|D|Cm|Sb):\s*(/Lotus/\S+)",
    re.I,
)
LAYER_RE = re.compile(r"Layer\s+(/Lotus/Levels/\S+)", re.I)
OPEN_LEVEL_RE = re.compile(r"OpenLevel\s*-\s*(/Lotus/\S+)", re.I)
CLIENT_LOADED_RE = re.compile(r'Client loaded \{"name":"([^"]+)"')
ABORT_RE = re.compile(r"Abort:\s*host/no session", re.I)

DISRUPTION_INTRO = "SentientArtifactMission.lua: Disruption: Intro door"
DISRUPTION_KEY_INSERT = "SentientArtifactMission.lua: Disruption: Starting defense for artifact"
DISRUPTION_DEFENSE_DONE = "SentientArtifactMission.lua: Disruption: Completed defense for artifact"
DISRUPTION_DEFENSE_FAIL = "SentientArtifactMission.lua: Disruption: Failed defense for artifact"
DISRUPTION_TOTAL = "SentientArtifactMission.lua: Disruption: Total artifacts complete so far this mission:"
DISRUPTION_ROUND_START = "SentientArtifactMission.lua: ModeState = 3"
DISRUPTION_ROUND_END = "SentientArtifactMission.lua: ModeState = 4"
DISRUPTION_TOXIN = "SentientArtifactMission.lua: Disruption: Level aura 15"
DISRUPTION_RUN_START = "NemesisMission.lua: NemesisGenerator::InitMission"

ORBITER_MARKERS = (
    "/Lotus/Levels/Proc/PlayerShip generating layout",
    "OpenLevel - /Lotus/Levels/Proc/PlayerShip",
    "ServerFramework:OpenLevel - /Lotus/Levels/Proc/PlayerShip",
)


@dataclass
class LogEvent:
    kind: str
    timestamp: float = 0.0
    payload: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.payload is None:
            self.payload = {}


def parse_timestamp(line: str) -> float:
    match = TIMESTAMP_RE.match(line)
    return float(match.group(1)) if match else 0.0


class LineParser:
    """Turn EE.log lines into structured events."""

    def __init__(self) -> None:
        self._json_buf: list[str] = []
        self._json_depth = 0
        self._collecting_mission_json = False
        self._pending_node = ""

    def reset(self) -> None:
        self._json_buf = []
        self._json_depth = 0
        self._collecting_mission_json = False
        self._pending_node = ""

    def feed(self, line: str) -> list[LogEvent]:
        events: list[LogEvent] = []
        ts = parse_timestamp(line)

        if self._collecting_mission_json:
            self._json_buf.append(line)
            self._json_depth += line.count("{") - line.count("}")
            if self._json_depth <= 0:
                blob = "\n".join(self._json_buf)
                self._collecting_mission_json = False
                self._json_buf = []
                mission = self._mission_from_json(blob)
                if mission:
                    events.append(LogEvent("mission_info", ts, {"mission": mission}))
            return events

        if "with MissionInfo:" in line:
            after = line.split("with MissionInfo:", 1)[1].strip()
            loaded = CLIENT_LOADED_RE.search(line)
            if loaded:
                self._pending_node = loaded.group(1)
            if after.startswith("{"):
                self._json_buf = [after]
                self._json_depth = after.count("{") - after.count("}")
                if self._json_depth <= 0:
                    mission = self._mission_from_json(after)
                    if mission:
                        events.append(LogEvent("mission_info", ts, {"mission": mission}))
                else:
                    self._collecting_mission_json = True
            else:
                self._json_buf = []
                self._json_depth = 0
                self._collecting_mission_json = True
            return events

        host = HOST_START_RE.search(line)
        if host:
            node_id = host.group(1).split("_")[0]
            level = host.group(2)
            events.append(
                LogEvent(
                    "host_start",
                    ts,
                    {"node_id": node_id, "level_override": level},
                )
            )

        name_match = MISSION_NAME_RE.search(line)
        if name_match:
            events.append(LogEvent("mission_name", ts, {"name": name_match.group(1).strip()}))

        layout = LAYOUT_SEGMENTS_RE.search(line)
        if layout:
            proc = ""
            path_match = re.search(r"(/Lotus/Levels/Proc/\S+)\s+generating layout", line)
            if path_match:
                proc = path_match.group(1)
            events.append(
                LogEvent(
                    "layout_segments",
                    ts,
                    {"segments": layout.group(1), "proc_path": proc},
                )
            )

        role = TILE_ROLE_RE.search(line)
        if role:
            path = role.group(2).rstrip(".,;")
            events.append(
                LogEvent(
                    "tile",
                    ts,
                    {
                        "tile": Tile(
                            role=role.group(1),
                            path=path,
                            short_name=short_tile_name(path),
                            source="log",
                        )
                    },
                )
            )

        layer = LAYER_RE.search(line)
        if layer:
            path = layer.group(1).rstrip(".,;")
            events.append(
                LogEvent(
                    "tile",
                    ts,
                    {
                        "tile": Tile(
                            role="Layer",
                            path=path,
                            short_name=short_tile_name(path),
                            source="log",
                        )
                    },
                )
            )

        if "Layer /Lotus/Levels/Backdrops" in line or "Sb: /Lotus/Levels/Backdrops" in line:
            events.append(LogEvent("layout_complete", ts, {}))

        open_level = OPEN_LEVEL_RE.search(line)
        if open_level:
            path = open_level.group(1)
            events.append(LogEvent("open_level", ts, {"path": path}))
            if "PlayerShip" in path:
                events.append(LogEvent("orbiter", ts, {}))

        if any(marker in line for marker in ORBITER_MARKERS) or ABORT_RE.search(line):
            reason = "abort" if ABORT_RE.search(line) else "orbiter"
            events.append(LogEvent("mission_end", ts, {"reason": reason}))

        if DISRUPTION_INTRO in line:
            events.append(LogEvent("disruption_intro", ts, {}))
        if DISRUPTION_RUN_START in line:
            events.append(LogEvent("disruption_run_start", ts, {}))
        if DISRUPTION_ROUND_START in line:
            events.append(LogEvent("disruption_round_start", ts, {}))
        if DISRUPTION_ROUND_END in line:
            events.append(LogEvent("disruption_round_end", ts, {}))
        if DISRUPTION_KEY_INSERT in line:
            events.append(LogEvent("disruption_key_insert", ts, {}))
        if DISRUPTION_DEFENSE_DONE in line:
            events.append(LogEvent("disruption_demo_kill", ts, {}))
        if DISRUPTION_DEFENSE_FAIL in line:
            events.append(LogEvent("disruption_defense_fail", ts, {}))
        if DISRUPTION_TOXIN in line:
            events.append(LogEvent("disruption_toxin", ts, {}))
        if DISRUPTION_TOTAL in line:
            total = _trailing_int(line)
            events.append(LogEvent("disruption_total", ts, {"total": total}))

        return events

    def _mission_from_json(self, blob: str) -> Optional[Mission]:
        try:
            start = blob.find("{")
            end = blob.rfind("}")
            if start < 0 or end < 0:
                return None
            data = json.loads(blob[start : end + 1])
        except json.JSONDecodeError:
            return None
        mission_type = str(data.get("missionType", ""))
        kind = MISSION_TYPE_MAP.get(mission_type, MissionKind.OTHER)
        level_override = str(data.get("levelOverride", ""))
        node_id = str(data.get("location") or self._pending_node or "")
        if "PlayerShip" in level_override:
            kind = MissionKind.HUB
        return Mission(
            node_id=node_id,
            display_name="",
            mission_type=mission_type,
            kind=kind,
            faction=str(data.get("faction", "")),
            level_override=level_override,
            tileset=tileset_from_path(level_override),
            seed=_maybe_int(data.get("seed")),
            min_level=_maybe_int(data.get("minEnemyLevel")),
            max_level=_maybe_int(data.get("maxEnemyLevel")),
        )


def _maybe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _trailing_int(line: str) -> int:
    match = re.search(r"(\d+)\s*$", line.strip())
    return int(match.group(1)) if match else 0
