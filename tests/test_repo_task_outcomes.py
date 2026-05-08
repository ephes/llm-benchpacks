"""Tests for report-only repo-task outcome summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from benchpack.repo_task_outcomes import summarize_repo_task_outcomes


def _repo_task_record(
    *,
    patch: Any = None,
    scoring: dict[str, Any] | None = None,
    repo_status: str = "failed",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case": "fix-repo",
        "repo_task": {"status": repo_status, "verify_exit_code": 1},
        "scoring": scoring or {"mode": "verify-script", "passed": False},
    }
    if patch is not None:
        record["patch"] = patch
    return record


@pytest.mark.parametrize(
    ("patch", "expected_patch_bytes"),
    [
        pytest.param(None, None, id="missing-patch"),
        pytest.param("not-a-dict", None, id="non-dict-patch"),
        pytest.param({"path": ""}, None, id="empty-path"),
        pytest.param({"path": "/tmp/outside.diff"}, None, id="absolute-path"),
        pytest.param({"path": "../outside.diff"}, None, id="escaping-path"),
        pytest.param({"path": "patch/missing.diff"}, None, id="missing-file"),
        pytest.param({"path": "patch/not-a-file.diff"}, None, id="directory"),
    ],
)
def test_repo_task_outcomes_treat_unknown_patch_state_as_report_only_unknown(
    tmp_path: Path,
    patch: Any,
    expected_patch_bytes: int | None,
) -> None:
    result_dir = tmp_path / "run"
    result_dir.mkdir()
    (tmp_path / "outside.diff").write_text("outside\n", encoding="utf-8")
    directory = result_dir / "patch" / "not-a-file.diff"
    directory.mkdir(parents=True)

    outcome = summarize_repo_task_outcomes(
        [_repo_task_record(patch=patch)],
        result_dir,
    )[0]

    assert outcome.patch_bytes == expected_patch_bytes
    assert outcome.outcome == "failed-unknown-mutation"


def test_repo_task_outcomes_classify_empty_patch_as_no_mutation(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run"
    patch = result_dir / "patch" / "fix-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("", encoding="utf-8")

    outcome = summarize_repo_task_outcomes(
        [_repo_task_record(patch={"path": "patch/fix-repo/rep-001.diff"})],
        result_dir,
    )[0]

    assert outcome.patch_bytes == 0
    assert outcome.outcome == "failed-no-mutation"


def test_repo_task_outcomes_classify_nonempty_failed_patch_as_mutation_visible(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run"
    patch = result_dir / "patch" / "fix-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff --git a/app.py b/app.py\n", encoding="utf-8")

    outcome = summarize_repo_task_outcomes(
        [_repo_task_record(patch={"path": "patch/fix-repo/rep-001.diff"})],
        result_dir,
    )[0]

    assert outcome.patch_bytes == 29
    assert outcome.outcome == "failed-with-mutation"


def test_repo_task_outcomes_classify_repo_task_passed_as_passed(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run"
    patch = result_dir / "patch" / "fix-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff --git a/app.py b/app.py\n", encoding="utf-8")

    outcome = summarize_repo_task_outcomes(
        [
            _repo_task_record(
                patch={"path": "patch/fix-repo/rep-001.diff"},
                scoring={"mode": "future-shape"},
                repo_status="passed",
            )
        ],
        result_dir,
    )[0]

    assert outcome.scoring == "unscored"
    assert outcome.outcome == "passed"
