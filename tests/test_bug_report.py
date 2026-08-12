from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tile_reader.bug_report import build_issue_body, collect_diagnostics, issue_url, sanitize
from tile_reader.session import Session


def test_sanitize_strips_email_and_ip() -> None:
    raw = "Windows user-name: Dave\ncontact me@example.com from 192.168.1.10\n"
    cleaned = sanitize(raw)
    assert "me@example.com" not in cleaned
    assert "192.168.1.10" not in cleaned
    assert "Dave" not in cleaned
    assert "<redacted-email>" in cleaned
    assert "<redacted-ip>" in cleaned


def test_issue_url_contains_label_and_title() -> None:
    url = issue_url("layout grade wrong", "body text")
    assert "labels=bug" in url
    assert "layout" in url
    assert url.startswith("https://github.com/")


def test_diagnostics_include_version() -> None:
    text = collect_diagnostics(Session())
    assert "Tiles R Us" in text
    assert "Mission:" in text


def test_issue_body_warns_against_eelog() -> None:
    body = build_issue_body("crash", "open app", "diag")
    assert "EE.log" in body
    assert "crash" in body


if __name__ == "__main__":
    test_sanitize_strips_email_and_ip()
    test_issue_url_contains_label_and_title()
    test_diagnostics_include_version()
    test_issue_body_warns_against_eelog()
    print("ok")
