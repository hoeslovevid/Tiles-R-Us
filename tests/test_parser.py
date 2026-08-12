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


if __name__ == "__main__":
    test_disruption_sample()
    test_survival_sample()
    test_rejected_room_aborts()
    print("ok")
