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
        opacity: float = 0.92,
    ) -> None:
        self.on_move = on_move
        self.font_size = font_size
        self.locked = False
        self.opacity = 1.0
        self._drag_x = 0
        self._drag_y = 0

        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=theme.BG)
        self.win.geometry(f"500x148+{x}+{y}")

        shell = tk.Frame(self.win, bg=theme.BORDER)
        shell.pack(fill="both", expand=True)
        self.accent = tk.Frame(shell, bg=theme.YELLOW, width=5)
        self.accent.pack(side="left", fill="y")

        self.frame = tk.Frame(shell, bg=theme.SURFACE)
        self.frame.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(self.frame, bg=theme.SURFACE)
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        top = tk.Frame(inner, bg=theme.SURFACE)
        top.pack(fill="x")

        self.grade = tk.Label(
            top,
            text="?",
            bg=theme.ELEVATED,
            fg=theme.GOLD,
            font=theme.font(32, "bold"),
            width=2,
            padx=8,
            pady=4,
        )
        self.grade.pack(side="left", padx=(0, 12))

        copy = tk.Frame(top, bg=theme.SURFACE)
        copy.pack(side="left", fill="both", expand=True)

        rec_row = tk.Frame(copy, bg=theme.SURFACE)
        rec_row.pack(fill="x")
        self.rec = tk.Label(
            rec_row,
            text="WAIT",
            bg=theme.WAIT_BG,
            fg=theme.YELLOW,
            font=theme.font(10, "bold"),
            padx=8,
            pady=2,
        )
        self.rec.pack(side="left")
        self.handle = tk.Label(
            rec_row,
            text="⋮⋮  drag",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=theme.font(8),
        )
        self.handle.pack(side="right")

        self.mission = tk.Label(
            copy,
            text="Waiting for mission",
            bg=theme.SURFACE,
            fg=theme.TEXT,
            font=theme.font(12, "bold"),
            anchor="w",
        )
        self.mission.pack(fill="x", pady=(6, 0))
        self.tiles = tk.Label(
            copy,
            text="No rooms yet",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
        )
        self.tiles.pack(fill="x")
        self.detail = tk.Label(
            inner,
            text="Start Warframe, then queue Disruption or Survival.",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
        )
        self.detail.pack(fill="x", pady=(8, 0))

        self._bind_drag(self.win, shell, self.accent, self.frame, inner, top, copy, rec_row)
        self._bind_drag(self.grade, self.rec, self.handle, self.mission, self.tiles, self.detail)
        self.set_opacity(opacity)

    def _bind_drag(self, *widgets: tk.Widget) -> None:
        for widget in widgets:
            widget.bind("<ButtonPress-1>", self._start_move)
            widget.bind("<B1-Motion>", self._do_move)
            widget.bind("<ButtonRelease-1>", self._stop_move)

    def set_opacity(self, alpha: float) -> None:
        self.opacity = max(0.25, min(1.0, float(alpha)))
        try:
            self.win.attributes("-alpha", self.opacity)
        except tk.TclError:
            pass

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        self.handle.configure(text="" if locked else "⋮⋮  drag")
        _set_clickthrough(self.win, locked)
        self.set_opacity(self.opacity)

    def set_visible(self, visible: bool) -> None:
        if visible:
            self.win.deiconify()
            self.win.attributes("-topmost", True)
            self.set_opacity(self.opacity)
        else:
            self.win.withdraw()

    def update_view(self, mission: Mission, grade: GradeResult, tiles: list[str], status: str) -> None:
        rec = grade.recommendation.value if isinstance(grade.recommendation, Recommendation) else str(grade.recommendation)
        rec_fg = theme.REC_COLORS.get(rec, theme.YELLOW)
        rec_bg = theme.REC_BG.get(rec, theme.WAIT_BG)
        self.accent.configure(bg=rec_fg)
        self.grade.configure(text=grade.grade, fg=theme.GRADE_COLORS.get(grade.grade, theme.MUTED))
        self.rec.configure(text=rec, fg=rec_fg, bg=rec_bg)
        name = mission.display_name or mission.node_id or "Unknown node"
        kind = mission.kind.value.title() if mission.kind else "Mission"
        tileset = mission.tileset or "Unknown tileset"
        self.mission.configure(text=f"{name}  ·  {kind}")
        self.tiles.configure(text=f"{tileset}   {' + '.join(tiles[:6]) if tiles else 'No rooms yet'}")
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
