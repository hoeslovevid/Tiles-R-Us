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
    widget.clipboard_clear()
    widget.clipboard_append(text)
    widget.update_idletasks()


def show_about(parent) -> None:
    from tkinter import messagebox

    messagebox.showinfo(
        f"About {APP_NAME}",
        f"{APP_NAME} {VERSION}\n\n"
        "Reads Warframe EE.log and grades Disruption / Survival layouts.\n\n"
        f"GitHub:\n{GITHUB_URL}",
        parent=parent,
    )


def show_bug_dialog(parent, session: Optional[Session] = None) -> None:
    import tkinter as tk
    from tkinter import messagebox

    from . import theme

    diagnostics = collect_diagnostics(session)
    dialog = tk.Toplevel(parent)
    dialog.title("Report a bug")
    dialog.configure(bg=theme.BG)
    dialog.geometry("580x600")
    dialog.transient(parent)
    dialog.attributes("-topmost", True)
    dialog.grab_set()
    theme.round_corners(dialog)

    header = tk.Frame(dialog, bg=theme.SURFACE, highlightthickness=1, highlightbackground=theme.BORDER)
    header.pack(fill="x", padx=16, pady=(16, 8))
    head_inner = tk.Frame(header, bg=theme.SURFACE)
    head_inner.pack(fill="x", padx=16, pady=12)
    tk.Label(head_inner, text="Report a bug", bg=theme.SURFACE, fg=theme.GOLD, font=theme.font(14, "bold")).pack(anchor="w")
    tk.Label(
        head_inner,
        text="Opens a GitHub issue. Diagnostics never include EE.log (that file can contain your email and IP).",
        bg=theme.SURFACE,
        fg=theme.MUTED,
        wraplength=520,
        justify="left",
        font=theme.font(9),
    ).pack(anchor="w", pady=(4, 0))

    body = tk.Frame(dialog, bg=theme.BG)
    body.pack(fill="both", expand=True, padx=16)

    tk.Label(body, text="WHAT HAPPENED", bg=theme.BG, fg=theme.GOLD_DIM, font=theme.font(8, "bold")).pack(anchor="w", pady=(8, 4))
    what = tk.Text(body, height=4, bg=theme.SURFACE, fg=theme.TEXT, insertbackground=theme.TEXT, bd=0, font=theme.font(10), wrap="word", highlightthickness=1, highlightbackground=theme.BORDER)
    what.pack(fill="x")

    tk.Label(body, text="STEPS TO REPRODUCE", bg=theme.BG, fg=theme.GOLD_DIM, font=theme.font(8, "bold")).pack(anchor="w", pady=(12, 4))
    steps = tk.Text(body, height=4, bg=theme.SURFACE, fg=theme.TEXT, insertbackground=theme.TEXT, bd=0, font=theme.font(10), wrap="word", highlightthickness=1, highlightbackground=theme.BORDER)
    steps.pack(fill="x")

    include = tk.BooleanVar(value=True)
    theme.check(
        body,
        "Include app diagnostics (mission, rooms, grade, OS — no account data)",
        include,
    )

    def _body() -> str:
        diag = diagnostics if include.get() else "(diagnostics not included)"
        return build_issue_body(what.get("1.0", "end"), steps.get("1.0", "end"), diag)

    def _title() -> str:
        first = what.get("1.0", "end").strip().splitlines()
        return first[0][:80] if first and first[0] else f"{APP_NAME} bug"

    def submit() -> None:
        body = _body()
        copy_to_clipboard(dialog, body)
        open_issue(_title(), body)
        messagebox.showinfo(
            "Bug report",
            "GitHub should open with a pre-filled issue.\n\nThe full report was also copied to your clipboard.",
            parent=dialog,
        )
        dialog.destroy()

    def copy_only() -> None:
        copy_to_clipboard(dialog, _body())
        messagebox.showinfo("Copied", "Bug report copied to the clipboard.", parent=dialog)

    buttons = tk.Frame(dialog, bg=theme.BG)
    buttons.pack(fill="x", padx=16, pady=16)
    theme.button(buttons, "Open GitHub issue", submit, kind="primary").pack(side="left", padx=(0, 8))
    theme.button(buttons, "Copy report", copy_only).pack(side="left")
    theme.button(buttons, "Cancel", dialog.destroy).pack(side="right")
    what.focus_set()

