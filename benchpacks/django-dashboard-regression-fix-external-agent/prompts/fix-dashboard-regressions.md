Fix the small Python dashboard repository by editing only the dashboard package
files that contain the regressions.

Allowed repo-root paths to edit:

- `dashboard/permissions.py`
- `dashboard/formatting.py`
- `dashboard/views.py`

Do not edit tests, README files, or verifier files.

Current file: `dashboard/permissions.py`

```python
from __future__ import annotations

from typing import Any


def can_view_project(project: dict[str, Any], user: dict[str, Any] | None) -> bool:
    """Return whether a user can see a dashboard project."""

    if project.get("visibility") == "public":
        return True
    if project.get("visibility") == "private":
        return user is not None
    if user is None:
        return False
    if user.get("role") == "admin":
        return True
    if project.get("owner_id") == user.get("id"):
        return True
    if user.get("id") in project.get("member_ids", []):
        return True
    return False
```

Current file: `dashboard/formatting.py`

```python
from __future__ import annotations

from typing import Any


def format_project_row(project: dict[str, Any]) -> dict[str, str]:
    """Return the compact row shape rendered by the dashboard."""

    owner = project.setdefault("owner", {})
    if isinstance(owner, dict):
        owner_name = owner.get("name") or "Unassigned"
    else:
        owner_name = str(owner)

    status = project.setdefault("status", "unknown")
    due = project.get("due") or ""
    priority = project.get("priority", "normal")
    title = str(project.get("title", ""))

    return {
        "title": title,
        "owner": owner_name,
        "status": str(status).replace("_", " ").title(),
        "due": str(due),
        "priority": str(priority).lower(),
    }
```

Current file: `dashboard/views.py`

```python
from __future__ import annotations

from typing import Any

from .formatting import format_project_row
from .permissions import can_view_project


def dashboard_rows(
    projects: list[dict[str, Any]],
    user: dict[str, Any] | None,
    *,
    include_archived: bool = False,
) -> list[dict[str, str]]:
    """Return rows visible on the project dashboard."""

    rows: list[dict[str, str]] = []
    for project in projects:
        if project.get("archived") and not include_archived:
            rows.append(format_project_row(project))
        elif can_view_project(project, user):
            rows.append(format_project_row(project))

    return sorted(rows, key=lambda row: row["title"])
```

Useful existing helpers in `dashboard/models.py`:

```python
from __future__ import annotations

from datetime import date


PRIORITY_RANK = {
    "urgent": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
}
FAR_FUTURE = date(9999, 12, 31)


def priority_rank(priority: object) -> int:
    """Return the stable dashboard sort rank for a project priority."""

    return PRIORITY_RANK.get(str(priority or "normal").lower(), PRIORITY_RANK["normal"])


def due_sort_value(value: object) -> date:
    """Return a sortable due date, placing missing due dates last."""

    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return FAR_FUTURE
```

Relevant test expectations from `tests/test_dashboard.py`:

```python
self.assertEqual(
    [row["title"] for row in dashboard_rows(copy.deepcopy(PROJECTS), viewer)],
    ["Team rollout", "Public launch", "Untitled follow-up"],
)

self.assertTrue(can_view_project(private_project, {"id": 20, "role": "member"}))
self.assertFalse(can_view_project(private_project, {"id": 99, "role": "member"}))
self.assertTrue(can_view_project(draft_project, {"id": 20, "role": "member"}))
self.assertFalse(can_view_project(draft_project, None))
self.assertTrue(can_view_project(team_project, {"id": 99, "role": "member"}))
self.assertFalse(can_view_project(team_project, {"id": 42, "role": "member"}))
self.assertTrue(can_view_project(draft_project, {"id": 42, "role": "admin"}))

self.assertNotIn(
    "Archived migration",
    [row["title"] for row in dashboard_rows(copy.deepcopy(PROJECTS), {"id": 10, "role": "member"})],
)

rows = dashboard_rows(projects, {"id": 10, "role": "admin"})
self.assertEqual(
    [row["title"] for row in rows],
    [
        "Draft pricing",
        "Payroll cleanup",
        "Team rollout",
        "Public launch",
        "Untitled follow-up",
    ],
)
self.assertEqual(rows[-1]["owner"], "Unassigned")
self.assertEqual(rows[-1]["status"], "Unknown")
self.assertEqual(projects, original)
```

Observed failures:

```text
$ python -m unittest discover -s tests
FAIL: test_filters_private_and_draft_projects
AssertionError: private and draft projects appeared for an unauthorized user

FAIL: test_archived_projects_are_excluded_by_default
AssertionError: archived projects appeared in the default dashboard

FAIL: test_rows_sort_by_due_priority_title_and_do_not_mutate_input
AssertionError: rows were sorted by title and project dictionaries were mutated
```

Expected behavior:

- Admin users may view every project.
- Draft projects may be viewed only by their owner or an admin.
- Private projects may be viewed only by their owner or an admin.
- Public non-draft projects may be viewed by anyone.
- Team projects may be viewed by their owner, listed members, or an admin.
- `dashboard_rows(projects, user, include_archived=False)` excludes archived
  projects by default.
- `include_archived=True` includes visible archived projects.
- Rows are sorted by due date, then priority rank, then title.
- Missing owners render as `"Unassigned"` and missing statuses render as
  `"Unknown"`.
- Rendering rows must not mutate the input project dictionaries.

Output contract:

- Your entire response must be one fenced code block with info string exactly
  `diff`.
- The first line of your response must be the literal fence marker `` ```diff ``.
- Do not include `<think>`, hidden reasoning, analysis, explanations, shell
  commands, or markdown outside the fenced block.
- Use only exact repo-root paths listed above.
- Omit `index` lines and do not invent paths.
- Inside the block, return a complete unified diff that applies with
  `git apply` from the repository root.
- Close the fenced block.
