Fix the small Python repository by editing only the file that contains the task
summary regression.

Repo path to edit:

- `task_summary.py`

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

Return only one fenced code block with info string exactly `diff`.
The first line of your response must be the literal fence marker `` ```diff ``.
Inside that block, return a unified diff that applies from the repository root.
Do not include shell commands, explanations, markdown outside the fenced block,
or unrelated file edits.
