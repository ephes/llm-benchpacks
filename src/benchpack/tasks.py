"""Deterministic task log artifacts for measured repo-task executions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .packs import Case


class TaskError(ValueError):
    """Raised when repo-task task log artifacts cannot be recorded safely."""


@dataclass(frozen=True)
class TaskArtifactPaths:
    """Absolute task stdout/stderr artifact paths for one measured repetition."""

    stdout: Path
    stderr: Path


def task_artifact_paths(
    output_dir: Path,
    case: Case,
    repetition: int,
) -> TaskArtifactPaths:
    """Return deterministic task log artifact paths for a case repetition."""

    if isinstance(repetition, bool) or not isinstance(repetition, int):
        raise ValueError("repetition must be an integer >= 1")
    if repetition < 1:
        raise ValueError("repetition must be an integer >= 1")
    stem = f"rep-{repetition:03d}"
    root = Path(output_dir) / "task" / case.id
    return TaskArtifactPaths(
        stdout=root / f"{stem}.stdout.log",
        stderr=root / f"{stem}.stderr.log",
    )


def task_record(paths: TaskArtifactPaths, output_dir: Path) -> dict[str, str]:
    """Return the run.jsonl task object for task log artifacts."""

    base = Path(output_dir).resolve()
    try:
        stdout_path = paths.stdout.resolve().relative_to(base)
        stderr_path = paths.stderr.resolve().relative_to(base)
    except (OSError, ValueError) as exc:
        raise TaskError(
            f"task artifact path is not under run output directory {output_dir}"
        ) from exc
    return {
        "stdout_path": stdout_path.as_posix(),
        "stderr_path": stderr_path.as_posix(),
    }


def write_noop_task_logs(output_dir: Path, case: Case, repetition: int) -> dict[str, str]:
    """Write empty task logs for the current runner-owned no-op task phase."""

    paths = task_artifact_paths(output_dir, case, repetition)
    try:
        paths.stdout.parent.mkdir(parents=True, exist_ok=True)
        paths.stdout.write_text("", encoding="utf-8")
        paths.stderr.write_text("", encoding="utf-8")
    except OSError as exc:
        raise TaskError(
            f"could not write task logs for repo-task case {case.id!r}"
        ) from exc
    return task_record(paths, output_dir)
