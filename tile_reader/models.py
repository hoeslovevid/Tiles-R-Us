from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MissionKind(str, Enum):
    DISRUPTION = "disruption"
    SURVIVAL = "survival"
    OTHER = "other"
    HUB = "hub"


class Recommendation(str, Enum):
    STAY = "STAY"
    ABORT = "ABORT"
    WAIT = "WAIT"


MISSION_TYPE_MAP = {
    "MT_ARTIFACT": MissionKind.DISRUPTION,
    "MT_SURVIVAL": MissionKind.SURVIVAL,
}


@dataclass
class Tile:
    role: str
    path: str
    short_name: str
    source: str = "log"

    def key(self) -> str:
        return self.short_name.lower()


@dataclass
class Mission:
    node_id: str = ""
    display_name: str = ""
    mission_type: str = ""
    kind: MissionKind = MissionKind.OTHER
    faction: str = ""
    level_override: str = ""
    tileset: str = ""
    catalog_key: str = ""
    seed: Optional[int] = None
    min_level: Optional[int] = None
    max_level: Optional[int] = None


@dataclass
class Layout:
    segments: str = ""
    proc_path: str = ""
    tiles: list[Tile] = field(default_factory=list)
    complete: bool = False
    source: str = "log"

    def short_names(self) -> list[str]:
        return [t.short_name for t in self.tiles]

    def intermediate_names(self) -> list[str]:
        names = []
        for tile in self.tiles:
            if tile.role in {"I", "O", "Layer", "manual", "screenshot"}:
                names.append(tile.short_name)
        if names:
            return names
        return self.short_names()


@dataclass
class GradeResult:
    grade: str = "?"
    score: int = 0
    recommendation: Recommendation = Recommendation.WAIT
    reasons: list[str] = field(default_factory=list)
    matched_layout: str = ""
    catalog_key: str = ""


@dataclass
class DisruptionRound:
    number: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0
    key_inserts: list[float] = field(default_factory=list)
    demo_kills: list[float] = field(default_factory=list)
    keys_failed: int = 0

    def duration(self) -> float:
        if self.finished_at and self.started_at:
            return max(0.0, self.finished_at - self.started_at)
        return 0.0


@dataclass
class DisruptionRun:
    started_at: float = 0.0
    toxin: bool = False
    rounds: list[DisruptionRound] = field(default_factory=list)
    total_artifacts: int = 0

    @property
    def current_round(self) -> Optional[DisruptionRound]:
        return self.rounds[-1] if self.rounds else None


@dataclass
class SurvivalState:
    good_tile_found: bool = False
    good_tile_name: str = ""
    notes: list[str] = field(default_factory=list)
