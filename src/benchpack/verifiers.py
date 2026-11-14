"""Deterministic verifier artifacts for measured repo-task executions."""

from __future__ import annotations

import json
import math
import os
import queue
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from .packs import Case, Pack, Scoring
from .safe_files import read_contained_regular
from .workspaces import PreparedWorkspace


DEFAULT_VERIFY_TIMEOUT_S = 300.0
MAX_VERIFY_JSON_BYTES = 1024 * 1024
MAX_VERIFY_LOG_STREAM_BYTES = 8 * 1024 * 1024
MAX_VERIFY_LOG_TOTAL_BYTES = 12 * 1024 * 1024
_LOG_CHUNK_BYTES = 65536


class VerifierOutputLimit(Exception):
    """The verifier exceeded its log disk allowance."""

    stdout: str = ""
    stderr: str = ""


class VerifierError(ValueError):
    """Raised when a repo-task verifier cannot be resolved or executed safely."""


@dataclass(frozen=True)
class VerifyArtifactPaths:
    """Absolute verifier artifact paths for one measured repetition."""

    json: Path
    stdout: Path
    stderr: Path


@dataclass(frozen=True)
class VerifierResult:
    """Result fields added to one measured repo-task row."""

    exit_code: int | None
    verify: dict[str, str]
    repo_task: dict[str, Any]
    scoring: dict[str, Any]


def verify_artifact_paths(
    output_dir: Path,
    case: Case,
    repetition: int,
) -> VerifyArtifactPaths:
    """Return deterministic verifier artifact paths for a case repetition."""

    if isinstance(repetition, bool) or not isinstance(repetition, int):
        raise ValueError("repetition must be an integer >= 1")
    if repetition < 1:
        raise ValueError("repetition must be an integer >= 1")
    stem = f"rep-{repetition:03d}"
    root = Path(output_dir) / "verify" / case.id
    return VerifyArtifactPaths(
        json=root / f"{stem}.json",
        stdout=root / f"{stem}.stdout.log",
        stderr=root / f"{stem}.stderr.log",
    )


def verify_record(paths: VerifyArtifactPaths, output_dir: Path) -> dict[str, str]:
    """Return the run.jsonl verify object for verifier artifacts."""

    base = Path(output_dir).resolve()
    try:
        json_path = paths.json.resolve().relative_to(base)
        stdout_path = paths.stdout.resolve().relative_to(base)
        stderr_path = paths.stderr.resolve().relative_to(base)
    except (OSError, ValueError) as exc:
        raise VerifierError(
            f"verifier artifact path is not under run output directory {output_dir}"
        ) from exc
    return {
        "path": json_path.as_posix(),
        "stdout_path": stdout_path.as_posix(),
        "stderr_path": stderr_path.as_posix(),
    }


def resolve_verify_script(pack: Pack, scoring: Scoring) -> Path:
    """Resolve a verify-script path relative to the pack root."""

    if scoring.script is None:
        raise VerifierError("scoring mode 'verify-script' requires 'script'")
    if not isinstance(scoring.script, str):
        raise VerifierError("scoring mode 'verify-script' requires string 'script'")

    raw_script = Path(scoring.script)
    if raw_script.is_absolute():
        raise VerifierError("verify-script path must be relative to the pack directory")

    try:
        pack_root = pack.path.resolve(strict=True)
    except OSError as exc:
        raise VerifierError(f"pack directory could not be resolved: {pack.path}") from exc

    candidate = pack_root / raw_script
    try:
        resolved_candidate = candidate.resolve(strict=False)
    except OSError as exc:
        raise VerifierError(
            f"verify-script path {scoring.script!r} could not be resolved"
        ) from exc
    if not resolved_candidate.is_relative_to(pack_root):
        raise VerifierError(
            f"verify-script path {scoring.script!r} escapes the pack directory"
        )

    try:
        resolved_script = candidate.resolve(strict=True)
    except OSError as exc:
        raise VerifierError(
            f"verify-script path {scoring.script!r} does not exist"
        ) from exc
    if not resolved_script.is_relative_to(pack_root):
        raise VerifierError(
            f"verify-script path {scoring.script!r} escapes the pack directory"
        )
    if not resolved_script.is_file():
        raise VerifierError(
            f"verify-script path {scoring.script!r} must be an existing file"
        )
    return resolved_script


