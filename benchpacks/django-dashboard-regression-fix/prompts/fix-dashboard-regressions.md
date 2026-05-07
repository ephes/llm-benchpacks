Fix the small Python dashboard repository by editing only the dashboard package
files that contain the regressions.

Repo paths you may edit:

- `dashboard/permissions.py`
- `dashboard/formatting.py`
- `dashboard/views.py`

Do not edit tests, README files, or verifier files.

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

Return only one fenced code block with info string exactly `diff`.
The first line of your response must be the literal fence marker `` ```diff ``.
Inside that block, return a unified diff that applies from the repository root.
Do not include shell commands, explanations, markdown outside the fenced block,
or unrelated file edits.
