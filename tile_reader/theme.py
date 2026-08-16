from __future__ import annotations

import ctypes
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget


BG = "#07080c"
SURFACE = "#101218"
SURFACE_2 = "#161922"
ELEVATED = "#1c2030"
BORDER = "#2a3144"
BORDER_SOFT = "#3a4258"
GOLD = "#d4b46a"
GOLD_DIM = "#8f7544"
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


def font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    item = QFont(FONT, size)
    item.setWeight(weight)
    return item


def display_font(size: int) -> QFont:
    item = QFont(FONT, size, QFont.Weight.Bold)
    item.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
    return item


def stylesheet() -> str:
    return f"""
    QWidget {{
        color: {TEXT};
        font-family: "{FONT}";
        font-size: 13px;
    }}
    QMainWindow, QDialog {{
        background: {BG};
    }}
    QLabel#eyebrow {{
        color: {GOLD_DIM};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.6px;
    }}
    QLabel#muted {{
        color: {MUTED};
        font-size: 12px;
    }}
    QLabel#status {{
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.4px;
    }}
    QPushButton {{
        background: {ELEVATED};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 8px 12px;
        font-weight: 700;
        font-size: 12px;
    }}
    QPushButton:hover {{
        background: {BORDER};
        border-color: {BORDER_SOFT};
    }}
    QPushButton:pressed {{
        background: {SURFACE_2};
    }}
    QPushButton#primary {{
        background: {GOLD};
        color: {BG};
        border: none;
    }}
    QPushButton#primary:hover {{
        background: {GOLD_HOVER};
    }}
    QPushButton#ghost {{
        background: transparent;
        border: none;
        color: {MUTED};
        padding: 4px 8px;
    }}
    QPushButton#ghost:hover {{
        color: {GOLD};
        background: {ELEVATED};
    }}
    QPushButton#reject {{
        background: transparent;
        border: none;
        color: {MUTED};
        font-size: 11px;
        font-weight: 700;
        padding: 2px 6px;
    }}
    QPushButton#reject:hover, QPushButton#reject[on="true"] {{
        color: {RED};
    }}
    QCheckBox {{
        color: {MUTED};
        spacing: 8px;
        font-size: 12px;
    }}
    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {BORDER_SOFT};
        border-radius: 2px;
        background: {SURFACE};
    }}
    QCheckBox::indicator:checked {{
        background: {GOLD};
        border-color: {GOLD};
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: {ELEVATED};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 12px;
        height: 12px;
        margin: -5px 0;
        background: {GOLD};
        border-radius: 6px;
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER};
        border-radius: 4px;
        min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QMenu {{
        background: {SURFACE};
        color: {TEXT};
        border: 1px solid {BORDER};
        padding: 6px;
    }}
    QMenu::item {{
        padding: 6px 16px;
        border-radius: 3px;
    }}
    QMenu::item:selected {{
        background: {ELEVATED};
        color: {GOLD};
    }}
    QMenu::separator {{
        height: 1px;
        background: {BORDER};
        margin: 4px 8px;
    }}
    QTextEdit {{
        background: {SURFACE};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 8px;
        font-size: 13px;
    }}
    QFrame#hairline {{
        background: {BORDER};
        max-height: 1px;
        min-height: 1px;
    }}
    QFrame#room {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-left: 3px solid {BORDER};
        border-radius: 4px;
    }}
    QFrame#room[selected="true"] {{
        background: {SURFACE_2};
        border-left: 3px solid {GOLD};
    }}
    QFrame#room[rejected="true"] {{
        border-left: 3px solid {RED};
    }}
    QFrame#hero {{
        background: transparent;
    }}
    QFrame#rec {{
        border-radius: 4px;
        padding: 2px;
    }}
    """


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(font(10))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_2))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(ELEVATED))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(GOLD))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(BG))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet())


def round_corners(widget: QWidget, preference: int = 2) -> None:
    try:
        hwnd = int(widget.winId())
        value = ctypes.c_int(preference)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def qcolor(value: str) -> QColor:
    return QColor(value)
