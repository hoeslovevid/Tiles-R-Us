from __future__ import annotations

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Optional

from . import theme
from .bug_report import open_github, show_about, show_bug_dialog
from .catalog import CatalogStore
from .config import load_config, save_config
from .log_watcher import LogWatcher
from .meta import APP_NAME, VERSION
from .models import MissionKind, Recommendation, Tile
from .overlay import OverlayWindow
from .parser import LineParser
from .paths import default_ee_log, default_screenshot_dir, sample_dir
from .screenshot_watcher import ScreenshotWatcher
from .session import SessionController


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

        self._build()
        self.overlay = OverlayWindow(
            root,
            on_move=self._save_overlay_pos,
            font_size=int(self.cfg["overlay"].get("font_size", 16)),
            x=int(self.cfg["overlay"].get("x", 48)),
            y=int(self.cfg["overlay"].get("y", 48)),
        )
        if not self.cfg["overlay"].get("visible", True):
            self.overlay.set_visible(False)
        if self.cfg["overlay"].get("locked"):
            self.overlay_lock_var.set(True)
            self.overlay.set_locked(True)

        self._start_watchers()
        self.root.after(50, self._drain)
        self._refresh()

    def _build(self) -> None:
        self.root.title(f"{APP_NAME} {VERSION}")
        self.root.geometry("980x720")
        self.root.configure(bg=theme.BG)
        self.root.minsize(860, 620)
        if self.cfg.get("always_on_top"):
            self.root.attributes("-topmost", True)

        menubar = tk.Menu(self.root)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Report a bug…", command=self._report_bug)
        help_menu.add_command(label="Open GitHub", command=open_github)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=lambda: show_about(self.root))
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

        header = tk.Frame(self.root, bg=theme.BG)
        header.pack(fill="x", padx=18, pady=(16, 8))
        tk.Label(
            header,
            text="TILES R US",
            bg=theme.BG,
            fg=theme.GOLD,
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left")
        self.status_var = tk.StringVar(value="Starting…")
        tk.Label(header, textvariable=self.status_var, bg=theme.BG, fg=theme.MUTED, font=("Segoe UI", 10)).pack(
            side="right"
        )

        body = tk.Frame(self.root, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg=theme.BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = tk.Frame(body, bg=theme.BG, width=340)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        mission = self._card(left, "Mission", fill="x", pady=(0, 10))
        self.mission_name = self._label(mission, "Waiting for a mission", 14, theme.TEXT, bold=True)
        self.mission_meta = self._label(mission, "Queue Disruption or Survival while this app is running.", 10, theme.MUTED)

        grade_card = self._card(left, "Grade", fill="x", pady=(0, 10))
        grade_row = tk.Frame(grade_card, bg=theme.PANEL)
        grade_row.pack(fill="x")
        self.grade_letter = tk.Label(grade_row, text="?", bg=theme.PANEL, fg=theme.GOLD, font=("Segoe UI", 48, "bold"))
        self.grade_letter.pack(side="left", padx=(0, 16))
        grade_text = tk.Frame(grade_row, bg=theme.PANEL)
        grade_text.pack(side="left", fill="both", expand=True)
        self.rec_label = self._label(grade_text, "WAIT", 16, theme.YELLOW, bold=True)
        self.score_label = self._label(grade_text, "Score 0", 10, theme.MUTED)
        self.reasons = tk.Text(
            grade_card,
            height=6,
            bg=theme.PANEL_ALT,
            fg=theme.TEXT,
            bd=0,
            relief="flat",
            font=("Segoe UI", 10),
            wrap="word",
        )
        self.reasons.pack(fill="x", pady=(8, 0))
        self.reasons.configure(state="disabled")

        layout_card = self._card(left, "Layout", fill="both", expand=True)
        self.layout_label = self._label(layout_card, "No rooms identified.", 10, theme.MUTED)
        self.tile_list = tk.Listbox(
            layout_card,
            bg=theme.PANEL_ALT,
            fg=theme.TEXT,
            bd=0,
            highlightthickness=0,
            font=("Consolas", 11),
            selectbackground=theme.GOLD_DIM,
        )
        self.tile_list.pack(fill="both", expand=True, pady=(6, 0))

        tracker = self._card(right, "Live tracker", fill="x", pady=(0, 10))
        self.tracker_text = self._label(tracker, "No run in progress.", 10, theme.TEXT)

        picker = self._card(right, "Mark rooms you see", fill="both", expand=True, pady=(0, 10))
        self.picker_hint = self._label(
            picker,
            "If EE.log hides tiles, toggle the rooms in front of you.",
            9,
            theme.MUTED,
        )
        self.picker_frame = tk.Frame(picker, bg=theme.PANEL)
        self.picker_frame.pack(fill="both", expand=True, pady=(6, 0))

        settings = self._card(right, "Controls", fill="x")
        self.overlay_var = tk.BooleanVar(value=bool(self.cfg["overlay"].get("visible", True)))
        self.overlay_lock_var = tk.BooleanVar(value=bool(self.cfg["overlay"].get("locked", False)))
        self.top_var = tk.BooleanVar(value=bool(self.cfg.get("always_on_top", True)))
        self._check(settings, "Show overlay", self.overlay_var, self._toggle_overlay)
        self._check(settings, "Lock overlay (click-through)", self.overlay_lock_var, self._toggle_lock)
        self._check(settings, "Main window always on top", self.top_var, self._toggle_top)
        btn_row = tk.Frame(settings, bg=theme.PANEL)
        btn_row.pack(fill="x", pady=(8, 0))
        self._button(btn_row, "Demo: Disruption", lambda: self._play_sample("sample_disruption.log")).pack(
            side="left", padx=(0, 6)
        )
        self._button(btn_row, "Demo: Survival", lambda: self._play_sample("sample_survival.log")).pack(side="left")
        btn_row2 = tk.Frame(settings, bg=theme.PANEL)
        btn_row2.pack(fill="x", pady=(6, 0))
        self._button(btn_row2, "Open EE.log…", self._pick_log).pack(side="left", padx=(0, 6))
        self._button(btn_row2, "Replay current log", self._replay_log).pack(side="left")
        btn_row3 = tk.Frame(settings, bg=theme.PANEL)
        btn_row3.pack(fill="x", pady=(6, 0))
        self._button(btn_row3, "Report a bug", self._report_bug).pack(side="left", padx=(0, 6))
        self._button(btn_row3, "GitHub", open_github).pack(side="left")

        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _card(self, parent: tk.Widget, title: str, **pack) -> tk.Frame:
        wrap = tk.Frame(parent, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.BORDER)
        if pack:
            wrap.pack(**pack)
        inner = tk.Frame(wrap, bg=theme.PANEL)
        inner.pack(fill="both", expand=True, padx=12, pady=10)
        tk.Label(inner, text=title.upper(), bg=theme.PANEL, fg=theme.GOLD_DIM, font=("Segoe UI", 8, "bold")).pack(
            anchor="w"
        )
        return inner

    def _label(self, parent: tk.Widget, text: str, size: int, color: str, bold: bool = False) -> tk.Label:
        label = tk.Label(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=color,
            font=("Segoe UI", size, "bold" if bold else "normal"),
            anchor="w",
            justify="left",
            wraplength=520,
        )
        label.pack(fill="x")
        return label

    def _check(self, parent: tk.Widget, text: str, var: tk.BooleanVar, command) -> None:
        tk.Checkbutton(
            parent,
            text=text,
            variable=var,
            command=command,
            bg=theme.PANEL,
            fg=theme.TEXT,
            selectcolor=theme.PANEL_ALT,
            activebackground=theme.PANEL,
            activeforeground=theme.TEXT,
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", pady=1)

    def _button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=theme.PANEL_ALT,
            fg=theme.GOLD,
            activebackground=theme.GOLD_DIM,
            activeforeground=theme.BG,
            bd=0,
            padx=10,
            pady=5,
            font=("Segoe UI", 9, "bold"),
        )

    def _start_watchers(self) -> None:
        log_path = Path(self.cfg.get("ee_log_path") or default_ee_log())
        self.watcher = LogWatcher(
            log_path,
            on_line=lambda line: self.events.put(("line", line)),
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
                if kind == "line":
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
        except queue.Empty:
            pass
        if changed:
            self._refresh()
        self.root.after(50, self._drain)

    def _refresh(self) -> None:
        session = self.controller.session
        mission = session.mission
        grade = session.grade
        self.status_var.set(session.status)
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
        self.grade_letter.configure(text=grade.grade, fg=theme.GRADE_COLORS.get(grade.grade, theme.MUTED))
        self.rec_label.configure(text=rec, fg=theme.REC_COLORS.get(rec, theme.YELLOW))
        self.score_label.configure(text=f"Score {grade.score}" + (f"  ·  {grade.matched_layout}" if grade.matched_layout else ""))
        self.reasons.configure(state="normal")
        self.reasons.delete("1.0", "end")
        self.reasons.insert("1.0", "\n".join(grade.reasons) or "No grade yet.")
        self.reasons.configure(state="disabled")

        tiles = session.layout.short_names()
        extra = f"segments {session.layout.segments}" if session.layout.segments else session.layout.source
        self.layout_label.configure(text=extra or "No rooms identified.")
        self.tile_list.delete(0, "end")
        for tile in session.layout.tiles:
            self.tile_list.insert("end", f"{tile.role:<10} {tile.short_name}")

        self.tracker_text.configure(text=self._tracker_summary())
        self._rebuild_picker()
        self.overlay.update_view(mission, grade, session.layout.intermediate_names() or tiles, session.status)

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
                bg=theme.PANEL,
                fg=theme.MUTED,
                font=("Segoe UI", 9),
                wraplength=280,
                justify="left",
            ).pack(anchor="w")
            return
        selected = {tile.short_name.lower() for tile in self.controller.session.layout.tiles}
        rejected = {item.lower() for item in self.cfg.get("rejected_tiles", {}).get(catalog.key, [])}
        for room in catalog.rooms:
            row = tk.Frame(self.picker_frame, bg=theme.PANEL)
            row.pack(fill="x", pady=1)
            var = tk.BooleanVar(value=room.id.lower() in selected or room.display.lower() in selected)
            self.room_vars[room.id] = var
            tk.Checkbutton(
                row,
                text=f"{room.display}  ({room.score:+d})",
                variable=var,
                command=self._manual_tiles_changed,
                bg=theme.PANEL,
                fg=theme.RED if room.id.lower() in rejected else theme.TEXT,
                selectcolor=theme.PANEL_ALT,
                activebackground=theme.PANEL,
                activeforeground=theme.TEXT,
                font=("Segoe UI", 9),
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
            reject_var = tk.BooleanVar(value=room.id.lower() in rejected)
            tk.Checkbutton(
                row,
                text="reject",
                variable=reject_var,
                command=lambda rid=room.id, rv=reject_var, key=catalog.key: self._toggle_reject(key, rid, rv.get()),
                bg=theme.PANEL,
                fg=theme.MUTED,
                selectcolor=theme.PANEL_ALT,
                activebackground=theme.PANEL,
                font=("Segoe UI", 8),
            ).pack(side="right")

    def _manual_tiles_changed(self) -> None:
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
        self.controller._regrade()
        self._refresh()

    def _toggle_overlay(self) -> None:
        visible = self.overlay_var.get()
        self.cfg["overlay"]["visible"] = visible
        save_config(self.cfg)
        self.overlay.set_visible(visible)

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
        self._start_watchers()
        self._refresh()

    def _replay_log(self) -> None:
        path = Path(self.cfg.get("ee_log_path") or default_ee_log())
        if not path.exists():
            messagebox.showerror("No log", f"Could not find {path}")
            return
        self.parser.reset()
        self.controller.session.reset_mission()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines(True):
            for event in self.parser.feed(line):
                self.controller.handle(event)
        self.controller.session.status = f"Replayed {path.name}"
        self._refresh()

    def _report_bug(self) -> None:
        show_bug_dialog(self.root, self.controller.session)

    def _close(self) -> None:
        if self.watcher:
            self.watcher.stop()
        if self.shots:
            self.shots.stop()
        save_config(self.cfg)
        self.root.destroy()


def run() -> None:
    root = tk.Tk()
    TileReaderApp(root)
    root.mainloop()
