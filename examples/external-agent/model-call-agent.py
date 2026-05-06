#!/usr/bin/env python3
"""Deterministic local model-call-shaped external-agent example."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ALLOWED_WORKSPACE_FILE = "external-agent-model-call.txt"


def _fail(message: str) -> int:
    print(f"model-call-agent: {message}", file=sys.stderr)
    return 2


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer when present")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
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


def _validate_model_call_url(raw_url: str) -> str:
    parsed = urllib.parse.urlsplit(raw_url)
    if parsed.scheme != "http" or parsed.hostname is None:
        raise ValueError("--model-call-url must be an http loopback URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("--model-call-url must not contain credentials")
    if parsed.query:
        raise ValueError("--model-call-url must not contain a query string")
    hostname = parsed.hostname.lower()
    is_loopback = hostname == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise ValueError("--model-call-url must use a loopback host")
    return raw_url


def _load_and_validate_context(args: argparse.Namespace) -> tuple[Path, Path, Path, str]:
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
        _string(run.get("model_call_log_path"), "context.run.model_call_log_path")
    ).resolve(strict=False)
    model_call_relative = _relative_to(model_call_log_path, output_dir_arg)
    if model_call_relative is None:
        raise ValueError("context.run.model_call_log_path escapes output dir")
    if "raw" in model_call_relative.parts:
        raise ValueError("context.run.model_call_log_path must not be under raw")
    if not model_call_log_path.parent.is_dir():
        raise ValueError("context.run.model_call_log_path parent is missing")

    model = adapter.get("model")
    if not isinstance(model, str) or model == "":
        raise ValueError("context.adapter.model must be a non-empty string")

    return workspace_arg, output_dir_arg, model_call_log_path, model


def _call_local_model(
    *,
    url: str,
    case_id: str,
    repetition: int,
    model: str,
) -> tuple[dict[str, Any], float]:
    body = json.dumps(
        {
            "case": case_id,
            "repetition": repetition,
            "model": model,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = response.read()
    except urllib.error.URLError as exc:
        raise ValueError(f"local model call failed: {exc}") from exc
    duration_s = time.monotonic() - started
    try:
        return _object(json.loads(payload.decode("utf-8")), "model response"), duration_s
    except UnicodeDecodeError as exc:
        raise ValueError("local model response must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"could not parse local model response JSON: {exc}") from exc


def _validate_response(response: dict[str, Any], model: str) -> dict[str, Any]:
    if response.get("ok") is not True:
        raise ValueError("model response.ok must be true")
    if response.get("workspace_file") != ALLOWED_WORKSPACE_FILE:
        raise ValueError(
            f"model response.workspace_file must be {ALLOWED_WORKSPACE_FILE!r}"
        )
    content = response.get("content")
    if not isinstance(content, str):
        raise ValueError("model response.content must be a string")
    response_model = response.get("model")
    if response_model is not None:
        if not isinstance(response_model, str) or response_model == "":
            raise ValueError("model response.model must be a non-empty string")
        if response_model != model:
            raise ValueError("model response.model does not match context model")
    return {
        "content": content,
        "prompt_tokens": _optional_int(
            response.get("prompt_tokens"),
            "model response.prompt_tokens",
        ),
        "output_tokens": _optional_int(
            response.get("output_tokens"),
            "model response.output_tokens",
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-call-url", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repetition", required=True)
    parser.add_argument("--context", required=True)
    args = parser.parse_args(argv)

    try:
        url = _validate_model_call_url(args.model_call_url)
        repetition = int(args.repetition)
        workspace, _, model_call_log_path, model = _load_and_validate_context(args)
        response, duration_s = _call_local_model(
            url=url,
            case_id=args.case,
            repetition=repetition,
            model=model,
        )
        validated = _validate_response(response, model)
    except (OSError, ValueError) as exc:
        return _fail(str(exc))

    target_path = workspace / ALLOWED_WORKSPACE_FILE
    telemetry = {
        "schema_version": 1,
        "sequence": 1,
        "model": model,
        "ok": True,
        "adapter": "example-local-http",
        "endpoint": "local-http",
        "duration_s": round(duration_s, 6),
    }
    if validated["prompt_tokens"] is not None:
        telemetry["prompt_tokens"] = validated["prompt_tokens"]
    if validated["output_tokens"] is not None:
        telemetry["output_tokens"] = validated["output_tokens"]

    try:
        target_path.write_text(validated["content"], encoding="utf-8")
        model_call_log_path.write_text(
            json.dumps(telemetry, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return _fail(f"could not write model-call example artifacts: {exc}")

    print(f"model-call-agent wrote {ALLOWED_WORKSPACE_FILE} for {args.case}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
