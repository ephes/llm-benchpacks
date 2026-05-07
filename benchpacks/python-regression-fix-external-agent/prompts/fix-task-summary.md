You are running inside the prepared repository workspace for this benchmark
case. Fix the small Python repository by editing the workspace files directly.

Allowed repo-root path to edit:

- `task_summary.py`

Current file: `task_summary.py`

```python
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
```

Relevant test expectations from `tests/test_task_summary.py`:

```python
summary = summarize_tasks(tasks)

self.assertEqual(
    summary,
    {
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
    },
)
self.assertEqual(tasks, original)

self.assertEqual(
    overdue_titles(tasks, date(2026, 5, 5)),
    ["Call vendor", "Renew certificate", "Back up database"],
)
```

Observed failures:

```text
$ python -m unittest discover -s tests
FAIL: test_summarize_counts_status_and_owner_without_mutating (test_task_summary.TaskSummaryTests.test_summarize_counts_status_and_owner_without_mutating)
AssertionError: {'by_status': {'todo': 2, 'in-progress': 1, 'done': 1, 'blocked': 1}, 'by_owner': {'Dana': 1, 'Lee': 1, 'unassigned': 1, 'Rui': 1}} != {'by_status': {'todo': 2, 'in-progress': 1, 'done': 1, 'blocked': 1}, 'by_owner': {'Dana': 2, 'Lee': 1, 'unassigned': 1, 'Rui': 1}}

FAIL: test_overdue_titles_ignore_done_and_sort_by_due_then_title (test_task_summary.TaskSummaryTests.test_overdue_titles_ignore_done_and_sort_by_due_then_title)
AssertionError: Lists differ: ['Archive release notes', 'Back up database', 'Call vendor', 'Renew certificate'] != ['Call vendor', 'Renew certificate', 'Back up database']
```

Expected behavior:

- `summarize_tasks(tasks)` returns a dict with `by_status` counts for all tasks
  and `by_owner` counts for all tasks.
- Tasks without an `owner` count under `"unassigned"`.
- `summarize_tasks(tasks)` must not mutate the input task dictionaries.
- `overdue_titles(tasks, today)` returns titles for incomplete tasks only.
- Overdue means the task has an ISO `YYYY-MM-DD` due date before `today`.
- `today` may be either a `datetime.date` or an ISO `YYYY-MM-DD` string.
- Returned overdue titles must be sorted by due date, then title.

Workspace editing contract:

- Edit only the allowed repo-root path listed above.
- Do not write outside the prepared workspace.
- Do not edit tests, verifier files, prompts, README files, generated result
  artifacts, task logs, raw payloads, patch artifacts, or metadata files.
- Make the smallest source changes needed for the stated verifier expectations.
- No patch needs to be printed. The runner captures workspace changes after the
  external-agent task phase exits.
- A short stdout summary is fine, but scoring depends on workspace state and the
  deterministic verifier, not prose.
