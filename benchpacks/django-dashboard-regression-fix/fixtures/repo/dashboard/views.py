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
