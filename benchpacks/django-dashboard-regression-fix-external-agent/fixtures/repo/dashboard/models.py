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
