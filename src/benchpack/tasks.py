"""Deterministic task log artifacts for measured repo-task executions."""

from __future__ import annotations

import os
import re
import signal
import stat
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from time import monotonic, sleep

from .packs import Case, PUBLIC_HARNESS_FENCED_PATCH
from .safe_files import admitted_directory, atomic_write_at, trusted_root


# Keep timeout cleanup bounded while still giving cooperative harnesses a moment
# to flush output and exit before SIGKILL escalation.
_EXTERNAL_PROCESS_TIMEOUT_GRACE_S = 0.5
MAX_WORKSPACE_READ_BYTES = 16 * 1024 * 1024
MAX_WORKSPACE_ENTRIES = 100_000


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

        workspace_root = trusted_root(self.workspace)
        try:
            return _resolve_workspace_relative_path(relative_path, workspace_root)
        except _PatchContractError as exc:
            raise TaskError(f"unsafe harness workspace path: {exc}") from exc

    def _admission_base(self) -> Path:
        # The workspace root itself is walked without following links.
        return trusted_root(self.workspace).parent

    def read_workspace_text(self, relative_path: str) -> str:
        """Read bounded UTF-8 text through an admitted regular-file fd."""
        path = self.workspace_path(relative_path)
        try:
            with admitted_directory(path.parent, base=self._admission_base()) as directory:
                # Open relative to the admitted parent;
                # no path component can be followed again after admission.
                fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
                try:
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        raise OSError('workspace input must be regular')
                    chunks = []
                    total = 0
                    while total <= MAX_WORKSPACE_READ_BYTES:
                        chunk = os.read(fd, min(1024 * 1024, MAX_WORKSPACE_READ_BYTES + 1 - total))
                        if not chunk:
                            break
                        total += len(chunk)
                        chunks.append(chunk)
                    if total > MAX_WORKSPACE_READ_BYTES:
                        raise OSError('workspace read byte limit exceeded')
                    text = b''.join(chunks).decode('utf-8')
                finally:
                    os.close(fd)
            return text
        except (OSError, UnicodeError) as exc:
            raise TaskError(f"could not read harness workspace file {relative_path!r}") from exc

    def _inventory(self, *, directories: bool) -> tuple[str, ...]:
        paths = []
        count = 0
        root = trusted_root(self.workspace)

        def walk(directory, prefix):
            nonlocal count
            with os.scandir(directory) as entries:
                for entry in entries:
                    count += 1
                    if count > MAX_WORKSPACE_ENTRIES:
                        raise OSError('workspace inventory entry limit exceeded')
                    relative = f'{prefix}/{entry.name}' if prefix else entry.name
                    if entry.is_dir(follow_symlinks=False):
                        if directories:
                            paths.append(relative)
                        fd = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=directory)
                        try:
                            walk(fd, relative)
                            current = os.stat(entry.name, dir_fd=directory, follow_symlinks=False)
                            opened = os.fstat(fd)
                            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                                raise OSError('inventory directory was exchanged')
                        finally:
                            os.close(fd)
                    elif not directories:
                        # Escaping/dangling links are excluded from discovery.
                        candidate = (root / relative).resolve(strict=False)
                        if candidate.is_relative_to(root) and self.workspace_file_exists(relative):
                            paths.append(relative)

        try:
            with admitted_directory(root, base=root.parent) as directory:
                walk(directory, '')
        except (OSError, RecursionError) as exc:
            kind = 'directories' if directories else 'files'
            raise TaskError(f'could not list harness workspace {kind}') from exc
        return tuple(sorted(paths))

    def list_workspace_paths(self) -> tuple[str, ...]:
        """Return sorted paths, refusing incomplete discovery above the cap."""
        return self._inventory(directories=False)

    def list_workspace_dirs(self) -> tuple[str, ...]:
        """Return sorted non-symlink directories within the inventory cap."""
        return self._inventory(directories=True)

    def workspace_file_exists(self, relative_path: str) -> bool:
        path = self.workspace_path(relative_path)
        try:
            with admitted_directory(path.parent, base=self._admission_base()) as directory:
                mode = os.stat(path.name, dir_fd=directory, follow_symlinks=False).st_mode
                if stat.S_ISLNK(mode):
                    raise OSError('workspace entry was exchanged')
                return stat.S_ISREG(mode)
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise TaskError(f'could not inspect harness workspace file {relative_path!r}') from exc

    def delete_workspace_file(self, relative_path: str) -> bool:
        root = trusted_root(self.workspace)
        try:
            _resolve_workspace_relative_path(relative_path, root)
            raw = _raw_workspace_relative_path(relative_path, root)
        except _PatchContractError as exc:
            raise TaskError(f'unsafe harness workspace path: {exc}') from exc
        try:
            # Resolve only the parent: deleting an internal link removes the
            # link entry, while reads and replacements operate on its target.
            parent = raw.parent.resolve(strict=False)
            if not parent.is_relative_to(root):
                raise OSError('workspace parent escaped')
            with admitted_directory(parent, base=root.parent) as directory:
                info = os.stat(raw.name, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    if not self.workspace_file_exists(relative_path):
                        return False
                elif not stat.S_ISREG(info.st_mode):
                    return False
                os.unlink(raw.name, dir_fd=directory)
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise TaskError(f'could not delete harness workspace file {relative_path!r}') from exc

    def write_workspace_text(self, relative_path: str, content: str) -> None:
        path = self.workspace_path(relative_path)
        try:
            data = content.encode('utf-8')
            with admitted_directory(path.parent, base=self._admission_base(),
                                    create=True) as directory:
                atomic_write_at(directory, path.name, data)
        except (OSError, UnicodeError) as exc:
            raise TaskError(f'could not write harness workspace file {relative_path!r}') from exc


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

    return _write_task_logs(
        TaskExecutionRequest(output_dir, case, repetition, Path(output_dir), ""),
        stdout="", stderr="",
    )


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
    finished = False
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            stdout, stderr = _stop_external_process_group(process, case_id)
            finished = True
            return stdout, stderr, True
        result = _process_stream_to_text(stdout), _process_stream_to_text(stderr), False
        finished = True
        return result
    finally:
        primary = None if finished else sys.exception()
        try:
            if not finished:
                # communicate itself may be broken/interrupted. Reap without
                # relying on it again, preserving the original exception.
                try:
                    _reap_external_process_group(process, case_id)
                except BaseException as cleanup:
                    if primary is None:
                        raise
                    primary.add_note(f'external harness cleanup failed: {cleanup}')
        finally:
            close_error = None
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException as cleanup:
                        if primary is not None:
                            primary.add_note(f'external harness stream close failed: {cleanup}')
                        elif close_error is None:
                            close_error = cleanup
            if close_error is not None:
                raise close_error


def _reap_external_process_group(process, case_id):
    """Bounded cleanup even when collection fails or the leader has exited."""
    try:
        _signal_external_process_group(process.pid, signal.SIGTERM, case_id)
        # Keep the leader unreaped during grace so ownership remains attached
        # until the final group signal, even if it exits before descendants.
        sleep(_EXTERNAL_PROCESS_TIMEOUT_GRACE_S)
    finally:
        # start_new_session makes pid the owned pgid. Do not look it up via
        # a leader that may already have exited while descendants survive.
        try:
            _signal_external_process_group(process.pid, signal.SIGKILL, case_id)
        finally:
            process.wait(timeout=_EXTERNAL_PROCESS_TIMEOUT_GRACE_S)


def _stop_external_process_group(
    process: subprocess.Popen[str],
    case_id: str,
) -> tuple[str, str]:
    """Terminate a timed-out external harness process group and drain output."""

    pgid = process.pid
    primary = None
    try:
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
    except BaseException as exc:
        primary = exc
        raise
    finally:
        # A descendant can close its inherited pipes yet ignore termination.
        # communicate() has usually reaped the leader by now: macOS answers
        # EPERM for a group whose remaining members are already exiting, which
        # is the goal state here, not a runner error.
        try:
            _signal_external_process_group(pgid, signal.SIGKILL, case_id, exiting_ok=True)
        except BaseException as cleanup:
            if primary is None:
                raise
            primary.add_note(f'external harness kill failed: {cleanup}')


def _signal_external_process_group(
    pgid: int,
    signal_number: signal.Signals,
    case_id: str,
    *,
    exiting_ok: bool = False,
) -> None:
    """Send one signal to a harness process group, tolerating already-dead groups."""

    try:
        os.killpg(pgid, signal_number)
    except ProcessLookupError:
        return
    except PermissionError as exc:
        if exiting_ok:
            return
        raise TaskError(
            f"could not stop external subprocess harness process group for "
            f"repo-task case {case_id!r}"
        ) from exc
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
    task_record(paths, request.output_dir)  # Admit containment before any mutation.
    published = []
    try:
        # Encode both streams before touching either destination.
        streams = [(paths.stdout, stdout.encode('utf-8')),
                   (paths.stderr, stderr.encode('utf-8'))]
        with admitted_directory(paths.stdout.parent, base=request.output_dir,
                                create=True) as directory:
            # Reject either unsafe final destination before publishing stdout.
            for path, _ in streams:
                try:
                    mode = os.stat(path.name, dir_fd=directory, follow_symlinks=False).st_mode
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(mode):
                    raise OSError('task log destination must be regular')
            for path, data in streams:
                atomic_write_at(directory, path.name, data)
                published.append(path.name)
    except (OSError, UnicodeError) as exc:
        raise TaskError(
            f"could not write task logs for repo-task case {request.case.id!r}; "
            f"published logs: {', '.join(published) or 'none'}"
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

    deadline = None if timeout_s is None else monotonic() + timeout_s

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

    def remaining():
        if deadline is None:
            return None
        budget = deadline - monotonic()
        if budget <= 0:
            raise subprocess.TimeoutExpired('git apply --check', timeout_s)
        return budget

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
                timeout=remaining(),
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

    # Expiry before application starts is a safe rejection, not a partial edit.
    try:
        apply_budget = remaining()
    except subprocess.TimeoutExpired:
        return False, "", "Patch rejected: deadline exhausted; workspace left unchanged.\n"
    try:
        applied = subprocess.run(
            apply_command,
            input=diff,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=apply_budget,
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

    workspace_root = trusted_root(Path(workspace))
    try:
        destination = _resolve_workspace_relative_path(path, workspace_root)
    except _PatchContractError as exc:
        return False, "", f"Replacement file rejected: {exc}; workspace left unchanged.\n"
    published = False
    try:
        data = content.encode('utf-8')
        with admitted_directory(destination.parent, base=workspace_root.parent,
                                create=True) as directory:
            atomic_write_at(directory, destination.name, data)
            published = True
    except (OSError, UnicodeError) as exc:
        if published:
            raise TaskError("replacement published but workspace admission changed") from exc
        return (
            False, "",
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
    try:
        candidate = (workspace_root / Path(*parts)).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise _PatchContractError(f'could not resolve workspace path: {path}') from exc
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