def run_repo_task_verifier(
    *,
    pack: Pack,
    case: Case,
    scoring: Scoring,
    prepared_workspace: PreparedWorkspace,
    patch_path: Path,
    output_dir: Path,
    repetition: int,
    timeout_s: float = DEFAULT_VERIFY_TIMEOUT_S,
) -> VerifierResult:
    """Run a repo-task verifier and return fields for the result record."""

    script_path = resolve_verify_script(pack, scoring)
    paths = verify_artifact_paths(output_dir, case, repetition)
    paths.json.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(script_path),
        "--workspace",
        str(prepared_workspace.path.resolve()),
        "--case",
        case.id,
        "--pack-id",
        pack.id,
        "--pack-version",
        pack.version,
        "--source-fixture-id",
        prepared_workspace.source_fixture.id,
        "--patch",
        str(Path(patch_path).resolve()),
        "--output",
        str(paths.json.absolute()),
    ]

    run_kwargs: dict[str, Any] = {}
    if scoring.environment is not None:
        run_kwargs["env"] = {**os.environ, **scoring.environment}

    try:
        with paths.stdout.open("wb") as stdout, paths.stderr.open("wb") as stderr:
            completed = _run_verifier_command(
                command,
                stdout=stdout,
                stderr=stderr,
                timeout=timeout_s,
                **run_kwargs,
            )
    except (subprocess.TimeoutExpired, VerifierOutputLimit) as exc:
        extra = ({"output_limit": True} if isinstance(exc, VerifierOutputLimit)
                 else {"timed_out": True, "timeout_s": timeout_s})
        _write_authoritative_json(
            paths.json,
            exit_code=None,
            passed=False,
            extra_fields=extra,
        )
        return VerifierResult(
            exit_code=None,
            verify=verify_record(paths, output_dir),
            repo_task={"status": "failed", "verify_exit_code": None},
            scoring={"mode": "verify-script", "passed": False},
        )
    except OSError as exc:
        raise VerifierError(
            f"could not run verifier for repo-task case {case.id!r}"
        ) from exc

    exit_code = int(completed.returncode)
    passed = exit_code == 0
    _write_authoritative_json(paths.json, exit_code=exit_code, passed=passed)

    status = "passed" if passed else "failed"
    return VerifierResult(
        exit_code=exit_code,
        verify=verify_record(paths, output_dir),
        repo_task={"status": status, "verify_exit_code": exit_code},
        scoring={"mode": "verify-script", "passed": passed},
    )


_TIMEOUT_GRACE_S = 0.5
# After the verifier's process group is gone, a descendant that escaped it can
# still hold the pipes open; stop waiting for their EOF after this long.
_EOF_GRACE_S = 1.0
_DIAGNOSTIC_TAIL_BYTES = 65536


def _log_tail(stream: BinaryIO) -> str:
    """Read only a bounded UTF-8 diagnostic tail of the admitted log bytes."""

    # A separate open file description leaves inherited writer offsets alone.
    with open(stream.name, "rb") as reader:
        reader.seek(0, os.SEEK_END)
        reader.seek(max(0, reader.tell() - _DIAGNOSTIC_TAIL_BYTES))
        return reader.read(_DIAGNOSTIC_TAIL_BYTES).decode("utf-8", errors="replace")


def _wait_for_verifier(process: subprocess.Popen, timeout: float) -> None:
    """Wait for the leader and any remaining members of its POSIX group."""

    deadline = time.monotonic() + timeout
    process.wait(timeout=timeout)
    if os.name != "posix":
        return
    while True:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, timeout)
        time.sleep(min(0.01, remaining))


