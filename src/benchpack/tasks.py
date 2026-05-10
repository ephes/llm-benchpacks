"""Deterministic task log artifacts for measured repo-task executions."""

from __future__ import annotations

import os
import re
import signal
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath

from .packs import Case, PUBLIC_HARNESS_FENCED_PATCH


# Keep timeout cleanup bounded while still giving cooperative harnesses a moment
# to flush output and exit before SIGKILL escalation.
_EXTERNAL_PROCESS_TIMEOUT_GRACE_S = 0.5


class TaskError(ValueError):
    """Raised when repo-task task log artifacts cannot be recorded safely."""


@dataclass(frozen=True)
class TaskArtifactPaths:
    """Absolute task stdout/stderr artifact paths for one measured repetition."""

    stdout: Path
    stderr: Path


@dataclass(frozen=True)
class AgentSessionHarnessResult:
    """Internal result from one agent-session harness task phase."""

    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class AgentSessionHarnessRequest:
    """Internal runner-owned context for an agent-session harness.

    ``task_paths`` are deterministic destinations the runner populates from the
    returned stdout/stderr strings; harnesses should not write them directly.
    """

    output_dir: Path
    case: Case
    repetition: int
    workspace: Path
    model_output_text: str
    task_paths: TaskArtifactPaths

    def workspace_path(self, relative_path: str) -> Path:
        """Resolve a harness workspace-relative path, rejecting escapes."""

        workspace_root = self.workspace.resolve(strict=False)
        try:
            return _resolve_workspace_relative_path(relative_path, workspace_root)
        except _PatchContractError as exc:
            raise TaskError(f"unsafe harness workspace path: {exc}") from exc

    def read_workspace_text(self, relative_path: str) -> str:
        """Read UTF-8 text from a file below the prepared workspace only."""

        path = self.workspace_path(relative_path)
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise TaskError(
                f"could not read harness workspace file {relative_path!r} "
                f"for repo-task case {self.case.id!r}"
            ) from exc

    def list_workspace_paths(self) -> tuple[str, ...]:
        """Return sorted POSIX file paths below the prepared workspace."""

        workspace_root = self.workspace.resolve(strict=False)
        try:
            if not workspace_root.is_dir():
                raise OSError(f"workspace is not a directory: {workspace_root}")
            paths = [
                child.relative_to(workspace_root).as_posix()
                for child in workspace_root.rglob("*")
                if child.is_file()
                and child.resolve(strict=False).is_relative_to(workspace_root)
            ]
        except OSError as exc:
            raise TaskError(
                f"could not list harness workspace files for repo-task case "
                f"{self.case.id!r}"
            ) from exc
        return tuple(sorted(paths))

    def list_workspace_dirs(self) -> tuple[str, ...]:
        """Return sorted POSIX directory paths below the prepared workspace."""

        workspace_root = self.workspace.resolve(strict=False)
        try:
            if not workspace_root.is_dir():
                raise OSError(f"workspace is not a directory: {workspace_root}")
            paths = [
                child.relative_to(workspace_root).as_posix()
                for child in workspace_root.rglob("*")
                if not child.is_symlink()
                and child.is_dir()
                and child.resolve(strict=False).is_relative_to(workspace_root)
            ]
        except OSError as exc:
            raise TaskError(
                f"could not list harness workspace directories for repo-task case "
                f"{self.case.id!r}"
            ) from exc
        return tuple(sorted(paths))

    def workspace_file_exists(self, relative_path: str) -> bool:
        """Return whether a regular file exists below the prepared workspace."""

        path = self.workspace_path(relative_path)
        try:
            return path.is_file()
        except OSError as exc:
            raise TaskError(
                f"could not inspect harness workspace file {relative_path!r} "
                f"for repo-task case {self.case.id!r}"
            ) from exc

    def delete_workspace_file(self, relative_path: str) -> bool:
        """Delete a regular file entry below the prepared workspace if present."""

        workspace_root = self.workspace.resolve(strict=False)
        try:
            path = _resolve_workspace_relative_path(relative_path, workspace_root)
            raw_path = _raw_workspace_relative_path(relative_path, workspace_root)
        except _PatchContractError as exc:
            raise TaskError(f"unsafe harness workspace path: {exc}") from exc

        try:
            if raw_path.is_symlink():
                if not path.is_file():
                    return False
                raw_path.unlink()
                return True
            if not path.exists() or not path.is_file():
                return False
            path.unlink()
        except OSError as exc:
            raise TaskError(
                f"could not delete harness workspace file {relative_path!r} "
                f"for repo-task case {self.case.id!r}"
            ) from exc
        return True

    def write_workspace_text(self, relative_path: str, content: str) -> None:
        """Write UTF-8 text below the prepared workspace only."""

        path = self.workspace_path(relative_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise TaskError(
                f"could not write harness workspace file {relative_path!r} "
                f"for repo-task case {self.case.id!r}"
            ) from exc


AgentSessionHarness = Callable[[AgentSessionHarnessRequest], AgentSessionHarnessResult]


@dataclass(frozen=True)
class ExternalProcessHarness:
    """Runner-owned subprocess harness invocation for one repo-task phase.

    ``argv`` is supplied by runner-side code or tests, not by pack manifests.
    The executor runs it without a shell and appends explicit context arguments
    for the prepared workspace, case id, output directory, repetition, and
    optional runner-owned context JSON file.
    """

    argv: Sequence[str]


@dataclass(frozen=True)
class TaskExecutionRequest:
    """Runner-side request for executing one measured repo-task phase."""

    output_dir: Path
    case: Case
    repetition: int
    workspace: Path
    model_output_text: str
    harness_id: str | None = None
    task_timeout_s: float | None = None
    agent_session_harness: AgentSessionHarness | None = None
    external_process_harness: ExternalProcessHarness | None = None
    external_context_path: Path | None = None


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

    The default executor is the fenced model-output patch bridge. Public
    ``harness_id`` selection currently accepts only ``"fenced-patch"`` and
    routes to that same executor. Internal in-process agent-session and
    external-process harnesses can still be supplied by runner-side tests or
    future implementation code.
    """

    if (
        request.harness_id is not None
        and request.agent_session_harness is not None
    ):
        raise TaskError(
            "public harness_id cannot be combined with internal "
            "agent_session_harness"
        )
    if (
        request.harness_id is not None
        and request.external_process_harness is not None
    ):
        raise TaskError(
            "public harness_id cannot be combined with internal "
            "external_process_harness"
        )
    if (
        request.agent_session_harness is not None
        and request.external_process_harness is not None
    ):
        raise TaskError(
            "internal agent_session_harness cannot be combined with internal "
            "external_process_harness"
        )
    if (
        request.task_timeout_s is not None
        and request.agent_session_harness is not None
    ):
        raise TaskError(
            "task_timeout_s cannot be combined with internal agent_session_harness"
        )
    if request.harness_id is not None:
        if request.harness_id != PUBLIC_HARNESS_FENCED_PATCH:
            raise TaskError(f"unknown repo-task harness id {request.harness_id!r}")
        return _run_fenced_model_patch_executor(request)
    if request.agent_session_harness is not None:
        return _run_agent_session_harness_executor(
            request,
            request.agent_session_harness,
        )
    if request.external_process_harness is not None:
        return _run_external_process_harness_executor(
            request,
            request.external_process_harness,
        )
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
        _, stdout, stderr = apply_fenced_edit_to_workspace(
            patch,
            request.workspace,
            timeout_s=request.task_timeout_s,
        )

    return _write_task_logs(request, stdout=stdout, stderr=stderr)


def _run_agent_session_harness_executor(
    request: TaskExecutionRequest,
    harness: AgentSessionHarness,
) -> dict[str, str]:
    """Run an internal agent-session harness and record existing task logs."""

    paths = task_artifact_paths(request.output_dir, request.case, request.repetition)
    harness_request = AgentSessionHarnessRequest(
        output_dir=request.output_dir,
        case=request.case,
        repetition=request.repetition,
        workspace=request.workspace,
        model_output_text=request.model_output_text,
        task_paths=paths,
    )
    result = harness(harness_request)
    if not isinstance(result, AgentSessionHarnessResult):
        raise TaskError(
            "agent-session harness must return AgentSessionHarnessResult"
        )
    if not isinstance(result.stdout, str) or not isinstance(result.stderr, str):
        raise TaskError("agent-session harness stdout/stderr must be strings")
    return _write_task_logs(request, stdout=result.stdout, stderr=result.stderr)


def _run_external_process_harness_executor(
    request: TaskExecutionRequest,
    harness: ExternalProcessHarness,
) -> dict[str, str]:
    """Run a runner-owned subprocess harness and record existing task logs."""

    command, workspace = _external_process_command(request, harness)
    try:
        stdout, stderr, timed_out = _run_external_process_command(
            command,
            workspace,
            timeout_s=request.task_timeout_s,
            case_id=request.case.id,
        )
    except OSError as exc:
        raise TaskError(
            f"could not run external subprocess harness for repo-task case "
            f"{request.case.id!r}"
        ) from exc

    if timed_out:
        stderr += (
            f"External subprocess harness timed out after "
            f"{request.task_timeout_s:g} seconds; process stopped.\n"
        )
        return _write_task_logs(request, stdout=stdout, stderr=stderr)

    return _write_task_logs(
        request,
        stdout=stdout,
        stderr=stderr,
    )


def _run_external_process_command(
    command: Sequence[str],
    workspace: Path,
    *,
    timeout_s: float | None,
    case_id: str,
) -> tuple[str, str, bool]:
    """Run an external harness subprocess with POSIX process-group cleanup."""

    process = subprocess.Popen(
        command,
        cwd=workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_s)
        return (
            _process_stream_to_text(stdout),
            _process_stream_to_text(stderr),
            False,
        )
    except subprocess.TimeoutExpired:
        stdout, stderr = _stop_external_process_group(process, case_id)
        return stdout, stderr, True


def _stop_external_process_group(
    process: subprocess.Popen[str],
    case_id: str,
) -> tuple[str, str]:
    """Terminate a timed-out external harness process group and drain output."""

    try:
        pgid = os.getpgid(process.pid)
    except ProcessLookupError:
        return _communicate_after_external_timeout(process, case_id)
    except OSError as exc:
        raise TaskError(
            f"could not inspect external subprocess harness process group for "
            f"repo-task case {case_id!r}"
        ) from exc

    _signal_external_process_group(pgid, signal.SIGTERM, case_id)
    try:
        return _communicate_after_external_timeout(process, case_id)
    except subprocess.TimeoutExpired:
        _signal_external_process_group(pgid, signal.SIGKILL, case_id)
        try:
            return _communicate_after_external_timeout(process, case_id)
        except subprocess.TimeoutExpired as exc:
            raise TaskError(
                f"could not stop external subprocess harness process group for "
                f"repo-task case {case_id!r}"
            ) from exc


def _signal_external_process_group(
    pgid: int,
    signal_number: signal.Signals,
    case_id: str,
) -> None:
    """Send one signal to a harness process group, tolerating already-dead groups."""

    try:
        os.killpg(pgid, signal_number)
    except ProcessLookupError:
        return
    except OSError as exc:
        raise TaskError(
            f"could not stop external subprocess harness process group for "
            f"repo-task case {case_id!r}"
        ) from exc


def _communicate_after_external_timeout(
    process: subprocess.Popen[str],
    case_id: str,
) -> tuple[str, str]:
    """Drain process output after timeout signaling with a bounded wait."""

    try:
        stdout, stderr = process.communicate(
            timeout=_EXTERNAL_PROCESS_TIMEOUT_GRACE_S
        )
    except OSError as exc:
        raise TaskError(
            f"could not collect external subprocess harness logs for "
            f"repo-task case {case_id!r}"
        ) from exc
    return _process_stream_to_text(stdout), _process_stream_to_text(stderr)


def _external_process_command(
    request: TaskExecutionRequest,
    harness: ExternalProcessHarness,
) -> tuple[list[str], Path]:
    """Return validated subprocess argv plus runner-owned context arguments."""

    argv = harness.argv
    if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
        raise TaskError("external subprocess harness argv must be a sequence")
    command = list(argv)
    if not command:
        raise TaskError("external subprocess harness argv must not be empty")
    for argument in command:
        if not isinstance(argument, str) or argument == "" or "\x00" in argument:
            raise TaskError(
                "external subprocess harness argv entries must be non-empty "
                "strings without NUL bytes"
            )

    try:
        workspace = request.workspace.resolve(strict=True)
    except OSError as exc:
        raise TaskError(
            f"could not resolve external subprocess harness workspace path "
            f"{request.workspace} for repo-task case {request.case.id!r}"
        ) from exc
    try:
        output_dir = request.output_dir.resolve(strict=False)
    except OSError as exc:
        raise TaskError(
            f"could not resolve external subprocess harness output directory "
            f"{request.output_dir} for repo-task case {request.case.id!r}"
        ) from exc
    context_path = None
    if request.external_context_path is not None:
        try:
            context_path = request.external_context_path.resolve(strict=True)
        except OSError as exc:
            raise TaskError(
                f"could not resolve external subprocess harness context path "
                f"{request.external_context_path} for repo-task case "
                f"{request.case.id!r}"
            ) from exc
    if not workspace.is_dir():
        raise TaskError(
            f"external subprocess harness workspace is not a directory for "
            f"repo-task case {request.case.id!r}"
        )

    return (
        [
            *command,
            "--workspace",
            str(workspace),
            "--case",
            request.case.id,
            "--output-dir",
            str(output_dir),
            "--repetition",
            str(request.repetition),
            *(
                []
                if context_path is None
                else ["--context", str(context_path)]
            ),
        ],
        workspace,
    )


def _write_task_logs(
    request: TaskExecutionRequest,
    *,
    stdout: str,
    stderr: str,
) -> dict[str, str]:
    """Write deterministic task stdout/stderr logs for one execution."""

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


def _process_stream_to_text(value: str | bytes | None) -> str:
    """Normalize captured process output to text for task logs."""

    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def extract_fenced_patch(output_text: str) -> str | None:
    """Return the first fenced ``diff`` or ``patch`` block from model output."""

    fence_pattern = re.compile(
        r"(?ms)^```(?P<info>[^\r\n]*)\r?\n(?P<body>.*?)^```[ \t]*\r?$"
    )
    for match in fence_pattern.finditer(output_text):
        if match.group("info") in {"diff", "patch"}:
            return match.group("body")
    return None


def apply_unified_diff_to_workspace(
    diff: str,
    workspace: Path,
    *,
    timeout_s: float | None = None,
) -> tuple[bool, str, str]:
    """Apply a unified diff in ``workspace`` using the narrow task contract.

    Post-preflight apply timeouts raise ``TaskError`` because the workspace may
    be partially changed.
    """

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
    apply_command: list[str] | None = None
    try:
        for check_command, candidate_apply_command in (
            (
                ["git", "apply", "--check", "--whitespace=nowarn", "--recount"],
                ["git", "apply", "--whitespace=nowarn", "--recount"],
            ),
            # Keep the historical path as a compatibility fallback for any
            # git/version-specific diff form that rejects recount preflight.
            (
                ["git", "apply", "--check", "--whitespace=nowarn"],
                ["git", "apply", "--whitespace=nowarn"],
            ),
        ):
            check = subprocess.run(
                check_command,
                input=diff,
                cwd=workspace_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_s,
            )
            if check.returncode == 0:
                apply_command = candidate_apply_command
                break
    except subprocess.TimeoutExpired:
        return (
            False,
            "",
            "Patch rejected: git apply --check timed out; workspace left "
            "unchanged.\n",
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

    if apply_command is None:
        return (
            False,
            "",
            "Patch rejected: unified diff could not be applied cleanly; "
            "workspace left unchanged.\n",
        )

    try:
        applied = subprocess.run(
            apply_command,
            input=diff,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise TaskError(
            "patch application timed out after preflight; workspace may be "
            "partially changed"
        ) from exc
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


def apply_fenced_edit_to_workspace(
    block: str,
    workspace: Path,
    *,
    timeout_s: float | None = None,
) -> tuple[bool, str, str]:
    """Apply a fenced repo-task edit block to ``workspace``.

    The compatibility path remains a unified diff. A deliberately marked
    full-file replacement block is also accepted for endpoint-only models that
    can produce correct code but not a valid unified diff.
    """

    replacement = _parse_replacement_file_block(block)
    if replacement is None:
        return apply_unified_diff_to_workspace(
            block,
            workspace,
            timeout_s=timeout_s,
        )
    path, content, error = replacement
    if error is not None:
        return (
            False,
            "",
            f"Replacement file rejected: {error}; workspace left unchanged.\n",
        )
    return _apply_replacement_file_to_workspace(path, content, workspace)


def _parse_replacement_file_block(block: str) -> tuple[str, str, str | None] | None:
    normalized = block.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines(keepends=True)
    if not lines:
        return None

    first_line = lines[0].rstrip("\n")
    prefix = "*** Begin File: "
    if not first_line.startswith(prefix):
        return None
    path = first_line[len(prefix) :].strip()
    if not path:
        return ("", "", "missing file path")

    end_index: int | None = None
    for index in range(len(lines) - 1, 0, -1):
        if lines[index].rstrip() == "*** End File":
            end_index = index
            break
        if lines[index].strip():
            break
    if end_index is None:
        return (path, "", "missing end marker")

    return path, "".join(lines[1:end_index]), None


def _apply_replacement_file_to_workspace(
    path: str,
    content: str,
    workspace: Path,
) -> tuple[bool, str, str]:
    if content == "":
        return (
            False,
            "",
            "Replacement file rejected: empty file content; workspace left "
            "unchanged.\n",
        )

    workspace_root = Path(workspace).resolve(strict=False)
    try:
        destination = _resolve_workspace_relative_path(path, workspace_root)
    except _PatchContractError as exc:
        return (
            False,
            "",
            f"Replacement file rejected: {exc}; workspace left unchanged.\n",
        )
    try:
        if destination.exists() and destination.is_dir():
            return (
                False,
                "",
                "Replacement file rejected: target path is a directory; "
                "workspace left unchanged.\n",
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    except OSError:
        return (
            False,
            "",
            "Replacement file rejected: workspace file could not be written; "
            "workspace left unchanged.\n",
        )

    return True, "Applied fenced model replacement file to workspace.\n", ""


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
    _resolve_workspace_relative_path(path, workspace_root)


def _resolve_workspace_relative_path(path: str, workspace_root: Path) -> Path:
    parts = _workspace_relative_parts(path)
    candidate = (workspace_root / Path(*parts)).resolve(strict=False)
    if not candidate.is_relative_to(workspace_root):
        raise _PatchContractError(f"path escapes workspace: {path}")
    return candidate


def _raw_workspace_relative_path(path: str, workspace_root: Path) -> Path:
    parts = _workspace_relative_parts(path)
    return workspace_root / Path(*parts)


def _workspace_relative_parts(path: str) -> tuple[str, ...]:
    if "\x00" in path:
        raise _PatchContractError("path contains a null byte")
    relative = PurePosixPath(path)
    if relative.is_absolute():
        raise _PatchContractError(f"path escapes workspace: {path}")
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise _PatchContractError(f"path escapes workspace: {path}")
    return relative.parts
