from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from datetime import date
from pathlib import Path
from typing import Any


SUMMARY_TASKS = [
    {"title": "Ship docs", "status": "todo", "owner": "Dana"},
    {"title": "Fix importer", "status": "in-progress", "owner": "Lee"},
    {"title": "Triage alerts", "status": "todo"},
    {"title": "Close release", "status": "done", "owner": "Dana"},
    {"title": "Review metrics", "status": "blocked", "owner": "Rui"},
]
EXPECTED_SUMMARY = {
    "by_status": {
        "todo": 2,
        "in-progress": 1,
        "done": 1,
        "blocked": 1,
    },
    "by_owner": {
        "Dana": 2,
        "Lee": 1,
        "unassigned": 1,
        "Rui": 1,
    },
}
OVERDUE_TASKS = [
    {
        "title": "Renew certificate",
        "status": "todo",
        "owner": "Dana",
        "due": "2026-05-02",
    },
    {
        "title": "Back up database",
        "status": "todo",
        "owner": "Lee",
        "due": "2026-05-03",
    },
    {
        "title": "Archive release notes",
        "status": "done",
        "owner": "Lee",
        "due": "2026-05-01",
    },
    {
        "title": "Call vendor",
        "status": "blocked",
        "owner": "Rui",
        "due": "2026-05-01",
    },
    {
        "title": "Prepare demo",
        "status": "todo",
        "owner": "Dana",
        "due": "2026-05-05",
    },
    {
        "title": "Collect feedback",
        "status": "todo",
        "owner": "Lee",
    },
]
EXPECTED_OVERDUE = ["Call vendor", "Renew certificate", "Back up database"]


def _load_task_summary(workspace: Path):
    module_path = workspace / "task_summary.py"
    spec = importlib.util.spec_from_file_location(
        "benchpack_fixture_task_summary",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_summary(module: Any) -> dict[str, Any]:
    tasks = copy.deepcopy(SUMMARY_TASKS)
    original = copy.deepcopy(tasks)
    actual = module.summarize_tasks(tasks)
    return {
        "name": "summarize_tasks_counts_and_no_mutation",
        "expected": EXPECTED_SUMMARY,
        "actual": actual,
        "input_unchanged": tasks == original,
        "passed": actual == EXPECTED_SUMMARY and tasks == original,
    }


def _check_overdue_with_date(module: Any) -> dict[str, Any]:
    actual = module.overdue_titles(copy.deepcopy(OVERDUE_TASKS), date(2026, 5, 5))
    return {
        "name": "overdue_titles_date_input",
        "expected": EXPECTED_OVERDUE,
        "actual": actual,
        "passed": actual == EXPECTED_OVERDUE,
    }


def _check_overdue_with_string(module: Any) -> dict[str, Any]:
    actual = module.overdue_titles(copy.deepcopy(OVERDUE_TASKS), "2026-05-05")
    return {
        "name": "overdue_titles_string_input",
        "expected": EXPECTED_OVERDUE,
        "actual": actual,
        "passed": actual == EXPECTED_OVERDUE,
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
        module = _load_task_summary(workspace)
        checks = [
            _check_summary(module),
            _check_overdue_with_date(module),
            _check_overdue_with_string(module),
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
