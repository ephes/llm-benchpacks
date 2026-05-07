from __future__ import annotations

import copy
import unittest
from datetime import date

from task_summary import overdue_titles, summarize_tasks


class TaskSummaryTests(unittest.TestCase):
    def test_summarize_counts_status_and_owner_without_mutating(self) -> None:
        tasks = [
            {"title": "Ship docs", "status": "todo", "owner": "Dana"},
            {"title": "Fix importer", "status": "in-progress", "owner": "Lee"},
            {"title": "Triage alerts", "status": "todo"},
            {"title": "Close release", "status": "done", "owner": "Dana"},
            {"title": "Review metrics", "status": "blocked", "owner": "Rui"},
        ]
        original = copy.deepcopy(tasks)

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

    def test_overdue_titles_ignore_done_and_sort_by_due_then_title(self) -> None:
        tasks = [
            {
                "title": "Renew certificate",
                "status": "todo",
                "owner": "Dana",
                "due": "2026-05-02",
            },
            {
                "title": "Back up database",
                "status": "todo",
                "owner": "Lee",
                "due": "2026-05-03",
            },
            {
                "title": "Archive release notes",
                "status": "done",
                "owner": "Lee",
                "due": "2026-05-01",
            },
            {
                "title": "Call vendor",
                "status": "blocked",
                "owner": "Rui",
                "due": "2026-05-01",
            },
            {
                "title": "Prepare demo",
                "status": "todo",
                "owner": "Dana",
                "due": "2026-05-05",
            },
            {
                "title": "Collect feedback",
                "status": "todo",
                "owner": "Lee",
            },
        ]

        self.assertEqual(
            overdue_titles(tasks, date(2026, 5, 5)),
            ["Call vendor", "Renew certificate", "Back up database"],
        )


if __name__ == "__main__":
    unittest.main()
