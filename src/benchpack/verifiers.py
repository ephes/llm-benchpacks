"""Deterministic verifier artifacts for measured repo-task executions."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from .packs import Case, Pack, Scoring
from .workspaces import PreparedWorkspace


DEFAULT_VERIFY_TIMEOUT_S = 300.0


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
        str(paths.json.resolve()),
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
    except subprocess.TimeoutExpired:
        _write_authoritative_json(
            paths.json,
            exit_code=None,
            passed=False,
            extra_fields={"timed_out": True, "timeout_s": timeout_s},
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
_DIAGNOSTIC_TAIL_BYTES = 65536


def _log_tail(stream: BinaryIO) -> str:
    """Read only a bounded UTF-8 diagnostic tail; logs retain the full bytes."""

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
    """Write output directly to owned logs with bounded process-group cleanup."""

    process = subprocess.Popen(
        command, stdout=stdout, stderr=stderr,
        start_new_session=os.name == "posix", **kwargs,
    )
    try:
        _wait_for_verifier(process, timeout)
    except subprocess.TimeoutExpired as exc:
        _stop_verifier(process)
        raise subprocess.TimeoutExpired(
            command, timeout, output=_log_tail(stdout), stderr=_log_tail(stderr)
        ) from exc
    except BaseException:
        # A terminal interrupt no longer reaches the isolated group.
        _stop_verifier(process)
        raise
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

    payload: dict[str, Any]
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = None
        payload = loaded if isinstance(loaded, dict) else {}
    else:
        payload = {}

    if extra_fields is not None:
        payload.update(extra_fields)
    payload["exit_code"] = exit_code
    payload["passed"] = passed
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
