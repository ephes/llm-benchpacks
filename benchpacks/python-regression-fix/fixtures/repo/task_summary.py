from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any


def summarize_tasks(tasks: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    by_status: Counter[str] = Counter()
    by_owner: Counter[str] = Counter()

    for task in tasks:
        status = task.get("status", "todo")
        owner = task.setdefault("owner", "unassigned")
        by_status[status] += 1
        if status != "done":
            by_owner[owner] += 1

    return {
        "by_status": dict(by_status),
        "by_owner": dict(by_owner),
    }


def overdue_titles(tasks: list[dict[str, Any]], today: date | str) -> list[str]:
    if isinstance(today, date):
        today_text = today.isoformat()
    else:
        today_text = today

    overdue: list[str] = []
    for task in tasks:
        due = task.get("due")
        if due and due < today_text:
            overdue.append(str(task.get("title", "")))

    return sorted(overdue)
