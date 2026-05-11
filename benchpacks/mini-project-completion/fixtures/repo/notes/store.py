from __future__ import annotations

from collections import Counter
from typing import Iterable

Note = dict[str, object]


def parse_notes(lines: Iterable[str]) -> list[Note]:
    notes: list[Note] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        notes.append({"title": text, "tags": []})
    return notes


def summarize_by_tag(notes: Iterable[Note]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for note in notes:
        for tag in note.get("tags", []):
            counts[str(tag)] += 1
    return dict(counts)


def filter_titles(notes: Iterable[Note], tag: str) -> list[str]:
    return [str(note.get("title", "")) for note in notes]


def render_report(notes: Iterable[Note]) -> str:
    counts = summarize_by_tag(notes)
    lines = [f"{tag}\t{count}" for tag, count in counts.items()]
    return "\n".join(lines)