def _run_verifier_command(
    command: list[str], *, timeout: float, stdout: BinaryIO, stderr: BinaryIO,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Drain bounded pipe chunks into owned logs, stopping on disk overflow."""

    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
        start_new_session=os.name == "posix", **kwargs,
    )
    events: queue.Queue[tuple[int, bytes | OSError]] = queue.Queue(maxsize=4)
    stopping = threading.Event()

    def reader(index: int, pipe: BinaryIO) -> None:
        while not stopping.is_set():
            try:
                chunk = pipe.read(_LOG_CHUNK_BYTES)
            except OSError as exc:
                chunk = exc
            while not stopping.is_set():
                try:
                    events.put((index, chunk), timeout=0.05)
                    break
                except queue.Full:
                    continue
            if not chunk or isinstance(chunk, OSError):
                return

    assert process.stdout is not None and process.stderr is not None
    pipes = (process.stdout, process.stderr)
    readers = [threading.Thread(target=reader, args=(i, pipe), daemon=True)
               for i, pipe in enumerate(pipes)]
    logs = (stdout, stderr)
    counts = [0, 0]
    closed: set[int] = set()
    deadline = time.monotonic() + timeout

    def write_chunk(index: int, chunk: bytes) -> bool:
        """Write within the log ceilings; False when the chunk did not fit."""
        allowed = min(MAX_VERIFY_LOG_STREAM_BYTES - counts[index],
                      MAX_VERIFY_LOG_TOTAL_BYTES - sum(counts))
        written = min(len(chunk), max(allowed, 0))
        logs[index].write(chunk[:written])
        counts[index] += written
        return written == len(chunk)

    def drain(until: float) -> None:
        """Keep what a stopped verifier still wrote (e.g. a SIGTERM traceback)."""
        while len(closed) < 2:
            remaining = until - time.monotonic()
            if remaining <= 0:
                return
            try:
                index, chunk = events.get(timeout=min(0.05, remaining))
            except queue.Empty:
                continue
            if isinstance(chunk, OSError) or not chunk:
                closed.add(index)
                continue
            if not write_chunk(index, chunk):
                return

    gone_at: float | None = None
    try:
        for thread in readers:
            thread.start()
        while True:
            # Keep wait/interrupt handling under this process owner's cleanup.
            try:
                process.wait(timeout=0)
            except subprocess.TimeoutExpired:
                pass
            group_alive = process.returncode is None
            if os.name == "posix" and not group_alive:
                try:
                    os.killpg(process.pid, 0)
                    group_alive = True
                except ProcessLookupError:
                    group_alive = False
            if not group_alive and process.returncode is not None:
                if len(closed) == 2:
                    break
                now = time.monotonic()
                if gone_at is None:
                    gone_at = now
                elif now - gone_at >= _EOF_GRACE_S:
                    # Only an escaped descendant can still hold the pipes.
                    break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                index, chunk = events.get(timeout=min(0.01, remaining))
            except queue.Empty:
                continue
            if isinstance(chunk, OSError):
                raise chunk
            if not chunk:
                closed.add(index)
                continue
            if not write_chunk(index, chunk):
                raise VerifierOutputLimit("verifier log output limit exceeded")
    except subprocess.TimeoutExpired as exc:
        _stop_verifier(process)
        drain(time.monotonic() + _TIMEOUT_GRACE_S)
        stdout.flush()
        stderr.flush()
        raise subprocess.TimeoutExpired(
            command, timeout, output=_log_tail(stdout), stderr=_log_tail(stderr)
        ) from exc
    except VerifierOutputLimit as exc:
        _stop_verifier(process)
        stdout.flush()
        stderr.flush()
        exc.stdout = _log_tail(stdout)
        exc.stderr = _log_tail(stderr)
        raise
    except BaseException:
        _stop_verifier(process)
        raise
    finally:
        stopping.set()
        for thread in readers:
            if thread.ident is not None:
                thread.join(timeout=_TIMEOUT_GRACE_S)
        for pipe in pipes:
            pipe.close()
        stdout.flush()
        stderr.flush()
    return subprocess.CompletedProcess(
        command, process.returncode, _log_tail(stdout), _log_tail(stderr)
    )


def _stop_verifier(process: subprocess.Popen) -> None:
    def send(*, kill: bool = False) -> None:
        try:
            if os.name == "posix":
                # The leader may already have exited while descendants write logs.
                os.killpg(process.pid, signal.SIGKILL if kill else signal.SIGTERM)
            elif not kill:
                process.terminate()
            else:
                process.kill()
        except ProcessLookupError:
            pass

    send()
    try:
        _wait_for_verifier(process, _TIMEOUT_GRACE_S)
    except subprocess.TimeoutExpired:
        pass
    finally:
        # Leader exit alone does not prove that the entire group has stopped.
        send(kill=True)
    process.wait(timeout=_TIMEOUT_GRACE_S)


def _write_authoritative_json(
    path: Path,
    *,
    exit_code: int | None,
    passed: bool,
    extra_fields: dict[str, Any] | None = None,
) -> None:
    """Create or correct structured verifier JSON after process exit."""

    payload: dict[str, Any] = {}
    try:
        path.lstat()
    except FileNotFoundError:
        pass  # Supplemental output is optional.
    except OSError:
        payload["supplemental_error"] = "read_error"
    else:
        snapshot = read_contained_regular(path.parent, path.name, MAX_VERIFY_JSON_BYTES)
        if snapshot is None or snapshot.data is None:
            payload["supplemental_error"] = "read_error"
        else:
            try:
                loaded = json.loads(
                    snapshot.data.decode("utf-8"),
                    parse_constant=_refuse_json_constant,
                    parse_float=_finite_json_float,
                )
                if not isinstance(loaded, dict):
                    raise ValueError("expected object")
                # Serialization can hit a resource limit as well as decoding.
                json.dumps(loaded, allow_nan=False)
                payload = loaded
            except (ValueError, RecursionError, OverflowError, MemoryError):
                payload["supplemental_error"] = "invalid_json"

    if extra_fields is not None:
        payload.update(extra_fields)
    payload["exit_code"] = exit_code
    payload["passed"] = passed
    serialized = json.dumps(payload, sort_keys=True, allow_nan=False) + "\n"
    try:
        previous = path.lstat()
    except FileNotFoundError:
        previous = None
    temporary = path.parent / f".{path.name}-{uuid.uuid4().hex}.tmp"
    # Like safe_files.atomic_write_at: 0o666 lets the umask apply to new files,
    # and an existing regular file keeps its permissions.
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            if previous is not None and stat.S_ISREG(previous.st_mode):
                os.fchmod(stream.fileno(), stat.S_IMODE(previous.st_mode))
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _refuse_json_constant(value: str) -> Any:
    raise ValueError("nonfinite JSON number")


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("nonfinite JSON number")
    return parsed
