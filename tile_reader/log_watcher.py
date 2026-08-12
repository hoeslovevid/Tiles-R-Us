from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional


class LogWatcher:
    """Tail EE.log and survive Warframe restarts / log truncation."""

    def __init__(
        self,
        path: Path,
        on_line: Callable[[str], None],
        on_status: Optional[Callable[[str], None]] = None,
        from_end: bool = True,
    ) -> None:
        self.path = path
        self.on_line = on_line
        self.on_status = on_status or (lambda _msg: None)
        self.from_end = from_end
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

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

    def _run(self) -> None:
        position = 0
        saw_file = False
        while not self._stop.is_set():
            if not self.path.exists():
                self._emit_status(f"Waiting for log: {self.path}")
                time.sleep(0.5)
                continue
            try:
                size = self.path.stat().st_size
            except OSError:
                time.sleep(0.2)
                continue
            if not saw_file:
                position = size if self.from_end else 0
                saw_file = True
                self._emit_status(f"Watching {self.path}")
            if size < position:
                position = 0
                self._emit_status("Log reset — Warframe restarted")
            try:
                with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                    handle.seek(position)
                    while not self._stop.is_set():
                        line = handle.readline()
                        if line:
                            if not line.endswith("\n"):
                                handle.seek(handle.tell() - len(line.encode("utf-8", errors="replace")))
                                time.sleep(0.05)
                                break
                            self.on_line(line)
                            position = handle.tell()
                            continue
                        try:
                            new_size = self.path.stat().st_size
                        except OSError:
                            break
                        if new_size < position:
                            position = 0
                            self._emit_status("Log reset — Warframe restarted")
                            break
                        time.sleep(0.05)
                        if not self.path.exists():
                            break
            except OSError as exc:
                self._emit_status(f"Log read error: {exc}")
                time.sleep(0.5)
