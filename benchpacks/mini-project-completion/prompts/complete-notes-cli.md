Complete the small Python notes-report project.

Allowed repo-root paths to edit:

- `notes/store.py`
- `notes/cli.py`

Do not edit tests, README files, project metadata, verifier files, prompts, or
generated artifacts.

Current file: `notes/store.py`

```python
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
```

Current file: `notes/cli.py`

```python
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
```

Relevant visible expectations from `tests/test_notes_cli.py`:

```python
SAMPLE_LINES = [
    "# comment lines are ignored",
    " Pay bills | finance, urgent ",
    "Read book| personal ",
    "No tags",
    "",
    "Plan trip | Travel, travel",
]

self.assertEqual(
    parse_notes(lines),
    [
        {"title": "Pay bills", "tags": ["finance", "urgent"]},
        {"title": "Read book", "tags": ["personal"]},
        {"title": "No tags", "tags": ["untagged"]},
        {"title": "Plan trip", "tags": ["travel"]},
    ],
)

self.assertEqual(
    summarize_by_tag(notes),
    {
        "finance": 1,
        "personal": 1,
        "travel": 1,
        "untagged": 1,
        "urgent": 1,
    },
)
self.assertEqual(
    render_report(notes),
    "finance\t1\npersonal\t1\ntravel\t1\nuntagged\t1\nurgent\t1\n",
)
self.assertEqual(filter_titles(notes, "URGENT"), ["Pay bills"])
```

Expected behavior:

- `parse_notes(lines)` ignores blank lines and lines whose first non-space
  character is `#`.
- Each non-comment note line may be either `title` or `title | tag, tag`.
- Titles are stripped of surrounding whitespace.
- Tags are stripped, lowercased, blank tags are ignored, and duplicate tags
  within one note count once.
- A note with no usable tags gets exactly one tag: `untagged`.
- Tag lists on each parsed note are sorted ascending.
- `parse_notes(lines)` must not mutate the input iterable when it is a list.
- `summarize_by_tag(notes)` counts each parsed note once per tag and returns a
  dict inserted in ascending tag order.
- `render_report(notes)` returns one line per tag in ascending tag order as
  `tag<TAB>count`, with a trailing newline when there is at least one line.
- `filter_titles(notes, tag)` compares tags case-insensitively after stripping
  whitespace and returns matching note titles in original note order.
- `main(["--input", path])` reads UTF-8 notes and prints `render_report(notes)`
  without adding extra blank lines.
- `main(["--input", path, "--tag", tag])` prints one matching title per line,
  preserving original note order, with a trailing newline when there is at
  least one title.

Output contract:

- Your entire response must be one fenced code block with info string exactly
  `diff`.
- The first line of your response must be the literal fence marker `` ```diff ``.
- Do not include `<think>`, hidden reasoning, analysis, explanations, shell
  commands, or markdown outside the fenced block.
- Use only exact repo-root paths listed above.
- Omit `index` lines and do not invent paths.
- Return a complete unified diff that applies with `git apply` from the
  repository root.
- Close the fenced block.
