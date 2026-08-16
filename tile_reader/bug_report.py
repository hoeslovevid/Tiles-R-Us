from __future__ import annotations

import platform
import re
import sys
import urllib.parse
import webbrowser
from typing import Optional

from .meta import APP_NAME, GITHUB_REPO, GITHUB_URL, NEW_ISSUE_URL, VERSION
from .models import Recommendation
from .session import Session


EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
USER_LINE_RE = re.compile(r"(Windows user-name:|Logged in |computer-name:)\s*.+", re.I)


def sanitize(text: str) -> str:
    text = EMAIL_RE.sub("<redacted-email>", text)
    text = IPV4_RE.sub("<redacted-ip>", text)
    text = USER_LINE_RE.sub(r"\1 <redacted>", text)
    return text


def collect_diagnostics(session: Optional[Session] = None) -> str:
    lines = [
        f"App: {APP_NAME} {VERSION}",
        f"Frozen: {getattr(sys, 'frozen', False)}",
        f"Python: {sys.version.split()[0]} {platform.architecture()[0]}",
        f"OS: {platform.platform()}",
        f"Repo: {GITHUB_REPO}",
    ]
    if session is None:
        return sanitize("\n".join(lines))
    mission = session.mission
    grade = session.grade
    rec = grade.recommendation.value if isinstance(grade.recommendation, Recommendation) else str(grade.recommendation)
    tiles = ", ".join(session.layout.short_names()) or "(none)"
    lines.extend(
        [
            "",
            "## Session",
            f"Status: {session.status}",
            f"Last event: {session.last_event or '(none)'}",
            f"Mission: {mission.display_name or '(none)'}",
            f"Node: {mission.node_id or '(none)'}",
            f"Type: {mission.mission_type or '(none)'} ({mission.kind.value})",
            f"Tileset: {mission.tileset or '(none)'}",
            f"Seed: {mission.seed if mission.seed is not None else '(none)'}",
            f"Segments: {session.layout.segments or '(none)'}",
            f"Rooms: {tiles}",
            f"Grade: {grade.grade} / {rec} (score {grade.score})",
            f"Reasons: {'; '.join(grade.reasons) or '(none)'}",
        ]
    )
    return sanitize("\n".join(lines))


def build_issue_body(what: str, steps: str, diagnostics: str) -> str:
    return (
        "## What happened\n"
        f"{what.strip() or '(not filled in)'}\n\n"
        "## Steps to reproduce\n"
        f"{steps.strip() or '(not filled in)'}\n\n"
        "## Diagnostics\n"
        "```\n"
        f"{diagnostics.strip()}\n"
        "```\n\n"
        "_Do not paste EE.log. It can contain your email and IP address._\n"
    )


def issue_url(title: str, body: str, max_body: int = 5500) -> str:
    clipped = body
    if len(clipped) > max_body:
        clipped = clipped[:max_body] + "\n\n…truncated. Full diagnostics were copied to the clipboard.\n"
    query = urllib.parse.urlencode(
        {
            "labels": "bug",
            "title": title.strip() or f"{APP_NAME} bug",
            "body": clipped,
        }
    )
    return f"{NEW_ISSUE_URL}?{query}"


def open_github() -> None:
    webbrowser.open(GITHUB_URL)


def open_issue(title: str, body: str) -> str:
    url = issue_url(title, body)
    webbrowser.open(url)
    return url


def copy_to_clipboard(widget, text: str) -> None:
    try:
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            return
    except Exception:
        pass
    if widget is not None and hasattr(widget, "clipboard_clear"):
        widget.clipboard_clear()
        widget.clipboard_append(text)
        widget.update_idletasks()


def show_about(parent) -> None:
    from PySide6.QtWidgets import QMessageBox

    QMessageBox.information(
        parent,
        f"About {APP_NAME}",
        f"{APP_NAME} {VERSION}\n\n"
        "Reads Warframe EE.log and grades Disruption / Survival layouts.\n\n"
        f"GitHub:\n{GITHUB_URL}",
    )


def show_bug_dialog(parent, session: Optional[Session] = None) -> None:
    from PySide6.QtWidgets import (
        QCheckBox,
        QDialog,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
    )

    from . import theme

    diagnostics = collect_diagnostics(session)
    dialog = QDialog(parent)
    dialog.setWindowTitle("Report a bug")
    dialog.resize(560, 560)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(8)

    title = QLabel("Report a bug")
    title.setStyleSheet(f"color: {theme.GOLD}; font-size: 16px; font-weight: 700;")
    layout.addWidget(title)
    hint = QLabel(
        "Opens a GitHub issue. Diagnostics never include EE.log (that file can contain your email and IP)."
    )
    hint.setWordWrap(True)
    hint.setStyleSheet(f"color: {theme.MUTED}; font-size: 12px;")
    layout.addWidget(hint)

    layout.addWidget(QLabel("WHAT HAPPENED"))
    what = QTextEdit()
    what.setFixedHeight(90)
    layout.addWidget(what)

    layout.addWidget(QLabel("STEPS TO REPRODUCE"))
    steps = QTextEdit()
    steps.setFixedHeight(90)
    layout.addWidget(steps)

    include = QCheckBox("Include app diagnostics (mission, rooms, grade, OS — no account data)")
    include.setChecked(True)
    layout.addWidget(include)

    def _body() -> str:
        diag = diagnostics if include.isChecked() else "(diagnostics not included)"
        return build_issue_body(what.toPlainText(), steps.toPlainText(), diag)

    def _title() -> str:
        first = what.toPlainText().strip().splitlines()
        return first[0][:80] if first and first[0] else f"{APP_NAME} bug"

    def submit() -> None:
        body = _body()
        copy_to_clipboard(dialog, body)
        open_issue(_title(), body)
        QMessageBox.information(
            dialog,
            "Bug report",
            "GitHub should open with a pre-filled issue.\n\nThe full report was also copied to your clipboard.",
        )
        dialog.accept()

    def copy_only() -> None:
        copy_to_clipboard(dialog, _body())
        QMessageBox.information(dialog, "Copied", "Bug report copied to the clipboard.")

    buttons = QHBoxLayout()
    open_btn = QPushButton("Open GitHub issue")
    open_btn.setObjectName("primary")
    open_btn.clicked.connect(submit)
    buttons.addWidget(open_btn)
    copy_btn = QPushButton("Copy report")
    copy_btn.clicked.connect(copy_only)
    buttons.addWidget(copy_btn)
    buttons.addStretch()
    cancel = QPushButton("Cancel")
    cancel.clicked.connect(dialog.reject)
    buttons.addWidget(cancel)
    layout.addLayout(buttons)
    what.setFocus()
    dialog.exec()

