from __future__ import annotations

import argparse
import copy
import importlib
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

PROJECTS = [
    {
        "id": 1,
        "title": "Public launch",
        "visibility": "public",
        "status": "active",
        "owner_id": 10,
        "owner": {"name": "Dana"},
        "due": "2026-05-10",
        "priority": "normal",
    },
    {
        "id": 2,
        "title": "Payroll cleanup",
        "visibility": "private",
        "status": "active",
        "owner_id": 20,
        "owner": {"name": "Rui"},
        "due": "2026-05-03",
        "priority": "urgent",
    },
    {
        "id": 3,
        "title": "Draft pricing",
        "visibility": "public",
        "status": "draft",
        "owner_id": 20,
        "owner": {"name": "Rui"},
        "due": "2026-05-01",
        "priority": "high",
    },
    {
        "id": 4,
        "title": "Archived migration",
        "visibility": "public",
        "status": "active",
        "owner_id": 10,
        "owner": {"name": "Dana"},
        "due": "2026-05-02",
        "priority": "high",
        "archived": True,
    },
    {
        "id": 5,
        "title": "Team rollout",
        "visibility": "team",
        "status": "blocked",
        "owner_id": 30,
        "member_ids": [99],
        "owner": {"name": "Lee"},
        "due": "2026-05-03",
        "priority": "normal",
    },
    {
        "id": 6,
        "title": "Untitled follow-up",
        "visibility": "public",
        "owner_id": 10,
        "due": "",
    },
]


def _load_modules(workspace: Path) -> tuple[Any, Any]:
    sys.path.insert(0, str(workspace))
    for module_name in [
        "dashboard.views",
        "dashboard.permissions",
        "dashboard.formatting",
        "dashboard.models",
    ]:
        sys.modules.pop(module_name, None)
    views = importlib.import_module("dashboard.views")
    permissions = importlib.import_module("dashboard.permissions")
    return views, permissions


def _check_filters(views: Any) -> dict[str, Any]:
    viewer = {"id": 99, "role": "member"}
    actual = [row["title"] for row in views.dashboard_rows(copy.deepcopy(PROJECTS), viewer)]
    expected = ["Team rollout", "Public launch", "Untitled follow-up"]
    return {
        "name": "dashboard_rows_filters_private_and_draft",
        "expected": expected,
        "actual": actual,
        "passed": actual == expected,
    }


def _check_permissions(permissions: Any) -> dict[str, Any]:
    results = {
        "private_owner": permissions.can_view_project(
            PROJECTS[1],
            {"id": 20, "role": "member"},
        ),
        "private_other": permissions.can_view_project(
            PROJECTS[1],
            {"id": 99, "role": "member"},
        ),
        "draft_owner": permissions.can_view_project(
            PROJECTS[2],
            {"id": 20, "role": "member"},
        ),
        "draft_anonymous": permissions.can_view_project(PROJECTS[2], None),
        "team_member": permissions.can_view_project(
            PROJECTS[4],
            {"id": 99, "role": "member"},
        ),
        "team_other": permissions.can_view_project(
            PROJECTS[4],
            {"id": 42, "role": "member"},
        ),
        "admin": permissions.can_view_project(
            PROJECTS[2],
            {"id": 42, "role": "admin"},
        ),
    }
    expected = {
        "private_owner": True,
        "private_other": False,
        "draft_owner": True,
        "draft_anonymous": False,
        "team_member": True,
        "team_other": False,
        "admin": True,
    }
    return {
        "name": "can_view_project_enforces_visibility_rules",
        "expected": expected,
        "actual": results,
        "passed": results == expected,
    }


def _check_archived_default(views: Any) -> dict[str, Any]:
    rows = views.dashboard_rows(copy.deepcopy(PROJECTS), {"id": 10, "role": "member"})
    titles = [row["title"] for row in rows]
    return {
        "name": "dashboard_rows_excludes_archived_by_default",
        "expected_absent": "Archived migration",
        "actual": titles,
        "passed": "Archived migration" not in titles,
    }


def _check_archived_included(views: Any) -> dict[str, Any]:
    rows = views.dashboard_rows(
        copy.deepcopy(PROJECTS),
        {"id": 10, "role": "member"},
        include_archived=True,
    )
    titles = [row["title"] for row in rows]
    return {
        "name": "dashboard_rows_include_archived_when_requested",
        "expected_present": "Archived migration",
        "actual": titles,
        "passed": "Archived migration" in titles,
    }


def _check_sorting_and_immutability(views: Any) -> dict[str, Any]:
    projects = copy.deepcopy(PROJECTS)
    original = copy.deepcopy(projects)
    rows = views.dashboard_rows(projects, {"id": 10, "role": "admin"})
    titles = [row["title"] for row in rows]
    expected = [
        "Draft pricing",
        "Payroll cleanup",
        "Team rollout",
        "Public launch",
        "Untitled follow-up",
    ]
    missing_row = rows[-1] if rows else {}
    missing_values_ok = (
        missing_row.get("owner") == "Unassigned"
        and missing_row.get("status") == "Unknown"
    )
    return {
        "name": "dashboard_rows_sorting_missing_values_and_no_mutation",
        "expected": expected,
        "actual": titles,
        "missing_values_ok": missing_values_ok,
        "input_unchanged": projects == original,
        "passed": titles == expected and missing_values_ok and projects == original,
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
        views, permissions = _load_modules(workspace)
        checks = [
            _check_filters(views),
            _check_permissions(permissions),
            _check_archived_default(views),
            _check_archived_included(views),
            _check_sorting_and_immutability(views),
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
