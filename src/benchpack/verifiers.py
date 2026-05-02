"""Deterministic verifier artifacts for measured repo-task executions."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .packs import Case, Pack, Scoring
from .workspaces import PreparedWorkspace


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

    exit_code: int
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

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        paths.stdout.write_text(completed.stdout, encoding="utf-8")
        paths.stderr.write_text(completed.stderr, encoding="utf-8")
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


def _write_authoritative_json(path: Path, *, exit_code: int, passed: bool) -> None:
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

    payload["exit_code"] = exit_code
    payload["passed"] = passed
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
