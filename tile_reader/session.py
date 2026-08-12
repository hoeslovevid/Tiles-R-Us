from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .catalog import CatalogStore, tileset_from_path
from .grader import grade_layout
from .models import (
    DisruptionRound,
    DisruptionRun,
    GradeResult,
    Layout,
    Mission,
    MissionKind,
    Recommendation,
    SurvivalState,
    Tile,
)
from .parser import LogEvent


HUB_PATHS = ("PlayerShip", "ClanDojo", "Hub")


@dataclass
class Session:
    mission: Mission = field(default_factory=Mission)
    layout: Layout = field(default_factory=Layout)
    grade: GradeResult = field(default_factory=GradeResult)
    disruption: Optional[DisruptionRun] = None
    survival: SurvivalState = field(default_factory=SurvivalState)
    status: str = "Waiting for Warframe"
    in_mission: bool = False
    last_event: str = ""

    def reset_mission(self) -> None:
        self.mission = Mission()
        self.layout = Layout()
        self.grade = GradeResult()
        self.disruption = None
        self.survival = SurvivalState()
        self.in_mission = False


class SessionController:
    def __init__(self, store: CatalogStore, config: dict[str, Any]) -> None:
        self.store = store
        self.config = config
        self.session = Session()

    def handle(self, event: LogEvent) -> bool:
        """Apply an event. Returns True if the UI should refresh."""
        kind = event.kind
        session = self.session
        session.last_event = kind

        if kind == "mission_name":
            session.mission.display_name = event.payload["name"]
            return True

        if kind == "host_start":
            path = event.payload.get("level_override", "")
            if any(hub in path for hub in HUB_PATHS):
                return False
            self._begin_mission()
            session.mission.node_id = event.payload.get("node_id", "")
            session.mission.level_override = path
            session.mission.tileset = tileset_from_path(path) or session.mission.tileset
            self._enrich_from_node()
            return True

        if kind == "mission_info":
            incoming: Mission = event.payload["mission"]
            if incoming.kind == MissionKind.HUB or any(
                hub in incoming.level_override for hub in HUB_PATHS
            ):
                return False
            if not session.in_mission:
                self._begin_mission()
            self._merge_mission(incoming)
            self._enrich_from_node()
            self._regrade()
            return True

        if kind == "layout_segments":
            proc = event.payload.get("proc_path", "")
            if any(hub in proc for hub in HUB_PATHS):
                return False
            if not session.in_mission:
                self._begin_mission()
            session.layout.segments = event.payload.get("segments", "")
            session.layout.proc_path = proc
            if proc:
                session.mission.level_override = session.mission.level_override or proc
                session.mission.tileset = session.mission.tileset or tileset_from_path(proc)
            self._regrade()
            return True

        if kind == "tile":
            tile: Tile = event.payload["tile"]
            if "Backdrops" in tile.path or tile.role in {"Cm", "Sb"}:
                return False
            if not session.in_mission:
                self._begin_mission()
            self.add_tile(tile)
            return True

        if kind == "layout_complete":
            session.layout.complete = True
            self._regrade()
            return True

        if kind == "mission_end":
            session.in_mission = False
            session.status = "Back in orbiter" if event.payload.get("reason") == "orbiter" else "Mission aborted"
            return True

        if kind.startswith("disruption_"):
            return self._handle_disruption(event)

        return False

    def add_tile(self, tile: Tile, regrade: bool = True) -> None:
        existing = {item.path for item in self.session.layout.tiles}
        if tile.path in existing:
            return
        self.session.layout.tiles.append(tile)
        if tile.source != "log":
            self.session.layout.source = tile.source
        if regrade:
            self._regrade()

    def set_manual_tiles(self, short_names: list[str]) -> None:
        self.session.layout.tiles = [
            Tile(role="manual", path=name, short_name=name, source="manual")
            for name in short_names
        ]
        self.session.layout.source = "manual"
        self.session.layout.complete = True
        self._regrade()

    def rejected_for_current(self) -> list[str]:
        key = self.session.mission.catalog_key
        if not key:
            catalog = self.store.catalog_for(
                self.session.mission.node_id,
                self.session.mission.kind,
                self.session.mission.level_override,
            )
            key = catalog.key if catalog else ""
        return list(self.config.get("rejected_tiles", {}).get(key, []))

    def _begin_mission(self) -> None:
        kept_name = self.session.mission.display_name
        self.session.reset_mission()
        self.session.mission.display_name = kept_name
        self.session.in_mission = True
        self.session.status = "Mission loading"

    def _merge_mission(self, incoming: Mission) -> None:
        current = self.session.mission
        current.node_id = incoming.node_id or current.node_id
        current.mission_type = incoming.mission_type or current.mission_type
        current.kind = incoming.kind if incoming.kind != MissionKind.OTHER else current.kind
        current.faction = incoming.faction or current.faction
        current.level_override = incoming.level_override or current.level_override
        current.tileset = incoming.tileset or current.tileset
        current.seed = incoming.seed if incoming.seed is not None else current.seed
        current.min_level = incoming.min_level if incoming.min_level is not None else current.min_level
        current.max_level = incoming.max_level if incoming.max_level is not None else current.max_level

    def _enrich_from_node(self) -> None:
        info = self.store.node_info(self.session.mission.node_id)
        if not info:
            return
        mission = self.session.mission
        mission.display_name = mission.display_name or info.get("name", "")
        if info.get("kind") == "disruption":
            mission.kind = MissionKind.DISRUPTION
        elif info.get("kind") == "survival":
            mission.kind = MissionKind.SURVIVAL
        mission.tileset = mission.tileset or info.get("tileset", "")
        mission.catalog_key = info.get("catalog_key", mission.catalog_key)
        if mission.kind == MissionKind.DISRUPTION and self.session.disruption is None:
            self.session.disruption = DisruptionRun()
        if mission.kind == MissionKind.SURVIVAL:
            self.session.status = "Survival — identify rooms"

    def _regrade(self) -> None:
        mission = self.session.mission
        if mission.kind not in {MissionKind.DISRUPTION, MissionKind.SURVIVAL}:
            if mission.mission_type:
                self.session.grade = GradeResult(
                    grade="—",
                    recommendation=Recommendation.WAIT,
                    reasons=["Waiting for a Disruption or Survival mission."],
                )
            return
        result = grade_layout(
            mission,
            self.session.layout,
            self.store,
            rejected=self.rejected_for_current(),
        )
        self.session.grade = result
        if mission.kind == MissionKind.SURVIVAL:
            good = any("Good farm room" in reason for reason in result.reasons)
            self.session.survival.good_tile_found = good
            self.session.survival.good_tile_name = next(
                (reason.split(": ", 1)[-1] for reason in result.reasons if reason.startswith("Good farm room")),
                "",
            )
        if result.recommendation == Recommendation.ABORT:
            self.session.status = "ABORT — bad layout"
        elif result.recommendation == Recommendation.STAY:
            self.session.status = "STAY — layout is usable"
        elif self.session.layout.tiles:
            self.session.status = "Layout partial — mark remaining rooms"
        else:
            self.session.status = f"{mission.kind.value.title()} loaded — waiting for rooms"

    def _handle_disruption(self, event: LogEvent) -> bool:
        session = self.session
        if session.disruption is None:
            session.disruption = DisruptionRun()
        run = session.disruption
        ts = event.timestamp
        if event.kind == "disruption_run_start":
            run.started_at = ts
        elif event.kind == "disruption_toxin":
            run.toxin = True
        elif event.kind == "disruption_round_start":
            run.rounds.append(DisruptionRound(number=len(run.rounds) + 1, started_at=ts))
        elif event.kind == "disruption_round_end" and run.current_round:
            run.current_round.finished_at = ts
        elif event.kind == "disruption_key_insert" and run.current_round:
            run.current_round.key_inserts.append(ts)
        elif event.kind == "disruption_demo_kill" and run.current_round:
            run.current_round.demo_kills.append(ts)
        elif event.kind == "disruption_defense_fail" and run.current_round:
            run.current_round.keys_failed += 1
        elif event.kind == "disruption_total":
            run.total_artifacts = int(event.payload.get("total") or 0)
        return True
