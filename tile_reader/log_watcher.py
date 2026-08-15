from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from .parser import LineParser, LogEvent


CATCH_UP_BYTES = 16 * 1024 * 1024
READ_CHUNK = 64 * 1024
POLL_SECONDS = 0.01
EVENT_BATCH = 24
MISSION_MARKERS = (
    b"launching level for",
    b"generating layout with segments",
    b"with MissionInfo:",
    b"HostRegion: added layer",
    b"DeathRoom tile selected",
    b"Removing streamed layer",
)


class LogWatcher:
    """Tail EE.log, parse off the UI thread, and survive Warframe restarts."""

    def __init__(
        self,
        path: Path,
        on_events: Callable[[list[LogEvent]], None],
        on_status: Optional[Callable[[str], None]] = None,
        from_end: bool = True,
        parser: Optional[LineParser] = None,
        catch_up_bytes: int = CATCH_UP_BYTES,
    ) -> None:
        self.path = path
        self.on_events = on_events
        self.on_status = on_status or (lambda _msg: None)
        self.from_end = from_end
        self.parser = parser or LineParser()
        self.catch_up_bytes = catch_up_bytes
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._pending: list[LogEvent] = []

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="EELogWatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _emit_status(self, message: str) -> None:
        try:
            self.on_status(message)
        except Exception:
            pass

    def _flush_events(self) -> None:
        if not self._pending:
            return
        batch = self._pending
        self._pending = []
        try:
            self.on_events(batch)
        except Exception:
            pass

    def _emit_line(self, line: str) -> None:
        events = self.parser.feed(line)
        if not events:
            return
        self._pending.extend(events)
        if len(self._pending) >= EVENT_BATCH:
            self._flush_events()

    def _catch_up_position(self, size: int) -> int:
        start = max(0, size - self.catch_up_bytes)
        try:
            with self.path.open("rb") as handle:
                handle.seek(start)
                data = handle.read(self.catch_up_bytes)
        except OSError:
            return start
        last = -1
        skip = (b"PlayerShip", b"DojoHub", b"ZarimanHub", b"ClanDojo")
        for marker in MISSION_MARKERS:
            search_at = len(data)
            while search_at > 0:
                idx = data.rfind(marker, 0, search_at)
                if idx < 0:
                    break
                snippet = data[idx : idx + 480]
                if any(token in snippet for token in skip) and marker == b"launching level for":
                    search_at = idx
                    continue
                if idx > last:
                    last = idx
                break
        if last < 0:
            return start
        nl = data.rfind(b"\n", 0, last)
        return start + (nl + 1 if nl >= 0 else last)

    def _run(self) -> None:
        position = 0
        saw_file = False
        while not self._stop.is_set():
            if not self.path.exists():
                self._emit_status(f"Waiting for log: {self.path}")
                if self._stop.wait(0.2):
                    return
                continue
            try:
                size = self.path.stat().st_size
            except OSError:
                if self._stop.wait(0.1):
                    return
                continue
            if not saw_file:
                if self.from_end:
                    position = self._catch_up_position(size)
                    self._emit_status(f"Watching {self.path} (catch-up {size - position} bytes)")
                else:
                    position = 0
                    self._emit_status(f"Watching {self.path} from start")
                saw_file = True
            if size < position:
                position = 0
                self.parser.reset()
                self._pending = []
                self._emit_status("Log reset — Warframe restarted")
            try:
                with self.path.open("rb") as handle:
                    handle.seek(position)
                    buf = b""
                    while not self._stop.is_set():
                        chunk = handle.read(READ_CHUNK)
                        if chunk:
                            buf += chunk
                            while True:
                                idx = buf.find(b"\n")
                                if idx < 0:
                                    break
                                raw, buf = buf[:idx], buf[idx + 1 :]
                                if raw.endswith(b"\r"):
                                    raw = raw[:-1]
                                line = raw.decode("utf-8", errors="replace") + "\n"
                                self._emit_line(line)
                            position = handle.tell() - len(buf)
                            continue
                        self._flush_events()
                        try:
                            new_size = self.path.stat().st_size
                        except OSError:
                            break
                        if new_size < position:
                            position = 0
                            buf = b""
                            self.parser.reset()
                            self._pending = []
                            self._emit_status("Log reset — Warframe restarted")
                            break
                        if self._stop.wait(POLL_SECONDS):
                            self._flush_events()
                            return
            except OSError as exc:
                self._emit_status(f"Log read error: {exc}")
                if self._stop.wait(0.2):
                    return
