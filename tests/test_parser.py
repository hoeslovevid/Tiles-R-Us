from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tile_reader.catalog import CatalogStore
from tile_reader.grader import grade_layout
from tile_reader.models import Recommendation
from tile_reader.parser import LineParser
from tile_reader.session import SessionController


def replay(path: Path) -> SessionController:
    store = CatalogStore()
    controller = SessionController(store, {"rejected_tiles": {}})
    parser = LineParser()
    for line in path.read_text(encoding="utf-8").splitlines(True):
        for event in parser.feed(line):
            controller.handle(event)
    return controller


def replay_text(text: str, rejected: dict | None = None) -> SessionController:
    store = CatalogStore()
    controller = SessionController(store, {"rejected_tiles": rejected or {}})
    parser = LineParser()
    for line in text.splitlines(True):
        for event in parser.feed(line):
            controller.handle(event)
    return controller


def test_disruption_sample() -> None:
    session = replay(ROOT / "data" / "samples" / "sample_disruption.log").session
    assert session.mission.node_id == "SolNode177"
    assert session.mission.display_name == "Kappa (Sedna)"
    names = session.layout.intermediate_names()
    assert any("Four" in name for name in names)
    assert any("Six" in name for name in names)
    assert session.grade.grade == "S"
    assert session.grade.recommendation == Recommendation.STAY
    assert session.disruption is not None
    assert len(session.disruption.rounds) == 1
    assert len(session.disruption.current_round.key_inserts) == 2


def test_survival_sample() -> None:
    session = replay(ROOT / "data" / "samples" / "sample_survival.log").session
    assert session.mission.node_id == "SolNode69"
    assert any("BotanyLab" in name for name in session.layout.short_names())
    assert session.grade.grade == "S"
    assert session.survival.good_tile_found


def test_rejected_room_aborts() -> None:
    store = CatalogStore()
    controller = SessionController(store, {"rejected_tiles": {"grineer_galleon_disruption": ["Eight"]}})
    parser = LineParser()
    log = (ROOT / "data" / "samples" / "sample_disruption.log").read_text(encoding="utf-8")
    log = log.replace("GrnIntermediateSix", "GrnIntermediateEight")
    for line in log.splitlines(True):
        for event in parser.feed(line):
            controller.handle(event)
    assert controller.session.grade.recommendation == Recommendation.ABORT
    assert controller.session.grade.grade == "F"


def test_hostregion_grades_before_backdrop() -> None:
    log = """12.000 Script [Info]: ThemedSquadOverlay.lua: Mission name: Kappa (Sedna)
12.010 Script [Info]: ThemedSquadOverlay.lua: Lobby::Host_StartMatch: launching level for SolNode177 (/Lotus/Levels/Proc/Grineer/GrineerGalleonDisruption)
12.020 Sys [Info]: Client loaded {"name":"SolNode177","quest":""} with MissionInfo:
{
    "missionType" : "MT_ARTIFACT",
    "faction" : "FC_GRINEER",
    "seed" : 424242,
    "location" : "SolNode177",
    "levelOverride" : "/Lotus/Levels/Proc/Grineer/GrineerGalleonDisruption"
}
12.100 Sys [Info]: /Lotus/Levels/Proc/Grineer/GrineerGalleonDisruption generating layout with segments: SCICICE
12.111 Sys [Info]: HostRegion: added layer 1, level=/Lotus/Levels/GrineerGalleon/GrnSpawn01
12.112 Sys [Info]: HostRegion: added layer 2, level=/Lotus/Levels/GrineerGalleon/GrnConnectorTwo
12.113 Sys [Info]: HostRegion: added layer 3, level=/Lotus/Levels/GrineerGalleon/GrnIntermediateFour
12.114 Sys [Info]: HostRegion: added layer 4, level=/Lotus/Levels/GrineerGalleon/GrnIntermediateSix
12.115 Sys [Info]: ResourceLoader: loaded /Lotus/Levels/GrineerGalleon/GrnSpawn01.level
12.116 Sys [Info]: ResourceLoader: loading Layer /Lotus/Levels/Proc/Grineer/GrineerGalleonDisruption.lp
"""
    session = replay_text(log).session
    assert session.grade.grade == "S"
    assert session.grade.recommendation == Recommendation.STAY
    assert session.layout.complete
    names = session.layout.short_names()
    assert not any(name.endswith(".lp") for name in names)
    assert "GrnSpawn01" in names
    assert sum(1 for name in names if name == "GrnSpawn01") == 1


def test_partial_disruption_waits() -> None:
    log = """12.010 Script [Info]: ThemedSquadOverlay.lua: Lobby::Host_StartMatch: launching level for SolNode177 (/Lotus/Levels/Proc/Grineer/GrineerGalleonDisruption)
12.020 Sys [Info]: Client loaded {"name":"SolNode177","quest":""} with MissionInfo:
{"missionType":"MT_ARTIFACT","location":"SolNode177","levelOverride":"/Lotus/Levels/Proc/Grineer/GrineerGalleonDisruption"}
12.111 Sys [Info]: HostRegion: added layer 3, level=/Lotus/Levels/GrineerGalleon/GrnIntermediateFour
"""
    session = replay_text(log).session
    assert session.grade.recommendation == Recommendation.WAIT
    assert session.grade.grade == "?"


def test_partial_survival_waits() -> None:
    log = """8.010 Script [Info]: ThemedSquadOverlay.lua: Lobby::Host_StartMatch: launching level for SolNode69 (/Lotus/Levels/Proc/Grineer/GrineerOceanSurvival)
8.020 Sys [Info]: Client loaded {"name":"SolNode69","quest":""} with MissionInfo:
{"missionType":"MT_SURVIVAL","location":"SolNode69","levelOverride":"/Lotus/Levels/Proc/Grineer/GrineerOceanSurvival"}
8.110 Sys [Info]: S: /Lotus/Levels/GrineerOcean/GrineerOceanSpawn01.level
"""
    session = replay_text(log).session
    assert session.grade.recommendation == Recommendation.WAIT
    assert session.grade.grade == "?"


def test_level_colon_tiles() -> None:
    parser = LineParser()
    events = parser.feed("12.0 Sys [Info]: Level: /Lotus/Levels/GrineerGalleon/GrnIntermediateFour\n")
    kinds = [event.kind for event in events]
    assert "tile" in kinds
    assert events[0].payload["tile"].role == "I"


if __name__ == "__main__":
    test_disruption_sample()
    test_survival_sample()
    test_rejected_room_aborts()
    test_hostregion_grades_before_backdrop()
    test_partial_disruption_waits()
    test_partial_survival_waits()
    test_level_colon_tiles()
    print("ok")
