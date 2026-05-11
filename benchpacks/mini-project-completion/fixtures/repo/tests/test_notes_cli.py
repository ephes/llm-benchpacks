from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from notes.cli import main
from notes.store import filter_titles, parse_notes, render_report, summarize_by_tag


SAMPLE_LINES = [
    "# comment lines are ignored",
    " Pay bills | finance, urgent ",
    "Read book| personal ",
    "No tags",
    "",
    "Plan trip | Travel, travel",
]


class NotesCliTests(unittest.TestCase):
    def test_parse_notes_normalizes_tags_without_mutation(self) -> None:
        lines = list(SAMPLE_LINES)
        original = list(lines)

        self.assertEqual(
            parse_notes(lines),
            [
                {"title": "Pay bills", "tags": ["finance", "urgent"]},
                {"title": "Read book", "tags": ["personal"]},
                {"title": "No tags", "tags": ["untagged"]},
                {"title": "Plan trip", "tags": ["travel"]},
            ],
        )
        self.assertEqual(lines, original)

    def test_summary_report_and_filter_are_deterministic(self) -> None:
        notes = parse_notes(SAMPLE_LINES)

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

    def test_cli_summary_and_tag_filter_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "notes.txt"
            input_path.write_text("\n".join(SAMPLE_LINES) + "\n", encoding="utf-8")

            summary_stdout = io.StringIO()
            with contextlib.redirect_stdout(summary_stdout):
                self.assertEqual(main(["--input", str(input_path)]), 0)
            self.assertEqual(
                summary_stdout.getvalue(),
                "finance\t1\npersonal\t1\ntravel\t1\nuntagged\t1\nurgent\t1\n",
            )

            filter_stdout = io.StringIO()
            with contextlib.redirect_stdout(filter_stdout):
                self.assertEqual(
                    main(["--input", str(input_path), "--tag", "travel"]),
                    0,
                )
            self.assertEqual(filter_stdout.getvalue(), "Plan trip\n")


if __name__ == "__main__":
    unittest.main()
