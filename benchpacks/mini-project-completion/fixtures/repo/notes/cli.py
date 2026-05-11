from __future__ import annotations

import argparse
from pathlib import Path

from .store import parse_notes, render_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="notes-report")
    parser.add_argument("--input", required=True)
    parser.add_argument("--tag")
    args = parser.parse_args(argv)

    lines = Path(args.input).read_text(encoding="utf-8").splitlines()
    notes = parse_notes(lines)
    print(render_report(notes))
    return 0
