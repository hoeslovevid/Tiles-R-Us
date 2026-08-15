from __future__ import annotations

import queue
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Optional

from . import theme
from .bug_report import open_github, show_about, show_bug_dialog
from .catalog import CatalogStore
from .config import load_config, save_config
from .log_watcher import LogWatcher
from .meta import APP_NAME, VERSION
from .models import MissionKind, Recommendation, Tile
from .overlay import OverlayWindow
from .parser import LineParser, parse_latest_mission
from .paths import default_ee_log, default_screenshot_dir, sample_dir
from .screenshot_watcher import ScreenshotWatcher
from .session import SessionController
from .updater import (
    ReleaseInfo,
    download_setup,
    fetch_latest_release,
    format_release_summary,
    launch_installer_and_relaunch,
)


class TileReaderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.cfg = load_config()
        self.store = CatalogStore()
        self.controller = SessionController(self.store, self.cfg)
        self.parser = LineParser()
        self.events: queue.Queue[Any] = queue.Queue()
        self.watcher: Optional[LogWatcher] = None
        self.shots: Optional[ScreenshotWatcher] = None
        self.room_vars: dict[str, tk.BooleanVar] = {}
        self._picker_key = None
        self._picker_force = True
        self._ignore_picker = False
        self._reason_key = None
        self._tile_key = None
        self._opacity_save_job: Optional[str] = None
        self.overlay: Optional[OverlayWindow] = None
        self._latest_release: Optional[ReleaseInfo] = None
        self._update_busy = False
        self._progress_win: Optional[tk.Toplevel] = None
        self._progress_label: Optional[tk.Label] = None
        self._overlay_pulse = 0
        self._guide_key = None

        self._build()
        opacity = float(self.cfg["overlay"].get("opacity", 0.92))
        self.overlay = OverlayWindow(
            root,
            on_move=self._save_overlay_pos,
            font_size=int(self.cfg["overlay"].get("font_size", 16)),
            x=int(self.cfg["overlay"].get("x", 48)),
            y=int(self.cfg["overlay"].get("y", 48)),
            opacity=opacity,
        )
        if not self.cfg["overlay"].get("visible", True):
            self.overlay.set_visible(False)
        if self.cfg["overlay"].get("locked"):
            self.overlay_lock_var.set(True)
            self.overlay.set_locked(True)

        self._start_watchers()
        self.root.after(16, self._drain)
        self._refresh()

    def _build(self) -> None:
        theme.apply(self.root)
        self.root.title(f"{APP_NAME} {VERSION}")
        self.root.geometry("1120x780")
        self.root.minsize(960, 680)
        theme.round_corners(self.root)
        if self.cfg.get("always_on_top"):
            self.root.attributes("-topmost", True)

        menubar = tk.Menu(self.root)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Check for updates…", command=self._check_for_updates)
        help_menu.add_command(label="Report a bug…", command=self._report_bug)
        help_menu.add_command(label="Open GitHub", command=open_github)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=lambda: show_about(self.root))
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

        chrome = tk.Frame(self.root, bg=theme.SURFACE, highlightthickness=1, highlightbackground=theme.BORDER)
        chrome.pack(fill="x", padx=16, pady=(16, 0))
        header = tk.Frame(chrome, bg=theme.SURFACE)
        header.pack(fill="x", padx=16, pady=12)

        brand = tk.Frame(header, bg=theme.SURFACE)
        brand.pack(side="left")
        tk.Label(brand, text=APP_NAME.upper(), bg=theme.SURFACE, fg=theme.GOLD, font=theme.font(18, "bold")).pack(
            side="left"
        )
        self.version_chip = tk.Label(
            brand,
            text=f"v{VERSION}",
            bg=theme.ELEVATED,
            fg=theme.MUTED,
            font=theme.font(8, "bold"),
            padx=8,
            pady=2,
            cursor="hand2",
        )
        self.version_chip.pack(side="left", padx=(10, 0))
        self.version_chip.bind("<Button-1>", lambda _e: self._check_for_updates())

        self.status_pill = tk.Label(
            header,
            text="Starting…",
            bg=theme.ELEVATED,
            fg=theme.MUTED,
            font=theme.font(9, "bold"),
            padx=12,
            pady=5,
        )
        self.status_pill.pack(side="right")
        self.status_var = tk.StringVar(value="Starting…")

        body = tk.Frame(self.root, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=16, pady=16)
        left = tk.Frame(body, bg=theme.BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        right = tk.Frame(body, bg=theme.BG, width=360)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        mission = theme.card(left, "Mission", fill="x", pady=(0, 12))
        self.mission_name = tk.Label(mission, text="Waiting for a mission", bg=theme.SURFACE, fg=theme.TEXT, font=theme.font(16, "bold"), anchor="w")
        self.mission_name.pack(fill="x")
        self.mission_meta = tk.Label(
            mission,
            text="Queue Disruption or Survival while this app is running.",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
        )
        self.mission_meta.pack(fill="x", pady=(2, 0))

        grade_card = theme.card(left, "Grade", fill="x", pady=(0, 12))
        grade_row = tk.Frame(grade_card, bg=theme.SURFACE)
        grade_row.pack(fill="x")
        self.grade_well = tk.Frame(grade_row, bg=theme.ELEVATED)
        self.grade_well.pack(side="left", padx=(0, 16))
        self.grade_letter = tk.Label(
            self.grade_well,
            text="?",
            bg=theme.ELEVATED,
            fg=theme.GOLD,
            font=theme.font(44, "bold"),
            width=2,
            padx=10,
            pady=6,
        )
        self.grade_letter.pack()
        grade_text = tk.Frame(grade_row, bg=theme.SURFACE)
        grade_text.pack(side="left", fill="both", expand=True)
        rec_row = tk.Frame(grade_text, bg=theme.SURFACE)
        rec_row.pack(fill="x")
        self.rec_label = tk.Label(
            rec_row,
            text="WAIT",
            bg=theme.WAIT_BG,
            fg=theme.YELLOW,
            font=theme.font(11, "bold"),
            padx=10,
            pady=3,
        )
        self.rec_label.pack(side="left")
        self.score_label = tk.Label(rec_row, text="Score 0", bg=theme.SURFACE, fg=theme.MUTED, font=theme.font(10), padx=10)
        self.score_label.pack(side="left")
        self.reasons_frame = tk.Frame(grade_card, bg=theme.SURFACE)
        self.reasons_frame.pack(fill="x", pady=(12, 0))

        layout_card = theme.card(left, "Layout", fill="both", expand=True)
        self.layout_label = tk.Label(layout_card, text="No rooms identified.", bg=theme.SURFACE, fg=theme.MUTED, font=theme.font(10), anchor="w")
        self.layout_label.pack(fill="x")
        self.tile_frame = tk.Frame(layout_card, bg=theme.SURFACE)
        self.tile_frame.pack(fill="both", expand=True, pady=(8, 0))

        tracker = theme.card(right, "Live tracker", fill="x", pady=(0, 12))
        self.tracker_text = tk.Label(
            tracker,
            text="No run in progress.",
            bg=theme.SURFACE,
            fg=theme.TEXT,
            font=theme.font(10),
            anchor="w",
            justify="left",
            wraplength=300,
        )
        self.tracker_text.pack(fill="x")

        picker = theme.card(right, "", fill="both", expand=True, pady=(0, 12))
        notebook = ttk.Notebook(picker, style="Dark.TNotebook")
        notebook.pack(fill="both", expand=True)
        mark_tab = tk.Frame(notebook, bg=theme.SURFACE)
        guide_tab = tk.Frame(notebook, bg=theme.SURFACE)
        notebook.add(mark_tab, text="  Mark rooms  ")
        notebook.add(guide_tab, text="  Tile guide  ")
        tk.Label(
            mark_tab,
            text="Auto-scan reads EE.log. Toggle only if a room was missed.",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
            wraplength=300,
            justify="left",
        ).pack(fill="x", padx=4, pady=(8, 0))
        self.picker_frame = tk.Frame(mark_tab, bg=theme.SURFACE)
        self.picker_frame.pack(fill="both", expand=True, pady=(8, 0), padx=4)
        tk.Label(
            guide_tab,
            text="What each room looks like for this node.",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
            wraplength=300,
            justify="left",
        ).pack(fill="x", padx=4, pady=(8, 0))
        self.guide_frame = tk.Frame(guide_tab, bg=theme.SURFACE)
        self.guide_frame.pack(fill="both", expand=True, pady=(8, 0), padx=4)

        settings = theme.card(right, "Overlay & controls", fill="x")
        self.overlay_var = tk.BooleanVar(value=bool(self.cfg["overlay"].get("visible", True)))
        self.overlay_lock_var = tk.BooleanVar(value=bool(self.cfg["overlay"].get("locked", False)))
        self.top_var = tk.BooleanVar(value=bool(self.cfg.get("always_on_top", True)))
        theme.check(settings, "Show overlay", self.overlay_var, self._toggle_overlay)
        theme.check(settings, "Lock overlay (click-through)", self.overlay_lock_var, self._toggle_lock)
        theme.check(settings, "Main window always on top", self.top_var, self._toggle_top)

        opacity_row = tk.Frame(settings, bg=theme.SURFACE)
        opacity_row.pack(fill="x", pady=(10, 0))
        tk.Label(opacity_row, text="Overlay opacity", bg=theme.SURFACE, fg=theme.MUTED, font=theme.font(9, "bold")).pack(
            side="left"
        )
        start_opacity = max(0.25, min(1.0, float(self.cfg["overlay"].get("opacity", 0.92))))
        self.opacity_value = tk.Label(
            opacity_row,
            text=f"{int(round(start_opacity * 100))}%",
            bg=theme.SURFACE,
            fg=theme.GOLD,
            font=theme.font(9, "bold"),
        )
        self.opacity_value.pack(side="right")
        self.opacity_var = tk.DoubleVar(value=start_opacity * 100)
        ttk.Scale(
            settings,
            from_=25,
            to=100,
            variable=self.opacity_var,
            command=self._on_opacity,
            style="Overlay.Horizontal.TScale",
        ).pack(fill="x", pady=(6, 0))

        btn_row = tk.Frame(settings, bg=theme.SURFACE)
        btn_row.pack(fill="x", pady=(12, 0))
        theme.button(btn_row, "Demo: Disruption", lambda: self._play_sample("sample_disruption.log")).pack(
            side="left", padx=(0, 6)
        )
        theme.button(btn_row, "Demo: Survival", lambda: self._play_sample("sample_survival.log")).pack(side="left")
        btn_row2 = tk.Frame(settings, bg=theme.SURFACE)
        btn_row2.pack(fill="x", pady=(6, 0))
        theme.button(btn_row2, "Open EE.log…", self._pick_log).pack(side="left", padx=(0, 6))
        theme.button(btn_row2, "Rescan mission", self._rescan_mission).pack(side="left")
        btn_row3 = tk.Frame(settings, bg=theme.SURFACE)
        btn_row3.pack(fill="x", pady=(6, 0))
        theme.button(btn_row3, "Report a bug", self._report_bug).pack(side="left", padx=(0, 6))
        self.update_btn = theme.button(btn_row3, "Check for updates", self._check_for_updates)
        self.update_btn.pack(side="left", padx=(0, 6))
        theme.button(btn_row3, "GitHub", open_github).pack(side="left")

        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(1800, lambda: self._check_for_updates(quiet=True))

    def _start_watchers(self) -> None:
        log_path = Path(self.cfg.get("ee_log_path") or default_ee_log())
        self.watcher = LogWatcher(
            log_path,
            on_events=lambda events: self.events.put(("events", events)),
            on_status=lambda msg: self.events.put(("status", msg)),
            from_end=bool(self.cfg.get("read_from_end", True)),
        )
        self.watcher.start()
        shot_dir = Path(self.cfg.get("screenshot_dir") or default_screenshot_dir())
        self.shots = ScreenshotWatcher(
            shot_dir,
            on_tile=lambda tile, path: self.events.put(("shot", tile, str(path))),
            on_status=lambda msg: self.events.put(("status", msg)),
        )
        self.shots.start()

    def _drain(self) -> None:
        changed = False
        try:
            while True:
                item = self.events.get_nowait()
                kind = item[0]
                if kind == "events":
                    for event in item[1]:
                        if self.controller.handle(event):
                            changed = True
                elif kind == "line":
                    for event in self.parser.feed(item[1]):
                        if self.controller.handle(event):
                            changed = True
                elif kind == "status":
                    self.controller.session.status = item[1]
                    changed = True
                elif kind == "shot":
                    tile: Tile = item[1]
                    self.controller.add_tile(tile)
                    changed = True
                elif kind == "update":
                    self._on_update_result(item[1], item[2])
                elif kind == "update_error":
                    self._on_update_error(item[1], item[2])
                elif kind == "update_progress":
                    self._on_update_progress(item[1], item[2])
                elif kind == "update_ready":
                    self._on_update_ready(item[1])
                elif kind == "rescan":
                    self._on_rescan(item[1])
        except queue.Empty:
            pass
        if changed:
            self.store.flush_discovered()
            self._refresh()
        self._overlay_pulse += 1
        if self._overlay_pulse >= 40:
            self._overlay_pulse = 0
            if self.overlay and self.overlay_var.get():
                self.overlay.keep_on_top()
        self.root.after(16, self._drain)

    def _refresh(self) -> None:
        session = self.controller.session
        mission = session.mission
        grade = session.grade
        name = mission.display_name or mission.node_id or "No mission"
        bits = [
            mission.kind.value.title() if mission.kind else "",
            mission.tileset,
            mission.node_id,
        ]
        if mission.seed is not None:
            bits.append(f"seed {mission.seed}")
        if mission.min_level and mission.max_level:
            bits.append(f"lv {mission.min_level}-{mission.max_level}")
        self.mission_name.configure(text=name)
        self.mission_meta.configure(text="  ·  ".join(bit for bit in bits if bit) or "Waiting…")

        rec = grade.recommendation.value if isinstance(grade.recommendation, Recommendation) else str(grade.recommendation)
        rec_fg = theme.REC_COLORS.get(rec, theme.YELLOW)
        rec_bg = theme.REC_BG.get(rec, theme.WAIT_BG)
        self.status_var.set(session.status)
        self.status_pill.configure(text=session.status, fg=rec_fg, bg=rec_bg)
        self.grade_letter.configure(text=grade.grade, fg=theme.GRADE_COLORS.get(grade.grade, theme.MUTED))
        self.rec_label.configure(text=rec, fg=rec_fg, bg=rec_bg)
        self.score_label.configure(text=f"Score {grade.score}" + (f"  ·  {grade.matched_layout}" if grade.matched_layout else ""))
        self._render_reasons(grade.reasons)

        tiles = session.layout.short_names()
        extra = f"segments {session.layout.segments}" if session.layout.segments else session.layout.source
        self.layout_label.configure(text=extra or "No rooms identified.")
        self._render_tiles(session.layout.tiles)

        self.tracker_text.configure(text=self._tracker_summary())
        self._sync_picker()
        self.overlay.update_view(mission, grade, session.layout.intermediate_names() or tiles, session.status)

    def _render_reasons(self, reasons: list[str]) -> None:
        key = "\n".join(reasons)
        if key == self._reason_key:
            return
        self._reason_key = key
        for child in self.reasons_frame.winfo_children():
            child.destroy()
        items = reasons or ["No grade yet."]
        for reason in items:
            row = tk.Frame(self.reasons_frame, bg=theme.SURFACE)
            row.pack(fill="x", pady=2)
            tk.Frame(row, bg=theme.GOLD_DIM, width=2).pack(side="left", fill="y", padx=(0, 10))
            tk.Label(
                row,
                text=reason,
                bg=theme.SURFACE,
                fg=theme.TEXT,
                font=theme.font(10),
                anchor="w",
                justify="left",
                wraplength=520,
            ).pack(side="left", fill="x", expand=True)

    def _render_tiles(self, tiles: list[Tile]) -> None:
        key = tuple((tile.role, tile.short_name) for tile in tiles)
        if key == self._tile_key:
            return
        self._tile_key = key
        for child in self.tile_frame.winfo_children():
            child.destroy()
        if not tiles:
            tk.Label(
                self.tile_frame,
                text="Rooms will appear here as the mission loads.",
                bg=theme.SURFACE,
                fg=theme.MUTED,
                font=theme.font(10),
                anchor="w",
            ).pack(fill="x")
            return
        for index, tile in enumerate(tiles):
            bg = theme.ELEVATED if index % 2 == 0 else theme.SURFACE
            row = tk.Frame(self.tile_frame, bg=bg)
            row.pack(fill="x", pady=1)
            tk.Label(
                row,
                text=tile.role,
                bg=bg,
                fg=theme.GOLD,
                font=theme.font(8, "bold"),
                width=8,
                padx=8,
                pady=5,
            ).pack(side="left")
            tk.Label(
                row,
                text=tile.short_name,
                bg=bg,
                fg=theme.TEXT,
                font=(theme.FONT_MONO, 10),
                anchor="w",
                padx=8,
            ).pack(side="left", fill="x", expand=True)

    def _on_opacity(self, _value: str | None = None) -> None:
        alpha = max(0.25, min(1.0, float(self.opacity_var.get()) / 100.0))
        self.cfg["overlay"]["opacity"] = round(alpha, 2)
        self.opacity_value.configure(text=f"{int(round(alpha * 100))}%")
        if self.overlay:
            self.overlay.set_opacity(alpha)
        if self._opacity_save_job:
            try:
                self.root.after_cancel(self._opacity_save_job)
            except tk.TclError:
                pass
        self._opacity_save_job = self.root.after(400, lambda: save_config(self.cfg))

    def _tracker_summary(self) -> str:
        session = self.controller.session
        if session.mission.kind == MissionKind.DISRUPTION:
            run = session.disruption
            if not run or not run.rounds:
                toxin = "  ·  toxin" if run and run.toxin else ""
                return f"Disruption ready{toxin}. Waiting for round 1."
            current = run.current_round
            last = current.duration() if current and current.finished_at else 0
            keys = len(current.key_inserts) if current else 0
            demos = len(current.demo_kills) if current else 0
            return (
                f"Round {current.number if current else 0}  ·  keys {keys}/4  ·  demos {demos}\n"
                f"Artifacts {run.total_artifacts}  ·  last round {last:.0f}s"
                + ("  ·  TOXIN" if run.toxin else "")
            )
        if session.mission.kind == MissionKind.SURVIVAL:
            if session.survival.good_tile_found:
                return f"Good farm room found: {session.survival.good_tile_name}"
            return "Survival: looking for the catalog farm room."
        return "No Disruption / Survival run in progress."

    def _sync_picker(self) -> None:
        mission = self.controller.session.mission
        catalog = self.store.catalog_for(mission.node_id, mission.kind, mission.level_override)
        key = catalog.key if catalog else ""
        if self._picker_force or key != self._picker_key:
            self._picker_force = False
            self._picker_key = key
            self._rebuild_picker()
            self._rebuild_guide()
            return
        if not catalog or not self.room_vars:
            return
        matched = set()
        for tile in self.controller.session.layout.tiles:
            room = catalog.match_tile(tile.short_name)
            if room:
                matched.add(room.id.lower())
        self._ignore_picker = True
        try:
            for room_id, var in self.room_vars.items():
                want = room_id.lower() in matched
                if var.get() != want:
                    var.set(want)
        finally:
            self._ignore_picker = False

    def _rebuild_picker(self) -> None:
        mission = self.controller.session.mission
        catalog = self.store.catalog_for(mission.node_id, mission.kind, mission.level_override)
        for child in self.picker_frame.winfo_children():
            child.destroy()
        self.room_vars = {}
        if not catalog:
            tk.Label(
                self.picker_frame,
                text="No room catalog for this node yet.",
                bg=theme.SURFACE,
                fg=theme.MUTED,
                font=theme.font(9),
                wraplength=300,
                justify="left",
            ).pack(anchor="w")
            return
        selected = {tile.short_name.lower() for tile in self.controller.session.layout.tiles}
        rejected = {item.lower() for item in self.cfg.get("rejected_tiles", {}).get(catalog.key, [])}
        for index, room in enumerate(catalog.rooms):
            bg = theme.ELEVATED if index % 2 == 0 else theme.SURFACE
            row = tk.Frame(self.picker_frame, bg=bg)
            row.pack(fill="x", pady=1)
            var = tk.BooleanVar(value=room.id.lower() in selected or room.display.lower() in selected)
            self.room_vars[room.id] = var
            tk.Checkbutton(
                row,
                text=f"{room.display}  ({room.score:+d})",
                variable=var,
                command=self._manual_tiles_changed,
                bg=bg,
                fg=theme.RED if room.id.lower() in rejected else theme.TEXT,
                selectcolor=theme.SURFACE_2,
                activebackground=bg,
                activeforeground=theme.TEXT,
                font=theme.font(9),
                anchor="w",
                bd=0,
                highlightthickness=0,
                cursor="hand2",
            ).pack(side="left", fill="x", expand=True, padx=4, pady=2)
            reject_var = tk.BooleanVar(value=room.id.lower() in rejected)
            tk.Checkbutton(
                row,
                text="reject",
                variable=reject_var,
                command=lambda rid=room.id, rv=reject_var, key=catalog.key: self._toggle_reject(key, rid, rv.get()),
                bg=bg,
                fg=theme.MUTED,
                selectcolor=theme.SURFACE_2,
                activebackground=bg,
                font=theme.font(8),
                bd=0,
                highlightthickness=0,
                cursor="hand2",
            ).pack(side="right", padx=4)

    def _rebuild_guide(self) -> None:
        mission = self.controller.session.mission
        catalog = self.store.catalog_for(mission.node_id, mission.kind, mission.level_override)
        for child in self.guide_frame.winfo_children():
            child.destroy()
        if not catalog:
            tk.Label(
                self.guide_frame,
                text="Queue a Disruption or Survival node to see its room guide.",
                bg=theme.SURFACE,
                fg=theme.MUTED,
                font=theme.font(9),
                wraplength=300,
                justify="left",
            ).pack(anchor="w")
            return
        if catalog.notes:
            tk.Label(
                self.guide_frame,
                text=catalog.notes,
                bg=theme.SURFACE,
                fg=theme.MUTED,
                font=theme.font(9),
                wraplength=300,
                justify="left",
            ).pack(anchor="w", pady=(0, 8))
        if not catalog.rooms:
            tk.Label(
                self.guide_frame,
                text="No named rooms in this catalog yet. Auto-scan will save new names when the log still prints them.",
                bg=theme.SURFACE,
                fg=theme.MUTED,
                font=theme.font(9),
                wraplength=300,
                justify="left",
            ).pack(anchor="w")
            return
        for index, room in enumerate(catalog.rooms):
            bg = theme.ELEVATED if index % 2 == 0 else theme.SURFACE_2
            card = tk.Frame(self.guide_frame, bg=bg)
            card.pack(fill="x", pady=3)
            header = tk.Frame(card, bg=bg)
            header.pack(fill="x", padx=8, pady=(8, 0))
            tk.Label(header, text=room.display, bg=bg, fg=theme.TEXT, font=theme.font(10, "bold"), anchor="w").pack(
                side="left"
            )
            score_fg = theme.GREEN if room.score > 0 else theme.RED if room.score < 0 else theme.MUTED
            tk.Label(header, text=f"{room.score:+d}", bg=bg, fg=score_fg, font=theme.font(9, "bold")).pack(side="right")
            body = room.looks or room.notes or "No landmark notes yet."
            tk.Label(
                card,
                text=body,
                bg=bg,
                fg=theme.MUTED,
                font=theme.font(9),
                wraplength=280,
                justify="left",
                anchor="w",
            ).pack(fill="x", padx=8, pady=(2, 8))

    def _manual_tiles_changed(self) -> None:
        if self._ignore_picker:
            return
        names = [room_id for room_id, var in self.room_vars.items() if var.get()]
        self.controller.set_manual_tiles(names)
        self._refresh()

    def _toggle_reject(self, catalog_key: str, room_id: str, enabled: bool) -> None:
        bucket = self.cfg.setdefault("rejected_tiles", {}).setdefault(catalog_key, [])
        if enabled and room_id not in bucket:
            bucket.append(room_id)
        if not enabled and room_id in bucket:
            bucket.remove(room_id)
        save_config(self.cfg)
        self._picker_force = True
        self.controller._regrade()
        self._refresh()

    def _rescan_mission(self) -> None:
        path = Path(self.cfg.get("ee_log_path") or default_ee_log())
        if not path.exists():
            messagebox.showerror("No log", f"Could not find {path}")
            return
        self.controller.session.status = "Rescanning current mission from EE.log…"
        self.status_pill.configure(text="Rescanning…", fg=theme.YELLOW, bg=theme.WAIT_BG)

        def worker() -> None:
            try:
                events = parse_latest_mission(path)
                self.events.put(("rescan", events))
            except Exception as exc:
                self.events.put(("update_error", f"Rescan failed: {exc}", False))

        threading.Thread(target=worker, name="TilesRUsRescan", daemon=True).start()

    def _on_rescan(self, events: list) -> None:
        self.parser.reset()
        self.controller.session.reset_mission()
        self._picker_force = True
        for event in events:
            self.controller.handle(event)
        self.controller.session.status = "Rescanned the latest mission in EE.log"
        self._refresh()

    def _toggle_overlay(self) -> None:
        visible = self.overlay_var.get()
        self.cfg["overlay"]["visible"] = visible
        save_config(self.cfg)
        if self.overlay:
            self.overlay.set_visible(visible)
            if visible:
                self.overlay.keep_on_top()

    def _toggle_lock(self) -> None:
        locked = self.overlay_lock_var.get()
        self.cfg["overlay"]["locked"] = locked
        save_config(self.cfg)
        self.overlay.set_locked(locked)

    def _toggle_top(self) -> None:
        value = self.top_var.get()
        self.cfg["always_on_top"] = value
        save_config(self.cfg)
        self.root.attributes("-topmost", value)

    def _save_overlay_pos(self, x: int, y: int) -> None:
        self.cfg["overlay"]["x"] = x
        self.cfg["overlay"]["y"] = y
        save_config(self.cfg)

    def _play_sample(self, name: str) -> None:
        path = sample_dir() / name
        if not path.exists():
            messagebox.showerror("Missing sample", f"Could not find {path}")
            return
        self.parser.reset()
        self.controller.session.reset_mission()
        self._picker_force = True
        for line in path.read_text(encoding="utf-8").splitlines(True):
            for event in self.parser.feed(line):
                self.controller.handle(event)
        self.controller.session.status = f"Demo replay: {name}"
        self._refresh()

    def _pick_log(self) -> None:
        chosen = filedialog.askopenfilename(title="Select EE.log", filetypes=[("Log files", "*.log"), ("All files", "*.*")])
        if not chosen:
            return
        self.cfg["ee_log_path"] = chosen
        self.cfg["read_from_end"] = False
        save_config(self.cfg)
        if self.watcher:
            self.watcher.stop()
        self.parser.reset()
        self.controller.session.reset_mission()
        self._picker_force = True
        self._start_watchers()
        self._refresh()

    def _replay_log(self) -> None:
        path = Path(self.cfg.get("ee_log_path") or default_ee_log())
        if not path.exists():
            messagebox.showerror("No log", f"Could not find {path}")
            return
        self.parser.reset()
        self.controller.session.reset_mission()
        self._picker_force = True
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines(True):
            for event in self.parser.feed(line):
                self.controller.handle(event)
        self.controller.session.status = f"Replayed {path.name}"
        self._refresh()

    def _check_for_updates(self, quiet: bool = False) -> None:
        if self._update_busy:
            return
        if self._latest_release and self._latest_release.newer and not quiet:
            self._prompt_update(self._latest_release)
            return
        self._update_busy = True
        if not quiet:
            self.update_btn.configure(text="Checking…")

        def worker() -> None:
            try:
                release = fetch_latest_release()
                self.events.put(("update", release, quiet))
            except Exception as exc:
                self.events.put(("update_error", str(exc), quiet))

        threading.Thread(target=worker, name="TilesRUsUpdateCheck", daemon=True).start()

    def _on_update_result(self, release: ReleaseInfo, quiet: bool) -> None:
        self._update_busy = False
        self._latest_release = release
        self._show_update_available(release.newer)
        if quiet and not release.newer:
            return
        if release.newer:
            if quiet:
                return
            self._prompt_update(release)
            return
        if not quiet:
            messagebox.showinfo(
                "Up to date",
                f"{APP_NAME} {VERSION} is the latest release.",
                parent=self.root,
            )

    def _on_update_error(self, message: str, quiet: bool) -> None:
        self._update_busy = False
        if getattr(self, "_progress_win", None):
            try:
                self._progress_win.destroy()
            except tk.TclError:
                pass
            self._progress_win = None
        available = bool(self._latest_release and self._latest_release.newer)
        self._show_update_available(available)
        if not quiet:
            messagebox.showerror("Update failed", message, parent=self.root)

    def _show_update_available(self, available: bool) -> None:
        if available and self._latest_release:
            label = f"v{VERSION} · update {self._latest_release.version}"
            self.version_chip.configure(text=label, bg=theme.GOLD, fg=theme.BG)
            self.update_btn.configure(text=f"Update to {self._latest_release.version}")
        else:
            self.version_chip.configure(text=f"v{VERSION}", bg=theme.ELEVATED, fg=theme.MUTED)
            self.update_btn.configure(text="Check for updates")

    def _prompt_update(self, release: ReleaseInfo) -> None:
        summary = format_release_summary(release)
        ok = messagebox.askyesno(
            "Update available",
            f"{APP_NAME} {release.version} is available (you have {VERSION}).\n\n"
            f"{summary}\n\n"
            "Download and install now? The app will close, then reopen.",
            parent=self.root,
        )
        if ok:
            self._start_update(release)

    def _start_update(self, release: ReleaseInfo) -> None:
        if self._update_busy:
            return
        self._update_busy = True
        dest = Path(tempfile.gettempdir()) / "TilesRUs-Setup.exe"
        self._open_progress(f"Downloading {APP_NAME} {release.version}…")

        def worker() -> None:
            try:
                download_setup(
                    release.setup_url,
                    dest,
                    progress=lambda done, total: self.events.put(("update_progress", done, total)),
                )
                self.events.put(("update_ready", dest))
            except Exception as exc:
                self.events.put(("update_error", str(exc), False))

        threading.Thread(target=worker, name="TilesRUsUpdateDownload", daemon=True).start()

    def _open_progress(self, title: str) -> None:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=theme.BG)
        win.geometry("420x120")
        win.transient(self.root)
        win.resizable(False, False)
        tk.Label(win, text=title, bg=theme.BG, fg=theme.TEXT, font=theme.font(11, "bold")).pack(padx=18, pady=(18, 8))
        self._progress_label = tk.Label(win, text="Starting…", bg=theme.BG, fg=theme.MUTED, font=theme.font(9))
        self._progress_label.pack(padx=18)
        self._progress_win = win
        win.protocol("WM_DELETE_WINDOW", lambda: None)

    def _on_update_progress(self, done: int, total: int) -> None:
        if not getattr(self, "_progress_label", None):
            return
        if total > 0:
            pct = min(100, int(done * 100 / total))
            self._progress_label.configure(text=f"{pct}%  ·  {done // 1024} KB / {total // 1024} KB")
        else:
            self._progress_label.configure(text=f"{done // 1024} KB downloaded")

    def _on_update_ready(self, setup_path: Path) -> None:
        self._update_busy = False
        if getattr(self, "_progress_win", None):
            try:
                self._progress_win.destroy()
            except tk.TclError:
                pass
            self._progress_win = None
        try:
            launch_installer_and_relaunch(setup_path)
        except Exception as exc:
            messagebox.showerror("Update failed", str(exc), parent=self.root)
            return
        self._close()

    def _report_bug(self) -> None:
        show_bug_dialog(self.root, self.controller.session)

    def _close(self) -> None:
        if self.watcher:
            self.watcher.stop()
        if self.shots:
            self.shots.stop()
        if self._opacity_save_job:
            try:
                self.root.after_cancel(self._opacity_save_job)
            except tk.TclError:
                pass
        save_config(self.cfg)
        self.store.flush_discovered()
        self.root.destroy()


def run() -> None:
    root = tk.Tk()
    TileReaderApp(root)
    root.mainloop()
