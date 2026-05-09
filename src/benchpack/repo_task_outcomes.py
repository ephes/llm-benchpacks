"""Report-only summaries for repo-task outcome artifacts."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MISSING = "—"


@dataclass(frozen=True)
class RepoTaskOutcome:
    """Compact report-facing summary for one repo-task result row."""

    case: str
    repetition: int | None
    repo_status: str
    verify_exit_code: int | None
    scoring: str
    patch_bytes: int | None
    outcome: str


def summarize_repo_task_outcomes(
    records: list[dict[str, Any]],
    result_dir: Path | None,
) -> list[RepoTaskOutcome]:
    """Return compact repo-task outcomes without changing result records."""

    outcomes: list[RepoTaskOutcome] = []
    for record in records:
        repo_task = record.get("repo_task")
        if not isinstance(repo_task, dict):
            continue
        case = record.get("case")
        if not isinstance(case, str):
            case = MISSING
        repetition = _repetition(record.get("repetition"))
        repo_status = _repo_status(repo_task.get("status"))
        verify_exit_code = _verify_exit_code(repo_task.get("verify_exit_code"))
        scoring = _scoring_label(record.get("scoring"))
        patch_bytes = _patch_bytes(record, result_dir)
        outcomes.append(
            RepoTaskOutcome(
                case=case,
                repetition=repetition,
                repo_status=repo_status,
                verify_exit_code=verify_exit_code,
                scoring=scoring,
                patch_bytes=patch_bytes,
                outcome=_classify_outcome(
                    repo_status=repo_status,
                    scoring=scoring,
                    patch_bytes=patch_bytes,
                ),
            )
        )
    return outcomes


def format_repetition(repetition: int | None) -> str:
    """Render a repetition value for Markdown tables."""

    return str(repetition) if repetition is not None else MISSING


def format_verify_exit_code(exit_code: int | None) -> str:
    """Render a verifier exit code for Markdown tables."""

    return str(exit_code) if exit_code is not None else MISSING


def format_patch_bytes(patch_bytes: int | None) -> str:
    """Render patch byte count for Markdown tables."""

    return str(patch_bytes) if patch_bytes is not None else MISSING


def _repetition(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 1:
        return None
    return value


def _repo_status(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    return MISSING


def _verify_exit_code(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _scoring_label(value: Any) -> str:
    if not isinstance(value, dict):
        return "unscored"
    mode = value.get("mode")
    passed = value.get("passed")
    if not isinstance(mode, str) or not isinstance(passed, bool):
        return "unscored"
    result = "pass" if passed else "fail"
    return f"{mode}:{result}"


def _patch_bytes(record: dict[str, Any], result_dir: Path | None) -> int | None:
    if result_dir is None:
        return None
    patch = record.get("patch")
    if not isinstance(patch, dict):
        return None
    raw_path = patch.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    if Path(raw_path).is_absolute():
        return None
    result_root = result_dir.resolve()
    patch_path = (result_root / raw_path).resolve(strict=False)
    try:
        patch_path.relative_to(result_root)
    except ValueError:
        return None
    try:
        patch_stat = patch_path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(patch_stat.st_mode):
        return None
    return patch_stat.st_size


def _classify_outcome(
    *,
    repo_status: str,
    scoring: str,
    patch_bytes: int | None,
) -> str:
    if repo_status == "passed":
        return "passed"
    if patch_bytes == 0:
        return "failed-no-mutation"
    if patch_bytes is not None and patch_bytes > 0:
        return "failed-with-mutation"
    return "failed-unknown-mutation"
