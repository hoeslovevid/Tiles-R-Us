from __future__ import annotations

import argparse
import sys

from .meta import APP_NAME, VERSION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tilesrus",
        description=f"{APP_NAME} - grade Warframe Disruption and Survival layouts.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} {VERSION}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    from .app import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
