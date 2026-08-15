from __future__ import annotations

import ctypes
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


BG = "#0a0b10"
SURFACE = "#12141c"
SURFACE_2 = "#191c27"
ELEVATED = "#222636"
BORDER = "#2e3344"
BORDER_SOFT = "#3a4156"
GOLD = "#d4b46a"
GOLD_DIM = "#9a804c"
GOLD_HOVER = "#e0c484"
TEXT = "#f3f1eb"
MUTED = "#8d93a6"
RED = "#f07167"
GREEN = "#5ee0a8"
YELLOW = "#e6c15a"
ORANGE = "#f0a05a"
STAY_BG = "#123528"
ABORT_BG = "#3a1518"
WAIT_BG = "#3a2e12"

# Back-compat aliases used around the app
PANEL = SURFACE
PANEL_ALT = SURFACE_2

FONT = "Segoe UI"
FONT_MONO = "Consolas"

GRADE_COLORS = {
    "S": GOLD,
    "A": GREEN,
    "B": "#7ad3a0",
    "C": YELLOW,
    "D": ORANGE,
    "F": RED,
    "?": MUTED,
    "—": MUTED,
}

REC_COLORS = {
    "STAY": GREEN,
    "ABORT": RED,
    "WAIT": YELLOW,
}

REC_BG = {
    "STAY": STAY_BG,
    "ABORT": ABORT_BG,
    "WAIT": WAIT_BG,
}


def font(size: int, weight: str = "normal") -> tuple[str, int, str]:
    return (FONT, size, weight)


def apply(root: tk.Tk) -> None:
    root.configure(bg=BG)
    try:
        root.option_add("*Font", font(10))
    except tk.TclError:
        pass
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        return
    style.configure(
        "Overlay.Horizontal.TScale",
        background=SURFACE,
        troughcolor=ELEVATED,
        bordercolor=SURFACE,
        lightcolor=GOLD,
        darkcolor=GOLD,
        sliderthickness=18,
        groovewidth=6,
    )
    style.map(
        "Overlay.Horizontal.TScale",
        background=[("active", SURFACE)],
        lightcolor=[("active", GOLD_HOVER)],
    )
    style.configure("Dark.TNotebook", background=BG, borderwidth=0)
    style.configure(
        "Dark.TNotebook.Tab",
        background=SURFACE_2,
        foreground=MUTED,
        padding=(16, 8),
        font=font(9, "bold"),
        borderwidth=0,
        lightcolor=SURFACE_2,
        darkcolor=SURFACE_2,
    )
    style.map(
        "Dark.TNotebook.Tab",
        background=[("selected", SURFACE), ("active", ELEVATED)],
        foreground=[("selected", GOLD), ("active", TEXT)],
    )


def round_corners(window: tk.Misc, preference: int = 2) -> None:
    try:
        window.update_idletasks()
        hwnd = int(window.winfo_id())
        parent = ctypes.windll.user32.GetParent(hwnd)
        if parent:
            hwnd = parent
        value = ctypes.c_int(preference)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def card(parent: tk.Widget, title: str = "", **pack) -> tk.Frame:
    wrap = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
    if pack:
        wrap.pack(**pack)
    inner = tk.Frame(wrap, bg=SURFACE)
    inner.pack(fill="both", expand=True, padx=16, pady=14)
    if title:
        tk.Label(inner, text=title.upper(), bg=SURFACE, fg=GOLD_DIM, font=font(8, "bold")).pack(anchor="w", pady=(0, 8))
    return inner


def button(parent: tk.Widget, text: str, command: Callable[[], None], kind: str = "secondary") -> tk.Button:
    if kind == "primary":
        bg, fg, hover, active_fg = GOLD, BG, GOLD_HOVER, BG
    elif kind == "danger":
        bg, fg, hover, active_fg = ABORT_BG, RED, "#4a1c20", TEXT
    else:
        bg, fg, hover, active_fg = ELEVATED, TEXT, BORDER_SOFT, TEXT
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=hover,
        activeforeground=active_fg,
        bd=0,
        relief="flat",
        padx=12,
        pady=7,
        font=font(9, "bold"),
        cursor="hand2",
        highlightthickness=0,
    )
    btn.bind("<Enter>", lambda _e, widget=btn, color=hover: widget.configure(bg=color))
    btn.bind("<Leave>", lambda _e, widget=btn, color=bg: widget.configure(bg=color))
    return btn


def check(parent: tk.Widget, text: str, var: tk.BooleanVar, command: Optional[Callable[[], None]] = None) -> tk.Checkbutton:
    widget = tk.Checkbutton(
        parent,
        text=text,
        variable=var,
        command=command,
        bg=parent.cget("bg"),
        fg=TEXT,
        selectcolor=ELEVATED,
        activebackground=parent.cget("bg"),
        activeforeground=TEXT,
        font=font(10),
        anchor="w",
        cursor="hand2",
        highlightthickness=0,
        bd=0,
    )
    widget.pack(fill="x", pady=2)
    return widget
