"""Runner-owned JSON context for public external-agent repo-task harnesses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .packs import Case, Pack
from .tasks import TaskArtifactPaths
from .workspaces import PreparedWorkspace


class ExternalAgentContextError(ValueError):
    """Raised when an external-agent context file cannot be written safely."""


def external_agent_context_path(
    output_dir: Path,
    case: Case,
    repetition: int,
) -> Path:
    """Return the deterministic external-agent context path for one execution."""

    if isinstance(repetition, bool) or not isinstance(repetition, int):
        raise ValueError("repetition must be an integer >= 1")
    if repetition < 1:
        raise ValueError("repetition must be an integer >= 1")
    return (
        Path(output_dir)
        / "task"
        / case.id
        / f"rep-{repetition:03d}.context.json"
    )


def external_agent_model_call_log_path(
    output_dir: Path,
    case: Case,
    repetition: int,
) -> Path:
    """Return the optional external-agent model-call JSONL artifact path."""

    if isinstance(repetition, bool) or not isinstance(repetition, int):
        raise ValueError("repetition must be an integer >= 1")
    if repetition < 1:
        raise ValueError("repetition must be an integer >= 1")
    return (
        Path(output_dir)
        / "task"
        / case.id
        / f"rep-{repetition:03d}.model-calls.jsonl"
    )


def build_external_agent_context(
    *,
    pack: Pack,
    case: Case,
    prepared_workspace: PreparedWorkspace,
    output_dir: Path,
    repetition: int,
    task_paths: TaskArtifactPaths,
    adapter_id: str,
    model: str,
    endpoint: str | None,
    adapter_defaults: dict[str, Any],
    run_metadata_path: Path | None,
    model_call_log_path: Path,
) -> dict[str, Any]:
    """Build the JSON-serializable context for one external-agent execution."""

    harness = (
        None
        if case.harness is None
        else {"id": case.harness.id, "timeout_s": case.harness.timeout_s}
    )
    source_path = str(prepared_workspace.source_fixture.raw["path"])
    try:
        workspace_path = prepared_workspace.path.resolve(strict=True)
    except OSError as exc:
        raise ExternalAgentContextError(
            f"could not resolve external-agent workspace path "
            f"{prepared_workspace.path}"
        ) from exc

    return {
        "version": 1,
        "pack": {
            "id": pack.id,
            "version": pack.version,
            "description": pack.description,
        },
        "case": {
            "id": case.id,
            "kind": case.kind,
            "prompt": case.prompt,
            "fixture_refs": list(case.fixture_refs),
            "harness": harness,
        },
        "workspace": {
            "path": str(workspace_path),
            "source_fixture_id": prepared_workspace.source_fixture.id,
            "source_path": source_path,
        },
        "run": {
            "output_dir": str(Path(output_dir).resolve(strict=False)),
            "repetition": repetition,
            "task_stdout_path": str(task_paths.stdout.resolve(strict=False)),
            "task_stderr_path": str(task_paths.stderr.resolve(strict=False)),
            "run_metadata_path": (
                None
                if run_metadata_path is None
                else str(Path(run_metadata_path).resolve(strict=False))
            ),
            "model_call_log_path": str(
                Path(model_call_log_path).resolve(strict=False)
            ),
        },
        "adapter": {
            "id": adapter_id,
            "model": model,
            "endpoint": endpoint,
            "defaults": dict(adapter_defaults),
        },
        "fixtures": [
            {
                "id": fixture.id,
                "kind": fixture.kind,
                "path": str(fixture.raw["path"]),
                "description": fixture.description,
            }
            for fixture in pack.fixtures
        ],
    }


def write_external_agent_context(
    path: Path,
    context: dict[str, Any],
) -> Path:
    """Write a deterministic external-agent context JSON file."""

    output_path = Path(path)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(context, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ExternalAgentContextError(
            f"could not write external-agent context file {output_path}"
        ) from exc
    return output_path
