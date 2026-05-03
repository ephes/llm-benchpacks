"""Deterministic task log artifacts for measured repo-task executions."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath

from .packs import Case


class TaskError(ValueError):
    """Raised when repo-task task log artifacts cannot be recorded safely."""


@dataclass(frozen=True)
class TaskArtifactPaths:
    """Absolute task stdout/stderr artifact paths for one measured repetition."""

    stdout: Path
    stderr: Path


@dataclass(frozen=True)
class TaskExecutionRequest:
    """Runner-side request for executing one measured repo-task phase."""

    output_dir: Path
    case: Case
    repetition: int
    workspace: Path
    model_output_text: str


class _PatchContractError(ValueError):
    """Raised when model output does not satisfy the narrow patch contract."""


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
    """Write empty task logs for callers that need placeholder artifacts."""

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


def run_model_patch_task(
    output_dir: Path,
    case: Case,
    repetition: int,
    workspace: Path,
    output_text: str,
) -> dict[str, str]:
    """Apply the first fenced model patch block and write task logs.

    Retained for direct helper tests and callers that predate the internal
    executor boundary; the CLI uses ``run_repo_task_executor``.
    """

    return _run_fenced_model_patch_executor(
        TaskExecutionRequest(
            output_dir=output_dir,
            case=case,
            repetition=repetition,
            workspace=workspace,
            model_output_text=output_text,
        )
    )


def run_repo_task_executor(request: TaskExecutionRequest) -> dict[str, str]:
    """Execute the current internal repo-task task phase.

    The only implemented executor is the fenced model-output patch bridge.
    Selection of other executors is intentionally not a manifest or CLI surface.
    """

    return _run_fenced_model_patch_executor(request)


def _run_fenced_model_patch_executor(
    request: TaskExecutionRequest,
) -> dict[str, str]:
    """Apply the first fenced model patch block and write task logs.

    Missing or unapplicable model patches are task-phase outcomes, not runner
    failures. They are written to stderr so downstream patch capture and
    verifier execution can observe the unchanged workspace.
    """

    stdout = ""
    stderr = ""
    patch = extract_fenced_patch(request.model_output_text)
    if patch is None:
        stderr = (
            "No fenced diff or patch block found in model output; "
            "workspace left unchanged.\n"
        )
    else:
        _, stdout, stderr = apply_unified_diff_to_workspace(
            patch,
            request.workspace,
        )

    paths = task_artifact_paths(request.output_dir, request.case, request.repetition)
    try:
        paths.stdout.parent.mkdir(parents=True, exist_ok=True)
        paths.stdout.write_text(stdout, encoding="utf-8")
        paths.stderr.write_text(stderr, encoding="utf-8")
    except OSError as exc:
        raise TaskError(
            f"could not write task logs for repo-task case {request.case.id!r}"
        ) from exc
    return task_record(paths, request.output_dir)


def extract_fenced_patch(output_text: str) -> str | None:
    """Return the first fenced ``diff`` or ``patch`` block from model output."""

    fence_pattern = re.compile(
        r"(?ms)^```(?P<info>[^\r\n]*)\r?\n(?P<body>.*?)^```[ \t]*\r?$"
    )
    for match in fence_pattern.finditer(output_text):
        if match.group("info") in {"diff", "patch"}:
            return match.group("body")
    return None


def apply_unified_diff_to_workspace(diff: str, workspace: Path) -> tuple[bool, str, str]:
    """Apply a unified diff in ``workspace`` using the narrow task contract."""

    if not diff.strip():
        return (
            False,
            "",
            "Patch rejected: fenced patch block is empty; workspace left unchanged.\n",
        )

    try:
        _validate_patch_paths(diff, workspace)
    except _PatchContractError as exc:
        return False, "", f"Patch rejected: {exc}; workspace left unchanged.\n"

    workspace_path = Path(workspace)
    try:
        check = subprocess.run(
            ["git", "apply", "--check", "--whitespace=nowarn"],
            input=diff,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return (
            False,
            "",
            "Patch rejected: git executable not found; workspace left unchanged.\n",
        )
    except OSError:
        return (
            False,
            "",
            "Patch rejected: workspace could not be accessed; workspace left unchanged.\n",
        )

    if check.returncode != 0:
        return (
            False,
            "",
            "Patch rejected: unified diff could not be applied cleanly; "
            "workspace left unchanged.\n",
        )

    try:
        applied = subprocess.run(
            ["git", "apply", "--whitespace=nowarn"],
            input=diff,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return (
            False,
            "",
            "Patch application failed after preflight; workspace may be partially "
            "changed.\n",
        )
    if applied.returncode != 0:
        return (
            False,
            "",
            "Patch application failed after preflight; workspace may be partially "
            "changed.\n",
        )

    return True, "Applied fenced model patch to workspace.\n", ""


def _validate_patch_paths(diff: str, workspace: Path) -> None:
    paths: list[str] = []
    for line in diff.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            path = _path_from_unified_header(line[4:])
            if path is not None:
                paths.append(path)
        elif line.startswith("diff --git "):
            paths.extend(_paths_from_git_header(line))

    if not paths:
        raise _PatchContractError("no file paths found in unified diff")

    workspace_root = Path(workspace).resolve(strict=False)
    for path in paths:
        _validate_workspace_relative_path(path, workspace_root)


def _path_from_unified_header(label: str) -> str | None:
    path = _decode_patch_path(label.split("\t", 1)[0])
    if path == "/dev/null":
        return None
    return _strip_diff_prefix(path)


def _paths_from_git_header(line: str) -> list[str]:
    parts = line.split()
    if len(parts) != 4:
        return []
    return [
        _strip_diff_prefix(_decode_patch_path(parts[2])),
        _strip_diff_prefix(_decode_patch_path(parts[3])),
    ]


def _decode_patch_path(path: str) -> str:
    if len(path) < 2 or path[0] != '"' or path[-1] != '"':
        return path
    try:
        return bytes(path[1:-1], "utf-8").decode("unicode_escape")
    except UnicodeDecodeError as exc:
        raise _PatchContractError("malformed quoted path") from exc


def _strip_diff_prefix(path: str) -> str:
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _validate_workspace_relative_path(path: str, workspace_root: Path) -> None:
    if "\x00" in path:
        raise _PatchContractError("path contains a null byte")
    relative = PurePosixPath(path)
    if relative.is_absolute():
        raise _PatchContractError(f"path escapes workspace: {path}")
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise _PatchContractError(f"path escapes workspace: {path}")

    candidate = (workspace_root / Path(*relative.parts)).resolve(strict=False)
    if not candidate.is_relative_to(workspace_root):
        raise _PatchContractError(f"path escapes workspace: {path}")
