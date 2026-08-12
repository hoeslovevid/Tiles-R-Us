from __future__ import annotations

import ctypes
import tkinter as tk
from typing import Callable, Optional

from . import theme
from .models import GradeResult, Mission, Recommendation


GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020


class OverlayWindow:
    def __init__(
        self,
        master: tk.Tk,
        on_move: Optional[Callable[[int, int], None]] = None,
        font_size: int = 16,
        x: int = 48,
        y: int = 48,
    ) -> None:
        self.on_move = on_move
        self.font_size = font_size
        self.locked = False
        self._drag_x = 0
        self._drag_y = 0

        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=theme.BG)
        self.win.geometry(f"460x150+{x}+{y}")

        self.frame = tk.Frame(self.win, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.GOLD_DIM)
        self.frame.pack(fill="both", expand=True, padx=2, pady=2)

        self.grade = tk.Label(
            self.frame,
            text="?",
            bg=theme.PANEL,
            fg=theme.GOLD,
            font=("Segoe UI", 36, "bold"),
            width=2,
        )
        self.grade.pack(side="left", padx=(12, 8), pady=8)

        right = tk.Frame(self.frame, bg=theme.PANEL)
        right.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=10)

        self.rec = tk.Label(right, text="WAIT", bg=theme.PANEL, fg=theme.YELLOW, font=("Segoe UI", 14, "bold"), anchor="w")
        self.rec.pack(fill="x")
        self.mission = tk.Label(right, text="Waiting for mission", bg=theme.PANEL, fg=theme.TEXT, font=("Segoe UI", 11), anchor="w")
        self.mission.pack(fill="x")
        self.tiles = tk.Label(right, text="No rooms yet", bg=theme.PANEL, fg=theme.MUTED, font=("Segoe UI", 10), anchor="w")
        self.tiles.pack(fill="x")
        self.detail = tk.Label(right, text="Start Warframe, then queue Disruption or Survival.", bg=theme.PANEL, fg=theme.MUTED, font=("Segoe UI", 9), anchor="w")
        self.detail.pack(fill="x")

        for widget in (self.win, self.frame, self.grade, right, self.rec, self.mission, self.tiles, self.detail):
            widget.bind("<ButtonPress-1>", self._start_move)
            widget.bind("<B1-Motion>", self._do_move)
            widget.bind("<ButtonRelease-1>", self._stop_move)

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        _set_clickthrough(self.win, locked)

    def set_visible(self, visible: bool) -> None:
        if visible:
            self.win.deiconify()
            self.win.attributes("-topmost", True)
        else:
            self.win.withdraw()

    def update_view(self, mission: Mission, grade: GradeResult, tiles: list[str], status: str) -> None:
        self.grade.configure(text=grade.grade, fg=theme.GRADE_COLORS.get(grade.grade, theme.MUTED))
        rec = grade.recommendation.value if isinstance(grade.recommendation, Recommendation) else str(grade.recommendation)
        self.rec.configure(text=rec, fg=theme.REC_COLORS.get(rec, theme.YELLOW))
        name = mission.display_name or mission.node_id or "Unknown node"
        kind = mission.kind.value.title() if mission.kind else "Mission"
        tileset = mission.tileset or "Unknown tileset"
        self.mission.configure(text=f"{name}  ·  {kind}  ·  {tileset}")
        self.tiles.configure(text=" + ".join(tiles[:6]) if tiles else "No rooms yet")
        self.detail.configure(text=grade.reasons[0] if grade.reasons else status)

    def _start_move(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if self.locked:
            return
        self._drag_x = event.x_root - self.win.winfo_x()
        self._drag_y = event.y_root - self.win.winfo_y()

    def _do_move(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if self.locked:
            return
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.win.geometry(f"+{x}+{y}")

    def _stop_move(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if self.on_move:
            self.on_move(self.win.winfo_x(), self.win.winfo_y())


def _set_clickthrough(window: tk.Toplevel, enabled: bool) -> None:
    try:
        hwnd = window.winfo_id()
        parent = ctypes.windll.user32.GetParent(hwnd)
        if parent:
            hwnd = parent
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED
        if enabled:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass
