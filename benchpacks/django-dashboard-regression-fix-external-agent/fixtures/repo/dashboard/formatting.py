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
