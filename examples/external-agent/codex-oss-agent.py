#!/usr/bin/env python3
"""Run Codex CLI as a local OSS external-agent harness.

This wrapper adapts the public benchpack external-agent argv/context handoff to
``codex exec --oss --local-provider <provider>``. It is intended for local
evidence slices where Codex is configured to use a local provider such as
Ollama, not for cloud-backed or credentialed runs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _fail(message: str) -> int:
    print(f"codex-oss-agent: {message}", file=sys.stderr)
    return 2


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _load_context(path: Path) -> dict[str, Any]:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), "context")
    except OSError as exc:
        raise ValueError(f"could not read context: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"could not parse context JSON: {exc}") from exc


def _load_and_validate_context(
    args: argparse.Namespace,
) -> tuple[Path, Path, Path, str]:
    repetition = int(args.repetition)
    if repetition < 1:
        raise ValueError("repetition must be a positive integer")

    workspace_arg = Path(args.workspace).resolve(strict=True)
    output_dir_arg = Path(args.output_dir).resolve(strict=True)
    context = _load_context(Path(args.context))

    if context.get("version") != 1:
        raise ValueError("context.version must be 1")
    case = _object(context.get("case"), "context.case")
    run = _object(context.get("run"), "context.run")
    workspace = _object(context.get("workspace"), "context.workspace")

    if _string(case.get("id"), "context.case.id") != args.case:
        raise ValueError("context.case.id does not match --case")
    if run.get("repetition") != repetition:
        raise ValueError("context.run.repetition does not match --repetition")

    context_workspace = Path(
        _string(workspace.get("path"), "context.workspace.path")
    ).resolve(strict=True)
    if context_workspace != workspace_arg:
        raise ValueError("context.workspace.path does not match --workspace")

    context_output_dir = Path(
        _string(run.get("output_dir"), "context.run.output_dir")
    ).resolve(strict=True)
    if context_output_dir != output_dir_arg:
        raise ValueError("context.run.output_dir does not match --output-dir")

    model_call_log_path = Path(
        _string(run.get("model_call_log_path"), "context.run.model_call_log_path")
    ).resolve(strict=False)
    try:
        model_call_log_path.relative_to(output_dir_arg)
    except ValueError as exc:
        raise ValueError("context.run.model_call_log_path escapes output dir") from exc
    if not model_call_log_path.parent.is_dir():
        raise ValueError("context.run.model_call_log_path parent is missing")

    prompt = _string(case.get("prompt"), "context.case.prompt")
    return workspace_arg, output_dir_arg, model_call_log_path, prompt


def _build_codex_prompt(*, case_id: str, prompt: str) -> str:
    return (
        "You are running as a benchpack external-agent harness inside a "
        "disposable benchmark workspace.\n\n"
        "Edit files directly in the current workspace to satisfy the task. "
        "Do not modify files outside the current workspace. Do not create a "
        "patch file for the runner; the runner will capture the workspace diff "
        "after you exit. If the task text asks for a fenced diff, treat that as "
        "the source workload's original output contract and instead make the "
        "corresponding direct file edits in this workspace.\n\n"
        f"Case id: {case_id}\n\n"
        "Task prompt:\n"
        f"{prompt}\n"
    )


def _write_telemetry(
    path: Path,
    *,
    model: str,
    provider: str,
    duration_s: float,
    ok: bool,
) -> None:
    payload: dict[str, object] = {
        "schema_version": 1,
        "sequence": 1,
        "model": model,
        "ok": ok,
        "adapter": "codex-cli",
        "endpoint": provider,
        "duration_s": round(duration_s, 6),
    }
    try:
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"could not write model-call telemetry: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--codex-model", required=True)
    parser.add_argument("--local-provider", default="ollama")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repetition", required=True)
    parser.add_argument("--context", required=True)
    args = parser.parse_args(argv)

    try:
        workspace, _, model_call_log_path, prompt = _load_and_validate_context(args)
    except (OSError, ValueError) as exc:
        return _fail(str(exc))

    codex_prompt = _build_codex_prompt(case_id=args.case, prompt=prompt)
    command = [
        args.codex_bin,
        "exec",
        "--oss",
        "--local-provider",
        args.local_provider,
        "--model",
        args.codex_model,
        "--skip-git-repo-check",
        "--cd",
        str(workspace),
        "--sandbox",
        "workspace-write",
        "--ephemeral",
        codex_prompt,
    ]
    started = time.monotonic()
    try:
        completed = subprocess.run(command, check=False, cwd=workspace, text=True)
    except OSError as exc:
        return _fail(f"could not run codex: {exc}")
    duration_s = time.monotonic() - started

    try:
        _write_telemetry(
            model_call_log_path,
            model=args.codex_model,
            provider=args.local_provider,
            duration_s=duration_s,
            ok=completed.returncode == 0,
        )
    except ValueError as exc:
        return _fail(str(exc))

    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
