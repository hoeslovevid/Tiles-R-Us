from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .models import MissionKind
from .paths import catalog_dir, data_dir, discovered_tiles_path


TILESET_HINTS = (
    ("GrineerGalleon", "Grineer Galleon"),
    ("GrineerSettlement", "Grineer Settlement"),
    ("GrineerOcean", "Grineer Sealab"),
    ("GrineerAsteroidFortress", "Kuva Fortress"),
    ("GrnFortress", "Kuva Fortress"),
    ("OrokinMoon", "Orokin Moon"),
    ("CorpusGasCity", "Corpus Gas City"),
    ("CorpusShip", "Corpus Ship"),
    ("InfestedCorpus", "Infested Ship"),
    ("Infested", "Infested Ship"),
    ("EntratiLab", "Albrecht's Laboratories"),
    ("Albrecht", "Albrecht's Laboratories"),
    ("Zariman", "Zariman"),
    ("Duviri", "Duviri"),
    ("PlayerShip", "Orbiter"),
)


CATALOG_HINTS = (
    ("GrineerGalleon", "disruption", "grineer_galleon_disruption"),
    ("GrineerSettlement", "disruption", "grineer_settlement_disruption"),
    ("OrokinMoon", "disruption", "orokin_moon_disruption"),
    ("CorpusGasCity", "disruption", "corpus_gas_city_disruption"),
    ("CorpusShip", "disruption", "corpus_ship_disruption"),
    ("GrineerAsteroidFortress", "disruption", "kuva_fortress_disruption"),
    ("EntratiLab", "disruption", "albrecht_disruption"),
    ("GrineerOcean", "survival", "grineer_sealab_survival"),
    ("InfestedCorpus", "survival", "infested_ship_survival"),
    ("GrineerGalleon", "survival", "grineer_galleon_survival"),
    ("CorpusGasCity", "survival", "corpus_gas_city_survival"),
)


@dataclass
class RoomInfo:
    id: str
    display: str
    score: int = 0
    tags: list[str] = field(default_factory=list)
    match: str = ""
    must_have: bool = False
    notes: str = ""
    looks: str = ""


@dataclass
class Catalog:
    key: str
    kind: str
    tileset: str
    title: str
    rooms: list[RoomInfo]
    known_layouts: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    def room_by_id(self, room_id: str) -> Optional[RoomInfo]:
        needle = room_id.lower()
        for room in self.rooms:
            if room.id.lower() == needle or room.display.lower() == needle:
                return room
            if room.match and room.match.lower() in needle:
                return room
        return None

    def match_tile(self, short_name: str) -> Optional[RoomInfo]:
        lower = short_name.lower()
        for room in self.rooms:
            token = (room.match or room.id).lower()
            if token and token in lower:
                return room
            if room.display.lower() == lower:
                return room
        return None


class CatalogStore:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.catalogs: dict[str, Catalog] = {}
        self.discovered: dict[str, list[str]] = {}
        self._discovered_dirty = False
        self.reload()

    def reload(self) -> None:
        nodes_path = data_dir() / "nodes.json"
        if nodes_path.exists():
            self.nodes = json.loads(nodes_path.read_text(encoding="utf-8"))
        self.catalogs = {}
        for path in sorted(catalog_dir().glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            for item in payload.get("catalogs", [payload] if "key" in payload else []):
                catalog = Catalog(
                    key=item["key"],
                    kind=item.get("kind", "other"),
                    tileset=item.get("tileset", ""),
                    title=item.get("title", item["key"]),
                    rooms=[RoomInfo(**room) for room in item.get("rooms", [])],
                    known_layouts=item.get("known_layouts", []),
                    notes=item.get("notes", ""),
                )
                self.catalogs[catalog.key] = catalog
        discovered_path = discovered_tiles_path()
        if discovered_path.exists():
            try:
                self.discovered = json.loads(discovered_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.discovered = {}
        self._discovered_dirty = False

    def remember_tile(self, catalog_key: str, short_name: str) -> None:
        if not catalog_key or not short_name:
            return
        bucket = self.discovered.setdefault(catalog_key, [])
        if short_name not in bucket:
            bucket.append(short_name)
            self._discovered_dirty = True

    def flush_discovered(self) -> None:
        if not self._discovered_dirty:
            return
        discovered_tiles_path().write_text(
            json.dumps(self.discovered, indent=2), encoding="utf-8"
        )
        self._discovered_dirty = False

    def node_info(self, node_id: str) -> dict[str, Any]:
        return self.nodes.get(node_id, {})

    def catalog_for(self, node_id: str, kind: MissionKind, level_override: str) -> Optional[Catalog]:
        info = self.node_info(node_id)
        key = info.get("catalog_key")
        if key and key in self.catalogs:
            return self.catalogs[key]
        kind_key = kind.value if isinstance(kind, MissionKind) else str(kind)
        for hint, hint_kind, catalog_key in CATALOG_HINTS:
            if hint.lower() in level_override.lower() and hint_kind == kind_key:
                return self.catalogs.get(catalog_key)
        return None


def tileset_from_path(path: str) -> str:
    for hint, label in TILESET_HINTS:
        if hint.lower() in path.lower():
            return label
    return ""


def short_tile_name(path: str) -> str:
    name = path.replace("\\", "/").split("/")[-1]
    name = re.sub(r"\.level$", "", name, flags=re.I)
    name = re.sub(r"/Scope$", "", name, flags=re.I)
    if name.lower() == "scope":
        parts = path.replace("\\", "/").rstrip("/").split("/")
        if len(parts) >= 2 and parts[-1].lower() == "scope":
            name = parts[-2]
    return expand_numeric_name(name)


_DIGIT_WORDS = {
    "1": "One",
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
    "10": "Ten",
    "11": "Eleven",
}


def expand_numeric_name(name: str) -> str:
    match = re.search(r"(Intermediate)(\d+)$", name, re.I)
    if not match:
        return name
    word = _DIGIT_WORDS.get(match.group(2))
    if not word:
        return name
    return name[: match.start(2)] + word
