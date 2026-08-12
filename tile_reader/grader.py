from __future__ import annotations

from typing import Iterable, Optional

from .catalog import Catalog, CatalogStore
from .models import (
    GradeResult,
    Layout,
    Mission,
    MissionKind,
    Recommendation,
    Tile,
)


GRADE_BANDS = (
    (8, "S"),
    (5, "A"),
    (2, "B"),
    (0, "C"),
    (-3, "D"),
)


def grade_layout(
    mission: Mission,
    layout: Layout,
    store: CatalogStore,
    rejected: Iterable[str] | None = None,
) -> GradeResult:
    catalog = store.catalog_for(mission.node_id, mission.kind, mission.level_override)
    if catalog:
        mission.catalog_key = catalog.key
    rejected_ids = {item.lower() for item in (rejected or []) if item}

    tiles = layout.tiles
    if not tiles:
        return GradeResult(
            grade="?",
            recommendation=Recommendation.WAIT,
            reasons=[
                "No rooms identified yet. DE hid tile names in EE.log (U37).",
                "Mark the rooms you see, or take an in-game F6 screenshot.",
            ],
            catalog_key=catalog.key if catalog else "",
        )

    if catalog:
        for tile in tiles:
            store.remember_tile(catalog.key, tile.short_name)

    if mission.kind == MissionKind.SURVIVAL:
        return _grade_survival(catalog, tiles, rejected_ids)
    if mission.kind == MissionKind.DISRUPTION:
        return _grade_disruption(catalog, layout, rejected_ids)
    return GradeResult(
        grade="?",
        recommendation=Recommendation.WAIT,
        reasons=["This mission type is not graded yet. Disruption and Survival are supported."],
        catalog_key=catalog.key if catalog else "",
    )


def _grade_survival(
    catalog: Optional[Catalog],
    tiles: list[Tile],
    rejected_ids: set[str],
) -> GradeResult:
    reasons: list[str] = []
    score = 0
    names = [tile.short_name for tile in tiles]
    if catalog:
        must = [room for room in catalog.rooms if room.must_have]
        found_must = []
        for room in must:
            hit = _tile_matches_room(names, room.id, room.match)
            if hit:
                found_must.append(room)
                score += max(room.score, 6)
                reasons.append(f"Good farm room: {room.display}")
            else:
                reasons.append(f"Missing farm room: {room.display}")
                score -= 6
        for room in catalog.rooms:
            if room.must_have:
                continue
            if _tile_matches_room(names, room.id, room.match):
                score += room.score
                if room.score < 0:
                    reasons.append(f"Slow room: {room.display}")
                elif room.score > 0:
                    reasons.append(f"Useful room: {room.display}")
        if _is_rejected(names, catalog, rejected_ids):
            return GradeResult(
                grade="F",
                score=score,
                recommendation=Recommendation.ABORT,
                reasons=["Rejected room is in this layout."] + reasons,
                catalog_key=catalog.key,
            )
        if must and not found_must:
            return GradeResult(
                grade="F",
                score=score,
                recommendation=Recommendation.ABORT,
                reasons=reasons or ["Required farm room not found."],
                catalog_key=catalog.key,
            )
        if must and found_must:
            return GradeResult(
                grade="S",
                score=score,
                recommendation=Recommendation.STAY,
                reasons=reasons,
                catalog_key=catalog.key,
            )
    grade, rec = _band(score)
    if not reasons:
        reasons.append("Layout recorded. Add room scores to the survival catalog to refine grades.")
    return GradeResult(
        grade=grade,
        score=score,
        recommendation=rec,
        reasons=reasons,
        catalog_key=catalog.key if catalog else "",
    )


def _grade_disruption(
    catalog: Optional[Catalog],
    layout: Layout,
    rejected_ids: set[str],
) -> GradeResult:
    reasons: list[str] = []
    score = 0
    names = layout.intermediate_names() or layout.short_names()

    if layout.segments:
        length = len(layout.segments.replace("[", "").replace("]", ""))
        if length <= 8:
            score += 2
            reasons.append(f"Compact segment string ({layout.segments})")
        elif length >= 12:
            score -= 2
            reasons.append(f"Long segment string ({layout.segments})")

    matched_layout = ""
    if catalog:
        if _is_rejected(names, catalog, rejected_ids):
            return GradeResult(
                grade="F",
                score=-10,
                recommendation=Recommendation.ABORT,
                reasons=["Rejected room is in this layout. Abort and requeue."]
                + [f"Rooms: {' + '.join(names[:6])}"],
                catalog_key=catalog.key,
            )
        for known in catalog.known_layouts:
            wanted = [str(item).lower() for item in known.get("tiles", [])]
            if wanted and _names_match(names, wanted):
                matched_layout = known.get("id", "")
                grade = str(known.get("grade", "A"))
                rec = (
                    Recommendation.STAY
                    if grade in {"S", "A", "B"}
                    else Recommendation.ABORT
                )
                reasons.append(f"Matched known layout: {known.get('id', 'unnamed')}")
                if known.get("notes"):
                    reasons.append(str(known["notes"]))
                return GradeResult(
                    grade=grade,
                    score=int(known.get("score", 8 if grade == "S" else 4)),
                    recommendation=rec,
                    reasons=reasons,
                    matched_layout=matched_layout,
                    catalog_key=catalog.key,
                )
        hits = 0
        for room in catalog.rooms:
            if _tile_matches_room(names, room.id, room.match):
                hits += 1
                score += room.score
                label = room.display or room.id
                if room.score <= -2:
                    reasons.append(f"Slow room: {label}")
                elif room.score >= 2:
                    reasons.append(f"Strong room: {label}")
                else:
                    reasons.append(f"Room: {label} ({room.score:+d})")
        if hits == 0:
            reasons.append("Rooms found, but none matched the catalog yet. They were saved to discovered_tiles.json.")
        elif hits == 1:
            score -= 1
            reasons.append("Only one catalog room identified — Disruption usually has two main rooms.")

    grade, rec = _band(score)
    if not reasons:
        reasons.append("Rooms recorded. Mark rejected rooms in the picker if you want auto-abort.")
    return GradeResult(
        grade=grade,
        score=score,
        recommendation=rec,
        reasons=reasons,
        matched_layout=matched_layout,
        catalog_key=catalog.key if catalog else "",
    )


def _band(score: int) -> tuple[str, Recommendation]:
    for threshold, grade in GRADE_BANDS:
        if score >= threshold:
            rec = Recommendation.STAY if grade in {"S", "A", "B"} else Recommendation.ABORT
            return grade, rec
    return "F", Recommendation.ABORT


def _tile_matches_room(names: list[str], room_id: str, match: str) -> bool:
    tokens = [token.lower() for token in (match, room_id) if token]
    for name in names:
        lower = name.lower()
        if any(token in lower for token in tokens):
            return True
    return False


def _is_rejected(names: list[str], catalog: Catalog, rejected_ids: set[str]) -> bool:
    if not rejected_ids:
        return False
    for name in names:
        lower = name.lower()
        if lower in rejected_ids:
            return True
        room = catalog.match_tile(name)
        if room and (room.id.lower() in rejected_ids or room.display.lower() in rejected_ids):
            return True
        for rejected in rejected_ids:
            if rejected and rejected in lower:
                return True
    return False


def _names_match(actual: list[str], wanted: list[str]) -> bool:
    actual_l = [name.lower() for name in actual]
    return all(any(token in name for name in actual_l) for token in wanted)
