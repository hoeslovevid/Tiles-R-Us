from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tile_reader.cli import build_parser, main


def test_version_and_help() -> None:
    parser = build_parser()
    try:
        parser.parse_args(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    try:
        parser.parse_args(["--version"])
    except SystemExit as exc:
        assert exc.code == 0


def test_main_rejects_unknown_flag() -> None:
    try:
        main(["--not-a-real-flag"])
    except SystemExit as exc:
        assert exc.code != 0
        return
    raise AssertionError("expected SystemExit")


if __name__ == "__main__":
    test_version_and_help()
    test_main_rejects_unknown_flag()
    print("ok")
