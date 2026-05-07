from __future__ import annotations

import copy
import unittest

from dashboard.permissions import can_view_project
from dashboard.views import dashboard_rows


PROJECTS = [
    {
        "id": 1,
        "title": "Public launch",
        "visibility": "public",
        "status": "active",
        "owner_id": 10,
        "owner": {"name": "Dana"},
        "due": "2026-05-10",
        "priority": "normal",
    },
    {
        "id": 2,
        "title": "Payroll cleanup",
        "visibility": "private",
        "status": "active",
        "owner_id": 20,
        "owner": {"name": "Rui"},
        "due": "2026-05-03",
        "priority": "urgent",
    },
    {
        "id": 3,
        "title": "Draft pricing",
        "visibility": "public",
        "status": "draft",
        "owner_id": 20,
        "owner": {"name": "Rui"},
        "due": "2026-05-01",
        "priority": "high",
    },
    {
        "id": 4,
        "title": "Archived migration",
        "visibility": "public",
        "status": "active",
        "owner_id": 10,
        "owner": {"name": "Dana"},
        "due": "2026-05-02",
        "priority": "high",
        "archived": True,
    },
    {
        "id": 5,
        "title": "Team rollout",
        "visibility": "team",
        "status": "blocked",
        "owner_id": 30,
        "member_ids": [99],
        "owner": {"name": "Lee"},
        "due": "2026-05-03",
        "priority": "normal",
    },
    {
        "id": 6,
        "title": "Untitled follow-up",
        "visibility": "public",
        "owner_id": 10,
        "due": "",
    },
]


class DashboardTests(unittest.TestCase):
    def test_filters_private_and_draft_projects(self) -> None:
        viewer = {"id": 99, "role": "member"}

        rows = dashboard_rows(copy.deepcopy(PROJECTS), viewer)

        self.assertEqual(
            [row["title"] for row in rows],
            ["Team rollout", "Public launch", "Untitled follow-up"],
        )

    def test_permission_helper_owner_admin_member_rules(self) -> None:
        private_project = PROJECTS[1]
        draft_project = PROJECTS[2]
        team_project = PROJECTS[4]

        self.assertTrue(can_view_project(private_project, {"id": 20, "role": "member"}))
        self.assertFalse(can_view_project(private_project, {"id": 99, "role": "member"}))
        self.assertTrue(can_view_project(draft_project, {"id": 20, "role": "member"}))
        self.assertFalse(can_view_project(draft_project, None))
        self.assertTrue(can_view_project(team_project, {"id": 99, "role": "member"}))
        self.assertFalse(can_view_project(team_project, {"id": 42, "role": "member"}))
        self.assertTrue(can_view_project(draft_project, {"id": 42, "role": "admin"}))

    def test_archived_projects_are_excluded_by_default(self) -> None:
        rows = dashboard_rows(copy.deepcopy(PROJECTS), {"id": 10, "role": "member"})

        self.assertNotIn("Archived migration", [row["title"] for row in rows])

    def test_include_archived_keeps_visible_archived_projects(self) -> None:
        rows = dashboard_rows(
            copy.deepcopy(PROJECTS),
            {"id": 10, "role": "member"},
            include_archived=True,
        )

        self.assertIn("Archived migration", [row["title"] for row in rows])

    def test_rows_sort_by_due_priority_title_and_do_not_mutate_input(self) -> None:
        projects = copy.deepcopy(PROJECTS)
        original = copy.deepcopy(projects)

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


if __name__ == "__main__":
    unittest.main()
