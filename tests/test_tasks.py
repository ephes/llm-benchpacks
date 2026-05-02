"""Tests for deterministic repo-task task log helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchpack.packs import Case
from benchpack.tasks import (
    TaskArtifactPaths,
    TaskError,
    task_artifact_paths,
    task_record,
    write_noop_task_logs,
)


def make_case() -> Case:
    return Case(
        id="edit-repo",
        kind="repo-task",
        prompt="Change the repository.",
        scoring=None,
        raw={},
    )


def test_task_artifact_paths_use_run_relative_layout(tmp_path: Path) -> None:
    paths = task_artifact_paths(tmp_path / "run", make_case(), 1)

    assert paths.stdout == (
        tmp_path / "run" / "task" / "edit-repo" / "rep-001.stdout.log"
    )
    assert paths.stderr == (
        tmp_path / "run" / "task" / "edit-repo" / "rep-001.stderr.log"
    )


@pytest.mark.parametrize("repetition", [0, -1, True, "1"])
def test_task_artifact_paths_reject_invalid_repetition(
    tmp_path: Path,
    repetition: object,
) -> None:
    with pytest.raises(ValueError, match="repetition"):
        task_artifact_paths(
            tmp_path / "run",
            make_case(),
            repetition,  # type: ignore[arg-type]
        )


def test_task_record_uses_run_relative_posix_paths(tmp_path: Path) -> None:
    out = tmp_path / "run"
    paths = TaskArtifactPaths(
        stdout=out / "task" / "edit-repo" / "rep-001.stdout.log",
        stderr=out / "task" / "edit-repo" / "rep-001.stderr.log",
    )

    assert task_record(paths, out) == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }


def test_task_record_rejects_paths_outside_output_dir(tmp_path: Path) -> None:
    paths = TaskArtifactPaths(
        stdout=tmp_path / "outside" / "rep-001.stdout.log",
        stderr=tmp_path / "run" / "task" / "edit-repo" / "rep-001.stderr.log",
    )

    with pytest.raises(TaskError, match="not under run output directory"):
        task_record(paths, tmp_path / "run")


def test_write_noop_task_logs_creates_empty_logs_and_record(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"

    record = write_noop_task_logs(out, make_case(), 1)

    assert record == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert (out / record["stdout_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["stderr_path"]).read_text(encoding="utf-8") == ""
