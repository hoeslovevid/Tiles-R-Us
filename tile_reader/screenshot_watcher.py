from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .catalog import short_tile_name
from .models import Tile


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
LOTUS_RE = re.compile(r"/Lotus/Levels/[A-Za-z0-9_./-]+")


class ScreenshotWatcher:
    """Watch Warframe F6 screenshots and pull tile paths out of metadata."""

    def __init__(
        self,
        folder: Path,
        on_tile: Callable[[Tile, Path], None],
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.folder = folder
        self.on_tile = on_tile
        self.on_status = on_status or (lambda _msg: None)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._seen: set[str] = set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="F6Watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def scan_file(self, path: Path) -> Optional[Tile]:
        text = extract_image_text(path)
        match = LOTUS_RE.search(text)
        if not match:
            return None
        raw = match.group(0).rstrip(".,;\"'")
        return Tile(role="screenshot", path=raw, short_name=short_tile_name(raw), source="screenshot")

    def _run(self) -> None:
        if not self.folder.exists():
            self.on_status(f"No screenshot folder yet: {self.folder}")
        else:
            for path in self.folder.glob("*"):
                if path.suffix.lower() in IMAGE_SUFFIXES:
                    self._seen.add(path.name)
            self.on_status(f"Watching screenshots in {self.folder}")
        while not self._stop.is_set():
            if self.folder.exists():
                for path in sorted(self.folder.glob("*"), key=lambda item: item.stat().st_mtime):
                    if path.suffix.lower() not in IMAGE_SUFFIXES:
                        continue
                    if path.name in self._seen:
                        continue
                    self._seen.add(path.name)
                    try:
                        tile = self.scan_file(path)
                    except OSError:
                        continue
                    if tile:
                        self.on_tile(tile, path)
                        self.on_status(f"F6 tile: {tile.short_name}")
                    else:
                        self.on_status(f"F6 shot had no tile metadata: {path.name}")
            time.sleep(0.4)


def extract_image_text(path: Path) -> str:
    data = path.read_bytes()
    if data[:2] == b"\xff\xd8":
        return _jpeg_text(data)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return _png_text(data)
    return data.decode("latin-1", errors="ignore")


def _jpeg_text(data: bytes) -> str:
    chunks: list[str] = []
    i = 2
    length = len(data)
    while i + 4 < length:
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker == 0xDA:
            break
        if marker == 0x00 or marker == 0xFF:
            i += 1
            continue
        size = int.from_bytes(data[i + 2 : i + 4], "big")
        payload = data[i + 4 : i + 2 + size]
        if marker in (0xFE, 0xE0, 0xE1, 0xE2, 0xED):
            chunks.append(payload.decode("latin-1", errors="ignore"))
        i += 2 + size
    return "\n".join(chunks)


def _png_text(data: bytes) -> str:
    chunks: list[str] = []
    i = 8
    while i + 8 < len(data):
        size = int.from_bytes(data[i : i + 4], "big")
        ctype = data[i + 4 : i + 8]
        payload = data[i + 8 : i + 8 + size]
        if ctype in {b"tEXt", b"iTXt", b"zTXt", b"tEXt"}:
            chunks.append(payload.decode("latin-1", errors="ignore"))
        i += 12 + size
        if ctype == b"IEND":
            break
    return "\n".join(chunks)
