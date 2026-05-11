"""Report-only summaries for repo-task outcome artifacts."""

from __future__ import annotations

import stat
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


MISSING = "—"
OUTCOME_PASSED = "passed"
OUTCOME_FAILED_NO_MUTATION = "failed-no-mutation"
OUTCOME_FAILED_SOURCE_MUTATION = "failed-source-mutation"
OUTCOME_FAILED_NON_SOURCE_MUTATION = "failed-non-source-mutation"
OUTCOME_FAILED_UNKNOWN_MUTATION = "failed-unknown-mutation"
KNOWN_OUTCOME_LABELS = (
    OUTCOME_PASSED,
    OUTCOME_FAILED_NO_MUTATION,
    OUTCOME_FAILED_SOURCE_MUTATION,
    OUTCOME_FAILED_NON_SOURCE_MUTATION,
    OUTCOME_FAILED_UNKNOWN_MUTATION,
)

_GENERATED_DIR_NAMES = frozenset(
    {
        ".cache",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "node_modules",
    }
)
_GENERATED_FILE_SUFFIXES = frozenset(
    {
        ".a",
        ".bin",
        ".class",
        ".db",
        ".dll",
        ".dylib",
        ".lib",
        ".o",
        ".obj",
        ".pyc",
        ".pyd",
        ".pyo",
        ".so",
        ".sqlite",
        ".sqlite3",
    }
)
_GENERATED_FILE_NAMES = frozenset({".coverage"})


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


@dataclass(frozen=True)
class RepoTaskOutcomeCounts:
    """Aggregate counts for report-facing repo-task outcome labels."""

    total: int
    passed: int
    failed_no_mutation: int
    failed_source_mutation: int
    failed_non_source_mutation: int
    failed_unknown_mutation: int
    other: int


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
        patch_paths = _patch_paths(record, result_dir)
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
                    patch_bytes=patch_bytes,
                    patch_paths=patch_paths,
                ),
            )
        )
    return outcomes


def count_repo_task_outcomes(
    outcomes: list[RepoTaskOutcome],
) -> RepoTaskOutcomeCounts:
    """Count compact repo-task outcome labels for summary tables."""

    counts = {label: 0 for label in KNOWN_OUTCOME_LABELS}
    other = 0
    for outcome in outcomes:
        if outcome.outcome in counts:
            counts[outcome.outcome] += 1
        else:
            other += 1
    return RepoTaskOutcomeCounts(
        total=len(outcomes),
        passed=counts[OUTCOME_PASSED],
        failed_no_mutation=counts[OUTCOME_FAILED_NO_MUTATION],
        failed_source_mutation=counts[OUTCOME_FAILED_SOURCE_MUTATION],
        failed_non_source_mutation=counts[OUTCOME_FAILED_NON_SOURCE_MUTATION],
        failed_unknown_mutation=counts[OUTCOME_FAILED_UNKNOWN_MUTATION],
        other=other,
    )


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
    patch_path = _safe_patch_path(record, result_dir)
    if patch_path is None:
        return None
    try:
        patch_stat = patch_path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(patch_stat.st_mode):
        return None
    return patch_stat.st_size


def _patch_paths(
    record: dict[str, Any],
    result_dir: Path | None,
) -> tuple[str, ...] | None:
    patch_path = _safe_patch_path(record, result_dir)
    if patch_path is None:
        return None
    try:
        patch_stat = patch_path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(patch_stat.st_mode):
        return None
    try:
        lines = patch_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    return _extract_patch_paths(lines)


def _safe_patch_path(
    record: dict[str, Any],
    result_dir: Path | None,
) -> Path | None:
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
    return patch_path


def _extract_patch_paths(lines: list[str]) -> tuple[str, ...]:
    paths: list[str] = []
    seen: set[str] = set()
    for line in lines:
        path = _path_from_patch_line(line)
        if path is None or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return tuple(paths)


def _path_from_patch_line(line: str) -> str | None:
    if line.startswith("diff --git "):
        return _path_from_git_diff_line(line)
    for prefix in ("--- ", "+++ "):
        if line.startswith(prefix):
            return _normalize_diff_label(line[len(prefix) :])
    for prefix in (
        "Binary file added: ",
        "Binary file deleted: ",
        "Binary files differ: ",
    ):
        if line.startswith(prefix):
            path = line[len(prefix) :].strip()
            return path or None
    return None


def _path_from_git_diff_line(line: str) -> str | None:
    body = line.removeprefix("diff --git ").strip()
    try:
        parts = shlex.split(body)
    except ValueError:
        parts = []
    if len(parts) >= 2:
        return _normalize_diff_label(parts[1])
    separator = " b/"
    if separator not in body:
        return None
    return _normalize_diff_label(body.rsplit(separator, 1)[1])


def _normalize_diff_label(label: str) -> str | None:
    path = label.strip().split("\t", 1)[0]
    if path == "/dev/null":
        return None
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path or None


def _is_source_path(path: str) -> bool:
    posix_path = PurePosixPath(path)
    parts = posix_path.parts
    if any(part in _GENERATED_DIR_NAMES for part in parts):
        return False
    if not parts:
        return False
    name = parts[-1]
    if name in _GENERATED_FILE_NAMES:
        return False
    suffixes = PurePosixPath(name).suffixes
    if suffixes and suffixes[-1].lower() in _GENERATED_FILE_SUFFIXES:
        return False
    return True


def _classify_outcome(
    *,
    repo_status: str,
    patch_bytes: int | None,
    patch_paths: tuple[str, ...] | None,
) -> str:
    if repo_status == "passed":
        return OUTCOME_PASSED
    if patch_bytes == 0:
        return OUTCOME_FAILED_NO_MUTATION
    if patch_bytes is not None and patch_bytes > 0 and patch_paths:
        if any(_is_source_path(path) for path in patch_paths):
            return OUTCOME_FAILED_SOURCE_MUTATION
        return OUTCOME_FAILED_NON_SOURCE_MUTATION
    return OUTCOME_FAILED_UNKNOWN_MUTATION
