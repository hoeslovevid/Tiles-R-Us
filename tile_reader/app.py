from __future__ import annotations

import queue
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .bug_report import open_github, show_about, show_bug_dialog
from .catalog import CatalogStore, RoomInfo
from .config import load_config, save_config
from .log_watcher import LogWatcher
from .meta import APP_NAME, VERSION
from .models import MissionKind, Recommendation, Tile
from .overlay import OverlayWindow
from .parser import LineParser, parse_latest_mission
from .paths import app_icon_path, default_ee_log, default_screenshot_dir, sample_dir, wordmark_path
from .screenshot_watcher import ScreenshotWatcher
from .session import SessionController
from .updater import (
    ReleaseInfo,
    download_setup,
    fetch_latest_release,
    format_release_summary,
    launch_installer_and_relaunch,
)


class RoomCard(QFrame):
    def __init__(
        self,
        room: RoomInfo,
        selected: bool,
        rejected: bool,
        on_toggle,
        on_reject,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.room = room
        self.selected = selected
        self.rejected = rejected
        self._on_toggle = on_toggle
        self.setObjectName("room")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_state()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        header = QHBoxLayout()
        name = QLabel(room.display)
        name.setStyleSheet(f"font-weight: 700; color: {theme.RED if rejected else theme.TEXT};")
        header.addWidget(name, 1)
        score_fg = theme.GREEN if room.score > 0 else theme.RED if room.score < 0 else theme.MUTED
        score = QLabel(f"{room.score:+d}")
        score.setStyleSheet(f"color: {score_fg}; font-weight: 700; font-size: 12px;")
        header.addWidget(score)
        reject_btn = QPushButton("REJECT")
        reject_btn.setObjectName("reject")
        reject_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reject_btn.setProperty("on", "true" if rejected else "false")
        reject_btn.clicked.connect(on_reject)
        header.addWidget(reject_btn)
        layout.addLayout(header)

        looks = QLabel(room.looks or room.notes or "No landmark notes yet.")
        looks.setObjectName("muted")
        looks.setWordWrap(True)
        looks.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px;")
        layout.addWidget(looks)

    def _apply_state(self) -> None:
        self.setProperty("selected", "true" if self.selected else "false")
        self.setProperty("rejected", "true" if self.rejected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_toggle()
        super().mousePressEvent(event)


class Companion(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = load_config()
        self.store = CatalogStore()
        self.controller = SessionController(self.store, self.cfg)
        self.parser = LineParser()
        self.events: queue.Queue[Any] = queue.Queue()
        self.watcher: Optional[LogWatcher] = None
        self.shots: Optional[ScreenshotWatcher] = None
        self._picker_key = None
        self._picker_force = True
        self._ignore_picker = False
        self._reason_key = None
        self._selected_rooms: set[str] = set()
        self._opacity_save_job: Optional[QTimer] = None
        self._latest_release: Optional[ReleaseInfo] = None
        self._update_busy = False
        self._progress: Optional[QDialog] = None
        self._progress_label: Optional[QLabel] = None
        self._overlay_pulse = 0
        self.overlay: Optional[OverlayWindow] = None
        self._room_cards: dict[str, RoomCard] = {}

        self._build()
        opacity = float(self.cfg["overlay"].get("opacity", 0.92))
        self.overlay = OverlayWindow(
            on_move=self._save_overlay_pos,
            font_size=int(self.cfg["overlay"].get("font_size", 16)),
            x=int(self.cfg["overlay"].get("x", 48)),
            y=int(self.cfg["overlay"].get("y", 48)),
            opacity=opacity,
        )
        if not self.cfg["overlay"].get("visible", True):
            self.overlay_check.setChecked(False)
            self.overlay.set_visible(False)
        if self.cfg["overlay"].get("locked"):
            self.lock_check.setChecked(True)
            self.overlay.set_locked(True)

        self._start_watchers()
        self._drain_timer = QTimer(self)
        self._drain_timer.timeout.connect(self._drain)
        self._drain_timer.start(16)
        QTimer.singleShot(1800, lambda: self._check_for_updates(quiet=True))
        self._refresh()

    def _build(self) -> None:
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        icon = QIcon(str(app_icon_path()))
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setMinimumSize(420, 720)
        self.resize(460, 860)
        if self.cfg.get("always_on_top"):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(0)

        header = QHBoxLayout()
        mark = QLabel()
        mark.setObjectName("wordmark")
        pix = QPixmap(str(wordmark_path()))
        if not pix.isNull():
            mark.setPixmap(pix.scaledToHeight(36, Qt.TransformationMode.SmoothTransformation))
        else:
            mark.setText(APP_NAME)
            mark.setStyleSheet(
                f"color: {theme.GOLD}; font-size: 15px; font-weight: 700; letter-spacing: 2px;"
            )
        header.addWidget(mark)
        self.version_chip = QPushButton(f"v{VERSION}")
        self.version_chip.setObjectName("ghost")
        self.version_chip.clicked.connect(lambda: self._check_for_updates(False))
        header.addWidget(self.version_chip)
        header.addStretch()
        more = QPushButton("···")
        more.setObjectName("ghost")
        more.setFixedWidth(36)
        more.clicked.connect(self._show_menu)
        header.addWidget(more)
        layout.addLayout(header)

        self.status_label = QLabel("STARTING")
        self.status_label.setObjectName("status")
        self.status_label.setStyleSheet(f"color: {theme.MUTED}; padding: 10px 0 12px 0;")
        layout.addWidget(self.status_label)

        line = QFrame()
        line.setObjectName("hairline")
        layout.addWidget(line)

        hero = QVBoxLayout()
        hero.setContentsMargins(0, 18, 0, 8)
        hero.setSpacing(4)
        self.grade_letter = QLabel("?")
        self.grade_letter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grade_letter.setFont(theme.display_font(72))
        self.grade_letter.setStyleSheet(f"color: {theme.GOLD};")
        hero.addWidget(self.grade_letter)

        self.rec_label = QLabel("WAIT")
        self.rec_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rec_label.setStyleSheet(
            f"color: {theme.YELLOW}; background: {theme.WAIT_BG}; font-size: 13px; "
            f"font-weight: 700; letter-spacing: 3px; padding: 8px;"
        )
        hero.addWidget(self.rec_label)
        layout.addLayout(hero)

        self.mission_name = QLabel("Waiting for a mission")
        self.mission_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mission_name.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.mission_name.setWordWrap(True)
        layout.addWidget(self.mission_name)
        self.mission_meta = QLabel("Queue Disruption or Survival while this app is running.")
        self.mission_meta.setObjectName("muted")
        self.mission_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mission_meta.setWordWrap(True)
        self.mission_meta.setStyleSheet(f"color: {theme.MUTED}; font-size: 12px; padding-bottom: 8px;")
        layout.addWidget(self.mission_meta)

        self.tracker_text = QLabel("No run in progress.")
        self.tracker_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tracker_text.setStyleSheet(f"color: {theme.TEXT}; font-size: 12px;")
        self.tracker_text.setWordWrap(True)
        layout.addWidget(self.tracker_text)

        self.score_label = QLabel("Score 0")
        self.score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.score_label.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px; padding-bottom: 10px;")
        layout.addWidget(self.score_label)

        self.reasons_label = QLabel("No grade yet.")
        self.reasons_label.setWordWrap(True)
        self.reasons_label.setStyleSheet(f"color: {theme.MUTED}; font-size: 12px; padding: 0 4px 14px 4px;")
        layout.addWidget(self.reasons_label)

        rooms_head = QHBoxLayout()
        eyebrow = QLabel("ROOMS")
        eyebrow.setObjectName("eyebrow")
        rooms_head.addWidget(eyebrow)
        rooms_head.addStretch()
        self.rooms_hint = QLabel("Tap a tile to mark it")
        self.rooms_hint.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px;")
        rooms_head.addWidget(self.rooms_hint)
        layout.addLayout(rooms_head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rooms_host = QWidget()
        self.rooms_layout = QVBoxLayout(self.rooms_host)
        self.rooms_layout.setContentsMargins(0, 8, 0, 8)
        self.rooms_layout.setSpacing(8)
        self.rooms_empty = QLabel("Queue a Disruption or Survival node to see its rooms.")
        self.rooms_empty.setWordWrap(True)
        self.rooms_empty.setStyleSheet(f"color: {theme.MUTED}; font-size: 12px;")
        self.rooms_layout.addWidget(self.rooms_empty)
        self.rooms_layout.addStretch()
        scroll.setWidget(self.rooms_host)
        layout.addWidget(scroll, 1)

        foot_line = QFrame()
        foot_line.setObjectName("hairline")
        layout.addWidget(foot_line)

        footer = QVBoxLayout()
        footer.setContentsMargins(0, 12, 0, 0)
        footer.setSpacing(8)
        checks = QHBoxLayout()
        self.overlay_check = QCheckBox("Overlay")
        self.overlay_check.setChecked(bool(self.cfg["overlay"].get("visible", True)))
        self.overlay_check.toggled.connect(self._toggle_overlay)
        checks.addWidget(self.overlay_check)
        self.lock_check = QCheckBox("Lock")
        self.lock_check.setChecked(bool(self.cfg["overlay"].get("locked")))
        self.lock_check.toggled.connect(self._toggle_lock)
        checks.addWidget(self.lock_check)
        checks.addStretch()
        start_opacity = max(0.25, min(1.0, float(self.cfg["overlay"].get("opacity", 0.92))))
        self.opacity_value = QLabel(f"{int(round(start_opacity * 100))}%")
        self.opacity_value.setStyleSheet(f"color: {theme.GOLD}; font-weight: 700; font-size: 12px;")
        checks.addWidget(self.opacity_value)
        footer.addLayout(checks)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(25, 100)
        self.opacity_slider.setValue(int(round(start_opacity * 100)))
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        footer.addWidget(self.opacity_slider)

        rescan = QPushButton("Rescan mission")
        rescan.clicked.connect(self._rescan_mission)
        footer.addWidget(rescan)
        layout.addLayout(footer)

        QTimer.singleShot(0, lambda: theme.round_corners(self))

    def _show_menu(self) -> None:
        menu = QMenu(self)
        top = QAction("Main window always on top", self)
        top.setCheckable(True)
        top.setChecked(bool(self.cfg.get("always_on_top")))
        top.toggled.connect(self._toggle_top)
        menu.addAction(top)
        menu.addSeparator()
        menu.addAction("Demo: Disruption", lambda: self._play_sample("sample_disruption.log"))
        menu.addAction("Demo: Survival", lambda: self._play_sample("sample_survival.log"))
        menu.addAction("Open EE.log…", self._pick_log)
        menu.addSeparator()
        update_label = "Check for updates"
        if self._latest_release and self._latest_release.newer:
            update_label = f"Update to {self._latest_release.version}"
        menu.addAction(update_label, lambda: self._check_for_updates(False))
        menu.addAction("Report a bug…", self._report_bug)
        menu.addAction("Open GitHub", open_github)
        menu.addSeparator()
        menu.addAction("About", lambda: show_about(self))
        menu.exec(self.cursor().pos())

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
            if self.overlay and self.overlay_check.isChecked():
                self.overlay.keep_on_top()

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
        self.mission_name.setText(name)
        self.mission_meta.setText("  ·  ".join(bit for bit in bits if bit) or "Waiting…")

        rec = grade.recommendation.value if isinstance(grade.recommendation, Recommendation) else str(grade.recommendation)
        rec_fg = theme.REC_COLORS.get(rec, theme.YELLOW)
        rec_bg = theme.REC_BG.get(rec, theme.WAIT_BG)
        grade_fg = theme.GRADE_COLORS.get(grade.grade, theme.MUTED)
        self.status_label.setText(session.status.upper())
        self.status_label.setStyleSheet(f"color: {rec_fg}; padding: 10px 0 12px 0; font-weight: 700; letter-spacing: 1.4px; font-size: 11px;")
        self.grade_letter.setText(grade.grade)
        self.grade_letter.setStyleSheet(f"color: {grade_fg};")
        self.rec_label.setText(rec)
        self.rec_label.setStyleSheet(
            f"color: {rec_fg}; background: {rec_bg}; font-size: 13px; font-weight: 700; "
            f"letter-spacing: 3px; padding: 8px;"
        )
        extra = f"  ·  {grade.matched_layout}" if grade.matched_layout else ""
        self.score_label.setText(f"Score {grade.score}{extra}")
        reasons = grade.reasons or ["No grade yet."]
        self.reasons_label.setText("\n".join(f"·  {item}" for item in reasons[:4]))
        self.tracker_text.setText(self._tracker_summary())
        self._sync_rooms()
        tiles = session.layout.short_names()
        if self.overlay:
            self.overlay.update_view(mission, grade, session.layout.intermediate_names() or tiles, session.status)

    def _tracker_summary(self) -> str:
        session = self.controller.session
        if session.mission.kind == MissionKind.DISRUPTION:
            run = session.disruption
            if not run or not run.rounds:
                toxin = "  ·  toxin" if run and run.toxin else ""
                return f"Disruption ready{toxin}"
            current = run.current_round
            last = current.duration() if current and current.finished_at else 0
            keys = len(current.key_inserts) if current else 0
            demos = len(current.demo_kills) if current else 0
            toxin = "  ·  TOXIN" if run.toxin else ""
            return f"Round {current.number if current else 0}  ·  keys {keys}/4  ·  demos {demos}{toxin}"
        if session.mission.kind == MissionKind.SURVIVAL:
            if session.survival.good_tile_found:
                return f"Farm room: {session.survival.good_tile_name}"
            return "Survival · looking for the farm room"
        return "No Disruption / Survival run"

    def _sync_rooms(self) -> None:
        mission = self.controller.session.mission
        catalog = self.store.catalog_for(mission.node_id, mission.kind, mission.level_override)
        key = catalog.key if catalog else ""
        matched: set[str] = set()
        if catalog:
            for tile in self.controller.session.layout.tiles:
                room = catalog.match_tile(tile.short_name)
                if room:
                    matched.add(room.id.lower())
        if self._picker_force or key != self._picker_key:
            self._picker_force = False
            self._picker_key = key
            self._selected_rooms = matched
            self._rebuild_rooms(catalog)
            return
        if matched != self._selected_rooms:
            self._selected_rooms = matched
            self._rebuild_rooms(catalog)

    def _rebuild_rooms(self, catalog) -> None:
        while self.rooms_layout.count():
            item = self.rooms_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._room_cards = {}
        if not catalog:
            empty = QLabel("Queue a Disruption or Survival node to see its rooms.")
            empty.setWordWrap(True)
            empty.setStyleSheet(f"color: {theme.MUTED}; font-size: 12px;")
            self.rooms_layout.addWidget(empty)
            self.rooms_layout.addStretch()
            return
        if catalog.notes:
            notes = QLabel(catalog.notes)
            notes.setWordWrap(True)
            notes.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px;")
            self.rooms_layout.addWidget(notes)
        rejected = {item.lower() for item in self.cfg.get("rejected_tiles", {}).get(catalog.key, [])}
        if not catalog.rooms:
            empty = QLabel("No named rooms in this catalog yet.")
            empty.setWordWrap(True)
            empty.setStyleSheet(f"color: {theme.MUTED}; font-size: 12px;")
            self.rooms_layout.addWidget(empty)
        for room in catalog.rooms:
            card = RoomCard(
                room,
                selected=room.id.lower() in self._selected_rooms,
                rejected=room.id.lower() in rejected,
                on_toggle=lambda rid=room.id: self._on_room_clicked(rid),
                on_reject=lambda rid=room.id, key=catalog.key: self._toggle_reject(key, rid),
            )
            self._room_cards[room.id] = card
            self.rooms_layout.addWidget(card)
        self.rooms_layout.addStretch()

    def _on_room_clicked(self, room_id: str) -> None:
        needle = room_id.lower()
        if needle in self._selected_rooms:
            self._selected_rooms.discard(needle)
        else:
            self._selected_rooms.add(needle)
        names = [rid for rid in self._room_cards if rid.lower() in self._selected_rooms]
        self.controller.set_manual_tiles(names)
        self._picker_force = True
        self._refresh()

    def _toggle_reject(self, catalog_key: str, room_id: str) -> None:
        bucket = self.cfg.setdefault("rejected_tiles", {}).setdefault(catalog_key, [])
        if room_id in bucket:
            bucket.remove(room_id)
        else:
            bucket.append(room_id)
        save_config(self.cfg)
        self._picker_force = True
        self.controller._regrade()
        self._refresh()

    def _on_opacity(self, value: int) -> None:
        alpha = max(0.25, min(1.0, value / 100.0))
        self.cfg["overlay"]["opacity"] = round(alpha, 2)
        self.opacity_value.setText(f"{int(round(alpha * 100))}%")
        if self.overlay:
            self.overlay.set_opacity(alpha)
        if self._opacity_save_job:
            self._opacity_save_job.stop()
        self._opacity_save_job = QTimer(self)
        self._opacity_save_job.setSingleShot(True)
        self._opacity_save_job.timeout.connect(lambda: save_config(self.cfg))
        self._opacity_save_job.start(400)

    def _toggle_overlay(self, visible: bool) -> None:
        self.cfg["overlay"]["visible"] = visible
        save_config(self.cfg)
        if self.overlay:
            self.overlay.set_visible(visible)
            if visible:
                self.overlay.keep_on_top()

    def _toggle_lock(self, locked: bool) -> None:
        self.cfg["overlay"]["locked"] = locked
        save_config(self.cfg)
        if self.overlay:
            self.overlay.set_locked(locked)

    def _toggle_top(self, value: bool) -> None:
        self.cfg["always_on_top"] = value
        save_config(self.cfg)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, value)
        self.show()

    def _save_overlay_pos(self, x: int, y: int) -> None:
        self.cfg["overlay"]["x"] = x
        self.cfg["overlay"]["y"] = y
        save_config(self.cfg)

    def _play_sample(self, name: str) -> None:
        path = sample_dir() / name
        if not path.exists():
            QMessageBox.critical(self, "Missing sample", f"Could not find {path}")
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
        chosen, _ = QFileDialog.getOpenFileName(self, "Select EE.log", "", "Log files (*.log);;All files (*.*)")
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

    def _rescan_mission(self) -> None:
        path = Path(self.cfg.get("ee_log_path") or default_ee_log())
        if not path.exists():
            QMessageBox.critical(self, "No log", f"Could not find {path}")
            return
        self.controller.session.status = "Rescanning current mission from EE.log…"
        self.status_label.setText("RESCANNING")

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

    def _check_for_updates(self, quiet: bool = False) -> None:
        if self._update_busy:
            return
        if self._latest_release and self._latest_release.newer and not quiet:
            self._prompt_update(self._latest_release)
            return
        self._update_busy = True
        self.version_chip.setText("checking…")

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
            QMessageBox.information(self, "Up to date", f"{APP_NAME} {VERSION} is the latest release.")

    def _on_update_error(self, message: str, quiet: bool) -> None:
        self._update_busy = False
        if self._progress:
            self._progress.close()
            self._progress = None
        available = bool(self._latest_release and self._latest_release.newer)
        self._show_update_available(available)
        if not quiet:
            QMessageBox.critical(self, "Update failed", message)

    def _show_update_available(self, available: bool) -> None:
        if available and self._latest_release:
            self.version_chip.setText(f"v{VERSION} · {self._latest_release.version}")
            self.version_chip.setStyleSheet(f"color: {theme.BG}; background: {theme.GOLD}; border: none; padding: 4px 8px;")
        else:
            self.version_chip.setText(f"v{VERSION}")
            self.version_chip.setStyleSheet("")

    def _prompt_update(self, release: ReleaseInfo) -> None:
        summary = format_release_summary(release)
        reply = QMessageBox.question(
            self,
            "Update available",
            f"{APP_NAME} {release.version} is available (you have {VERSION}).\n\n"
            f"{summary}\n\n"
            "Download and install now? The app will close, then reopen.",
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._start_update(release)

    def _start_update(self, release: ReleaseInfo) -> None:
        if self._update_busy:
            return
        self._update_busy = True
        dest = Path(tempfile.gettempdir()) / "TilesRUs-Setup.exe"
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Downloading {APP_NAME} {release.version}")
        dlg.setModal(True)
        box = QVBoxLayout(dlg)
        label = QLabel(f"Downloading {APP_NAME} {release.version}…")
        box.addWidget(label)
        self._progress_label = QLabel("Starting…")
        self._progress_label.setStyleSheet(f"color: {theme.MUTED};")
        box.addWidget(self._progress_label)
        dlg.resize(420, 120)
        self._progress = dlg
        dlg.show()

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

    def _on_update_progress(self, done: int, total: int) -> None:
        if not self._progress_label:
            return
        if total > 0:
            pct = min(100, int(done * 100 / total))
            self._progress_label.setText(f"{pct}%  ·  {done // 1024} KB / {total // 1024} KB")
        else:
            self._progress_label.setText(f"{done // 1024} KB downloaded")

    def _on_update_ready(self, setup_path: Path) -> None:
        self._update_busy = False
        if self._progress:
            self._progress.close()
            self._progress = None
        try:
            launch_installer_and_relaunch(setup_path)
        except Exception as exc:
            QMessageBox.critical(self, "Update failed", str(exc))
            return
        self.close()

    def _report_bug(self) -> None:
        show_bug_dialog(self, self.controller.session)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.watcher:
            self.watcher.stop()
        if self.shots:
            self.shots.stop()
        save_config(self.cfg)
        self.store.flush_discovered()
        if self.overlay:
            self.overlay.close()
        event.accept()


def run() -> None:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    icon = QIcon(str(app_icon_path()))
    if not icon.isNull():
        app.setWindowIcon(icon)
    theme.apply(app)
    window = Companion()
    window.show()
    app.exec()
