#!/usr/bin/env python3
"""Deterministic reference harness for the public external-agent contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _fail(message: str) -> int:
    print(f"reference-agent: {message}", file=sys.stderr)
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


def _relative_to(path: Path, base: Path) -> Path | None:
    try:
        return path.relative_to(base)
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repetition", required=True)
    parser.add_argument("--context", required=True)
    args = parser.parse_args(argv)

    try:
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
        adapter = _object(context.get("adapter", {}), "context.adapter")

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
            _string(
                run.get("model_call_log_path"),
                "context.run.model_call_log_path",
            )
        ).resolve(strict=False)
        model_call_relative = _relative_to(model_call_log_path, output_dir_arg)
        if model_call_relative is None:
            raise ValueError("context.run.model_call_log_path escapes output dir")
        # Keep example-owned telemetry separate from normal adapter raw artifacts.
        if "raw" in model_call_relative.parts:
            raise ValueError("context.run.model_call_log_path must not be under raw")
        if not model_call_log_path.parent.is_dir():
            raise ValueError("context.run.model_call_log_path parent is missing")
        model = adapter.get("model")
        if not isinstance(model, str) or model == "":
            raise ValueError("context.adapter.model must be a non-empty string")
    except (OSError, ValueError) as exc:
        return _fail(str(exc))

    marker_path = workspace_arg / "external-agent-example.txt"
    marker_text = (
        "external-agent reference harness\n"
        f"case={args.case}\n"
        f"repetition={repetition}\n"
    )
    try:
        marker_path.write_text(marker_text, encoding="utf-8")
        model_call_log_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "sequence": 1,
                    "model": model,
                    "ok": True,
                }
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return _fail(f"could not write reference harness artifacts: {exc}")

    print(f"reference-agent wrote external-agent-example.txt for {args.case}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
