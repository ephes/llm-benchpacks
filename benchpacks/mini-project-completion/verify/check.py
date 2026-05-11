from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

VISIBLE_LINES = [
    "# comment lines are ignored",
    " Pay bills | finance, urgent ",
    "Read book| personal ",
    "No tags",
    "",
    "Plan trip | Travel, travel",
]
EDGE_LINES = [
    "  # another comment",
    "Deploy app | Ops, ops, release,, ",
    "Document API | Docs",
    "Untitled | , ",
    "  Archive logs  ",
]


def _load_project(workspace: Path):
    sys.path.insert(0, str(workspace))
    for name in [
        "notes",
        "notes.store",
        "notes.cli",
    ]:
        sys.modules.pop(name, None)
    store = importlib.import_module("notes.store")
    cli = importlib.import_module("notes.cli")
    return store, cli


def _check_visible_parse(store: Any) -> dict[str, Any]:
    lines = list(VISIBLE_LINES)
    original = list(lines)
    actual = store.parse_notes(lines)
    expected = [
        {"title": "Pay bills", "tags": ["finance", "urgent"]},
        {"title": "Read book", "tags": ["personal"]},
        {"title": "No tags", "tags": ["untagged"]},
        {"title": "Plan trip", "tags": ["travel"]},
    ]
    return {
        "name": "visible_parse_notes",
        "expected": expected,
        "actual": actual,
        "input_unchanged": lines == original,
        "passed": actual == expected and lines == original,
    }


def _check_visible_summary_and_filter(store: Any) -> dict[str, Any]:
    notes = store.parse_notes(VISIBLE_LINES)
    expected_summary = {
        "finance": 1,
        "personal": 1,
        "travel": 1,
        "untagged": 1,
        "urgent": 1,
    }
    actual_summary = store.summarize_by_tag(notes)
    actual_report = store.render_report(notes)
    actual_titles = store.filter_titles(notes, " URGENT ")
    return {
        "name": "visible_summary_report_filter",
        "expected_summary": expected_summary,
        "actual_summary": actual_summary,
        "expected_report": (
            "finance\t1\npersonal\t1\ntravel\t1\nuntagged\t1\nurgent\t1\n"
        ),
        "actual_report": actual_report,
        "expected_titles": ["Pay bills"],
        "actual_titles": actual_titles,
        "passed": (
            actual_summary == expected_summary
            and actual_report
            == "finance\t1\npersonal\t1\ntravel\t1\nuntagged\t1\nurgent\t1\n"
            and actual_titles == ["Pay bills"]
        ),
    }


def _check_edge_cases(store: Any) -> dict[str, Any]:
    notes = store.parse_notes(EDGE_LINES)
    expected_notes = [
        {"title": "Deploy app", "tags": ["ops", "release"]},
        {"title": "Document API", "tags": ["docs"]},
        {"title": "Untitled", "tags": ["untagged"]},
        {"title": "Archive logs", "tags": ["untagged"]},
    ]
    expected_summary = {
        "docs": 1,
        "ops": 1,
        "release": 1,
        "untagged": 2,
    }
    return {
        "name": "hidden_edge_parse_summary_filter",
        "expected_notes": expected_notes,
        "actual_notes": notes,
        "expected_summary": expected_summary,
        "actual_summary": store.summarize_by_tag(notes),
        "expected_untagged_titles": ["Untitled", "Archive logs"],
        "actual_untagged_titles": store.filter_titles(notes, "UNTAGGED"),
        "passed": (
            notes == expected_notes
            and store.summarize_by_tag(notes) == expected_summary
            and store.filter_titles(notes, "UNTAGGED")
            == ["Untitled", "Archive logs"]
        ),
    }


def _check_cli(cli: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        input_path = Path(tmp) / "notes.txt"
        input_path.write_text("\n".join(VISIBLE_LINES) + "\n", encoding="utf-8")
        empty_input_path = Path(tmp) / "empty-notes.txt"
        empty_input_path.write_text(
            "# only comments\n\n   # and whitespace comments\n",
            encoding="utf-8",
        )

        summary_stdout = io.StringIO()
        with contextlib.redirect_stdout(summary_stdout):
            summary_rc = cli.main(["--input", str(input_path)])

        tag_stdout = io.StringIO()
        with contextlib.redirect_stdout(tag_stdout):
            tag_rc = cli.main(["--input", str(input_path), "--tag", "travel"])

        empty_summary_stdout = io.StringIO()
        with contextlib.redirect_stdout(empty_summary_stdout):
            empty_summary_rc = cli.main(["--input", str(empty_input_path)])

    return {
        "name": "cli_summary_and_filter",
        "summary_return_code": summary_rc,
        "expected_summary_stdout": (
            "finance\t1\npersonal\t1\ntravel\t1\nuntagged\t1\nurgent\t1\n"
        ),
        "actual_summary_stdout": summary_stdout.getvalue(),
        "tag_return_code": tag_rc,
        "expected_tag_stdout": "Plan trip\n",
        "actual_tag_stdout": tag_stdout.getvalue(),
        "empty_summary_return_code": empty_summary_rc,
        "expected_empty_summary_stdout": "",
        "actual_empty_summary_stdout": empty_summary_stdout.getvalue(),
        "passed": (
            summary_rc == 0
            and summary_stdout.getvalue()
            == "finance\t1\npersonal\t1\ntravel\t1\nuntagged\t1\nurgent\t1\n"
            and tag_rc == 0
            and tag_stdout.getvalue() == "Plan trip\n"
            and empty_summary_rc == 0
            and empty_summary_stdout.getvalue() == ""
        ),
    }


def _check_unittest_suite(workspace: Path) -> dict[str, Any]:
    test_file = workspace / "tests" / "test_notes_cli.py"
    loader = unittest.TestLoader()
    suite = loader.discover(str(workspace / "tests"))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return {
        "name": "visible_unittest_suite",
        "test_file_exists": test_file.is_file(),
        "tests_run": result.testsRun,
        "minimum_tests_run": 3,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "output": stream.getvalue(),
        "passed": (
            test_file.is_file()
            and result.testsRun >= 3
            and result.wasSuccessful()
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--pack-version", required=True)
    parser.add_argument("--source-fixture-id", required=True)
    parser.add_argument("--patch", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    workspace = Path(args.workspace)
    patch_path = Path(args.patch)
    output_path = Path(args.output)

    payload: dict[str, Any] = {
        "case": args.case,
        "pack_id": args.pack_id,
        "pack_version": args.pack_version,
        "source_fixture_id": args.source_fixture_id,
        "patch_exists": patch_path.is_file(),
        "patch_bytes": patch_path.stat().st_size if patch_path.is_file() else 0,
        "checks": [],
    }

    try:
        store, cli = _load_project(workspace)
        checks = [
            _check_visible_parse(store),
            _check_visible_summary_and_filter(store),
            _check_edge_cases(store),
            _check_cli(cli),
            _check_unittest_suite(workspace),
        ]
        payload["checks"] = checks
        payload["passed"] = (
            all(check["passed"] for check in checks)
            and payload["patch_exists"]
            and payload["patch_bytes"] > 0
        )
    except Exception as exc:
        payload["error"] = str(exc)
        payload["passed"] = False
    finally:
        try:
            sys.path.remove(str(workspace))
        except ValueError:
            pass

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
