from __future__ import annotations

import ctypes
from typing import Callable, Optional

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme
from .models import GradeResult, Mission, Recommendation
from .paths import app_icon_path


GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
LWA_ALPHA = 0x00000002


class OverlayWindow(QWidget):
    def __init__(
        self,
        on_move: Optional[Callable[[int, int], None]] = None,
        font_size: int = 16,
        x: int = 48,
        y: int = 48,
        opacity: float = 0.92,
    ) -> None:
        super().__init__(None)
        self.on_move = on_move
        self.font_size = font_size
        self.locked = False
        self.opacity = max(0.25, min(1.0, float(opacity)))
        self._drag: Optional[QPoint] = None
        self._hwnd = 0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(480, 132)
        self.move(x, y)
        icon = QIcon(str(app_icon_path()))
        if not icon.isNull():
            self.setWindowIcon(icon)

        self.setStyleSheet(
            f"OverlayWindow {{ background: {theme.SURFACE}; border: 1px solid {theme.GOLD_DIM}; }}"
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.accent = QFrame()
        self.accent.setFixedWidth(5)
        self.accent.setStyleSheet(f"background: {theme.YELLOW};")
        root.addWidget(self.accent)

        inner = QVBoxLayout()
        inner.setContentsMargins(14, 10, 14, 10)
        inner.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.grade = QLabel("?")
        self.grade.setFixedWidth(56)
        self.grade.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grade.setFont(theme.display_font(28))
        self.grade.setStyleSheet(f"color: {theme.GOLD}; background: {theme.ELEVATED}; padding: 4px 0;")
        top.addWidget(self.grade)

        copy = QVBoxLayout()
        copy.setSpacing(2)
        rec_row = QHBoxLayout()
        self.rec = QLabel("WAIT")
        self.rec.setObjectName("status")
        self.rec.setStyleSheet(
            f"color: {theme.YELLOW}; background: {theme.WAIT_BG}; padding: 3px 8px; font-weight: 700;"
        )
        rec_row.addWidget(self.rec, alignment=Qt.AlignmentFlag.AlignLeft)
        rec_row.addStretch()
        self.handle = QLabel("DRAG")
        self.handle.setStyleSheet(f"color: {theme.MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        rec_row.addWidget(self.handle)
        copy.addLayout(rec_row)

        self.mission = QLabel("Waiting for mission")
        self.mission.setStyleSheet(f"color: {theme.TEXT}; font-size: 13px; font-weight: 700;")
        copy.addWidget(self.mission)
        self.tiles = QLabel("No rooms yet")
        self.tiles.setObjectName("muted")
        self.tiles.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px;")
        copy.addWidget(self.tiles)
        top.addLayout(copy, 1)
        inner.addLayout(top)

        self.detail = QLabel("Use Borderless Windowed in Warframe so this HUD stays on top.")
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px;")
        inner.addWidget(self.detail)
        root.addLayout(inner, 1)

        self.show()
        theme.round_corners(self)
        self._apply_win32()

    def set_opacity(self, alpha: float) -> None:
        self.opacity = max(0.25, min(1.0, float(alpha)))
        self._apply_win32()

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        self.handle.setText("" if locked else "DRAG")
        self._apply_win32()

    def set_visible(self, visible: bool) -> None:
        if visible:
            self.show()
            self._apply_win32()
        else:
            self.hide()

    def keep_on_top(self) -> None:
        if not self.isVisible():
            return
        self._apply_win32()

    def update_view(self, mission: Mission, grade: GradeResult, tiles: list[str], status: str) -> None:
        rec = grade.recommendation.value if isinstance(grade.recommendation, Recommendation) else str(grade.recommendation)
        rec_fg = theme.REC_COLORS.get(rec, theme.YELLOW)
        rec_bg = theme.REC_BG.get(rec, theme.WAIT_BG)
        grade_fg = theme.GRADE_COLORS.get(grade.grade, theme.MUTED)
        self.accent.setStyleSheet(f"background: {rec_fg};")
        self.grade.setText(grade.grade)
        self.grade.setStyleSheet(f"color: {grade_fg}; background: {theme.ELEVATED}; padding: 4px 0;")
        self.rec.setText(rec)
        self.rec.setStyleSheet(
            f"color: {rec_fg}; background: {rec_bg}; padding: 3px 8px; font-weight: 700; letter-spacing: 1px;"
        )
        name = mission.display_name or mission.node_id or "Unknown node"
        kind = mission.kind.value.title() if mission.kind else "Mission"
        tileset = mission.tileset or "Unknown tileset"
        self.mission.setText(f"{name}  ·  {kind}")
        self.tiles.setText(f"{tileset}   {' + '.join(tiles[:6]) if tiles else 'No rooms yet'}")
        self.detail.setText(grade.reasons[0] if grade.reasons else status)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self.locked or event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self.locked or self._drag is None:
            return
        self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag = None
        if self.on_move and not self.locked:
            self.on_move(self.x(), self.y())

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._apply_win32()

    def _apply_win32(self) -> None:
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return
            self._hwnd = hwnd
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
            if self.locked:
                style |= WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
            else:
                style &= ~(WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            alpha = int(round(self.opacity * 255))
            user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
        except Exception:
            self.setWindowOpacity(self.opacity)
