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
