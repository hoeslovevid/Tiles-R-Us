from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
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
HOST_REGION_RE = re.compile(
    r"HostRegion:\s*added layer\s+\d+,\s*level=(/Lotus/Levels/[^\s,]+)",
    re.I,
)
LEVEL_COLON_RE = re.compile(r"Sys \[Info\]:\s*Level:\s*(/Lotus/Levels/[^\s,]+)", re.I)
GAME_LEVEL_RE = re.compile(r"Game \[Info\]:\s*Level=(/Lotus/Levels/[^\s,]+)", re.I)
OPEN_LEVEL_RE = re.compile(r"OpenLevel\s*-\s*(/Lotus/\S+)", re.I)
CLIENT_LOADED_RE = re.compile(r'Client loaded \{"name":"([^"]+)"')
HOST_LOADING_RE = re.compile(r'Host loading \{[^}\n]*"name":"([^"]+)"')
ABORT_RE = re.compile(r"Abort:\s*host/no session", re.I)
LOTUS_PATH_RE = re.compile(r"/Lotus/Levels/[A-Za-z0-9_./-]+")
AMBIENCE_RE = re.compile(r"/Lotus/Sounds/Ambience/[^/\s]+/([A-Za-z0-9_]+)")
DEATHROOM_RE = re.compile(r"DeathRoom tile selected:\s+\S+\s+(/Lotus/Levels/\S+)", re.I)
STREAM_LAYER_RE = re.compile(r"streamed layer:\s*(/Lotus/Levels/\S+)", re.I)
REQUIRED_OBJECT_RE = re.compile(r"Required by object\s+(/Lotus/Levels/\S+)", re.I)

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

SKIP_TILE_HINTS = (
    "/proc/",
    "playership",
    "backdrops",
    "skybox",
    "/lore/",
    "/interface/",
    "clandojo",
    "hub/",
    "darksectors",
    "/episodes/",
)

INTERESTING_NEEDLES = (
    "MissionInfo",
    "launching level",
    "Mission name:",
    "generating layout",
    "Layer ",
    "HostRegion: added layer",
    "Sys [Info]: Level:",
    "Game [Info]: Level=",
    "OpenLevel",
    "PlayerShip",
    "SentientArtifact",
    "Abort:",
    "NemesisGenerator",
    "ModeState",
    "S: /Lotus/",
    "C: /Lotus/",
    "I: /Lotus/",
    "O: /Lotus/",
    "E: /Lotus/",
    "D: /Lotus/",
    "S:/Lotus/",
    "C:/Lotus/",
    "I:/Lotus/",
    "O:/Lotus/",
    "E:/Lotus/",
    "D:/Lotus/",
    ":/Lotus/Levels/",
    "DeathRoom tile selected",
    "streamed layer",
    "Required by object /Lotus/Levels",
    "/Lotus/Sounds/Ambience/",
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


def _line_is_interesting(line: str) -> bool:
    return any(needle in line for needle in INTERESTING_NEEDLES)


def _normalize_level_path(path: str) -> str:
    path = path.strip().rstrip(".,;\"'/")
    path = re.sub(r"/Scope$", "", path, flags=re.I)
    path = re.sub(r"\.level$", "", path, flags=re.I)
    return path


def _should_skip_tile_path(path: str) -> bool:
    lower = path.lower()
    if lower.endswith(".lp"):
        return True
    if "/prefabs/" in lower:
        return True
    return any(hint in lower for hint in SKIP_TILE_HINTS)


def _infer_tile_role(role: str, path: str) -> str:
    if role and role not in {"Layer"}:
        return role
    lower = path.lower()
    if "intermediate" in lower or "moonint" in lower:
        return "I"
    if "spawn" in lower:
        return "S"
    if "connector" in lower:
        return "C"
    if "exit" in lower or "extract" in lower:
        return "E"
    if "objective" in lower:
        return "O"
    return role or "Layer"


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

        if not _line_is_interesting(line):
            return events

        if "with MissionInfo:" in line:
            after = line.split("with MissionInfo:", 1)[1].strip()
            loaded = CLIENT_LOADED_RE.search(line) or HOST_LOADING_RE.search(line)
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

        skip_tiles = "ResourceLoader" in line or "Resloader" in line
        if not skip_tiles:
            role = TILE_ROLE_RE.search(line)
            if role:
                self._add_tile_event(events, ts, role.group(1), role.group(2), "log")

            layer = LAYER_RE.search(line)
            if layer:
                self._add_tile_event(events, ts, "Layer", layer.group(1), "log")

            host_region = HOST_REGION_RE.search(line)
            if host_region:
                self._add_tile_event(events, ts, "Layer", host_region.group(1), "log")

            level_colon = LEVEL_COLON_RE.search(line)
            if level_colon:
                self._add_tile_event(events, ts, "Layer", level_colon.group(1), "log")

            game_level = GAME_LEVEL_RE.search(line)
            if game_level:
                self._add_tile_event(events, ts, "Layer", game_level.group(1), "log")

            death = DEATHROOM_RE.search(line)
            if death:
                self._add_tile_event(events, ts, "Layer", death.group(1), "log")

            streamed = STREAM_LAYER_RE.search(line)
            if streamed:
                self._add_tile_event(events, ts, "Layer", streamed.group(1), "log")

            required = REQUIRED_OBJECT_RE.search(line)
            if required:
                self._add_tile_event(events, ts, "Layer", required.group(1), "log")

            if not any((role, layer, host_region, level_colon, game_level, death, streamed, required)):
                for path in LOTUS_PATH_RE.findall(line):
                    self._add_tile_event(events, ts, "Layer", path, "log")

            ambience = AMBIENCE_RE.search(line)
            if ambience:
                self._add_tile_event(events, ts, "I", f"/Lotus/Levels/_Sound/{ambience.group(1)}", "log")

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

    def _add_tile_event(self, events: list[LogEvent], ts: float, role: str, path: str, source: str) -> None:
        path = _normalize_level_path(path)
        if _should_skip_tile_path(path):
            return
        events.append(
            LogEvent(
                "tile",
                ts,
                {
                    "tile": Tile(
                        role=_infer_tile_role(role, path),
                        path=path,
                        short_name=short_tile_name(path),
                        source=source,
                    )
                },
            )
        )

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


HUB_SNIPPETS = (b"PlayerShip", b"DojoHub", b"ZarimanHub", b"ClanDojo")


def parse_latest_mission(path: Path, window: int = 16 * 1024 * 1024) -> list[LogEvent]:
    data = Path(path).read_bytes()
    if len(data) > window:
        data = data[-window:]
    last = -1
    for marker in (b"launching level for", b"with MissionInfo:", b"DeathRoom tile selected"):
        search_at = len(data)
        while search_at > 0:
            idx = data.rfind(marker, 0, search_at)
            if idx < 0:
                break
            snippet = data[idx : idx + 480]
            if marker == b"launching level for" and any(token in snippet for token in HUB_SNIPPETS):
                search_at = idx
                continue
            if idx > last:
                last = idx
            break
    if last < 0:
        last = 0
    nl = data.rfind(b"\n", 0, last)
    start = nl + 1 if nl >= 0 else last
    text = data[start:].decode("utf-8", errors="replace")
    parser = LineParser()
    events: list[LogEvent] = []
    for line in text.splitlines(True):
        events.extend(parser.feed(line))
    return events
