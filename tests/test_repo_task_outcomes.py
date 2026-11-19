"""Tests for report-only repo-task outcome summaries."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from benchpack.repo_task_outcomes import (
    RepoTaskOutcome,
    count_repo_task_outcomes,
    summarize_repo_task_outcomes,
)


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


def test_repo_task_outcomes_treat_missing_artifact_root_as_unknown() -> None:
    outcome = summarize_repo_task_outcomes(
        [_repo_task_record(patch={"path": "patch/fix-repo/rep-001.diff"})],
        None,
    )[0]

    assert outcome.patch_bytes is None
    assert outcome.outcome == "failed-unknown-mutation"


def test_repo_task_outcomes_classify_nonempty_failed_patch_as_source_mutation(
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
    assert outcome.outcome == "failed-source-mutation"


def test_repo_task_outcomes_parse_quoted_git_diff_paths_with_spaces(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run"
    patch = result_dir / "patch" / "fix-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text(
        'diff --git "a/generated data/cache.pyc" "b/source dir/app file.py"\n',
        encoding="utf-8",
    )

    outcome = summarize_repo_task_outcomes(
        [_repo_task_record(patch={"path": "patch/fix-repo/rep-001.diff"})],
        result_dir,
    )[0]

    assert outcome.outcome == "failed-source-mutation"


@pytest.mark.parametrize(
    ("former", "current", "expected"),
    [
        ("a/src/app.py", ".cache/app.py", "failed-source-mutation"),
        (".cache/app.py", "b/src/app.py", "failed-source-mutation"),
        ("src data/app.py", ".cache/app.py", "failed-source-mutation"),
        (".cache/archive file.py", ".cache/app.py", "failed-non-source-mutation"),
        (".cache/archive file.pyc", "résumé file.pyc", "failed-non-source-mutation"),
    ],
)
def test_repo_task_outcomes_classify_both_git_rename_paths(
    tmp_path: Path, former: str, current: str, expected: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    old_path = repo / former
    new_path = repo / current
    old_path.parent.mkdir(parents=True)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.write_text("same contents\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", "--", former], cwd=repo, check=True)
    baseline = subprocess.check_output(["git", "write-tree"], cwd=repo).decode().strip()
    subprocess.run(["git", "mv", "--", former, current], cwd=repo, check=True)
    patch = subprocess.check_output(
        ["git", "-c", "core.quotePath=true", "diff", "--cached", "--find-renames",
         "--default-prefix", "--no-ext-diff", "--no-color", baseline],
        cwd=repo,
    )
    assert b"rename from " in patch and b"rename to " in patch
    assert b"\n--- " not in patch and b"\n+++ " not in patch
    (tmp_path / "rename.diff").write_bytes(patch)

    [outcome] = summarize_repo_task_outcomes(
        [_repo_task_record(patch={"path": "rename.diff"})], tmp_path,
    )

    assert outcome.patch_bytes == len(patch)
    assert outcome.outcome == expected


def test_repo_task_outcomes_classify_generated_only_patch_as_non_source_mutation(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run"
    patch = result_dir / "patch" / "fix-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text(
        "\n".join(
            [
                "Binary file added: __pycache__/task_summary.cpython-313.pyc",
                "--- /dev/null",
                "+++ b/.pytest_cache/v/cache/nodeids",
                "@@ -0,0 +1 @@",
                "+[]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    outcome = summarize_repo_task_outcomes(
        [_repo_task_record(patch={"path": "patch/fix-repo/rep-001.diff"})],
        result_dir,
    )[0]

    assert outcome.outcome == "failed-non-source-mutation"


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


def test_repo_task_outcome_counts_aggregate_known_labels(tmp_path: Path) -> None:
    result_dir = tmp_path / "run"
    passing_patch = result_dir / "patch" / "passed" / "rep-001.diff"
    passing_patch.parent.mkdir(parents=True)
    passing_patch.write_text("diff --git a/app.py b/app.py\n", encoding="utf-8")
    empty_patch = result_dir / "patch" / "empty" / "rep-001.diff"
    empty_patch.parent.mkdir(parents=True)
    empty_patch.write_text("", encoding="utf-8")
    failed_patch = result_dir / "patch" / "failed" / "rep-001.diff"
    failed_patch.parent.mkdir(parents=True)
    failed_patch.write_text("diff --git a/other.py b/other.py\n", encoding="utf-8")

    outcomes = summarize_repo_task_outcomes(
        [
            _repo_task_record(
                patch={"path": "patch/passed/rep-001.diff"},
                repo_status="passed",
            ),
            _repo_task_record(patch={"path": "patch/empty/rep-001.diff"}),
            _repo_task_record(patch={"path": "patch/failed/rep-001.diff"}),
            _repo_task_record(patch={"path": "patch/missing/rep-001.diff"}),
        ],
        result_dir,
    )

    counts = count_repo_task_outcomes(outcomes)

    assert counts.total == 4
    assert counts.passed == 1
    assert counts.failed_no_mutation == 1
    assert counts.failed_source_mutation == 1
    assert counts.failed_non_source_mutation == 0
    assert counts.failed_unknown_mutation == 1
    assert counts.other == 0


def test_repo_task_outcome_counts_preserve_unknown_labels_as_other() -> None:
    counts = count_repo_task_outcomes(
        [
            RepoTaskOutcome(
                case="fix-repo",
                repetition=1,
                repo_status="failed",
                verify_exit_code=1,
                scoring="verify-script:fail",
                patch_bytes=None,
                outcome="future-label",
            )
        ]
    )

    assert counts.total == 1
    assert counts.passed == 0
    assert counts.failed_no_mutation == 0
    assert counts.failed_source_mutation == 0
    assert counts.failed_non_source_mutation == 0
    assert counts.failed_unknown_mutation == 0
    assert counts.other == 1
