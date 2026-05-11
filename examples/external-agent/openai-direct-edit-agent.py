#!/usr/bin/env python3
"""Call an OpenAI-compatible chat endpoint and apply direct workspace edits."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


_ALLOWED_PATH_HEADING_RE = re.compile(r"^Allowed repo-root paths? to edit:\s*$")
_ALLOWED_PATH_RE = re.compile(r"^- `([^`]+)`\s*$")


def _fail(message: str) -> int:
    print(f"openai-direct-edit-agent: {message}", file=sys.stderr)
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
        relative_log_path = model_call_log_path.relative_to(output_dir_arg)
    except ValueError as exc:
        raise ValueError("context.run.model_call_log_path escapes output dir") from exc
    if "raw" in relative_log_path.parts:
        raise ValueError("context.run.model_call_log_path must not be under raw")
    if not model_call_log_path.parent.is_dir():
        raise ValueError("context.run.model_call_log_path parent is missing")

    return workspace_arg, output_dir_arg, model_call_log_path, _string(
        case.get("prompt"),
        "context.case.prompt",
    )


def _chat_completions_url(endpoint: str) -> str:
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or parsed.netloc == "":
        raise ValueError("--endpoint must be an http or https URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("--endpoint must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("--endpoint must not contain query or fragment")
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        final_path = path
    else:
        final_path = f"{path}/chat/completions"
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, final_path, "", "")
    )


def _safe_endpoint_label(endpoint: str) -> str:
    parsed = urllib.parse.urlsplit(endpoint)
    return parsed.hostname or "openai-compatible"


def _allowed_paths(prompt: str) -> tuple[str, ...]:
    values: list[str] = []
    in_allowed_section = False
    saw_allowed_bullet = False
    for line in prompt.splitlines():
        if not in_allowed_section:
            if _ALLOWED_PATH_HEADING_RE.match(line):
                in_allowed_section = True
            continue
        match = _ALLOWED_PATH_RE.match(line)
        if match is not None:
            values.append(match.group(1))
            saw_allowed_bullet = True
            continue
        if not line.strip():
            continue
        if saw_allowed_bullet:
            break
        break
    values = list(dict.fromkeys(values))
    if not values:
        raise ValueError("could not determine allowed edit paths from prompt")
    return tuple(values)


def _workspace_path(workspace: Path, relative_path: str) -> Path:
    if relative_path.startswith("/") or "\x00" in relative_path:
        raise ValueError(f"unsafe edit path: {relative_path!r}")
    parts = Path(relative_path).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe edit path: {relative_path!r}")
    target = (workspace / relative_path).resolve(strict=False)
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(f"edit path escapes workspace: {relative_path!r}") from exc
    return target


def _build_messages(prompt: str, allowed_paths: tuple[str, ...]) -> list[dict[str, str]]:
    allowed = "\n".join(f"- {path}" for path in allowed_paths)
    system = (
        "You are an external benchmark agent. Return only JSON, with no "
        "Markdown fences and no commentary. The JSON schema is: "
        '{"files":[{"path":"repo-relative path","content":"full UTF-8 file content"}],'
        '"summary":"short summary"}. '
        "Only include files that must be changed. Use full replacement file "
        "content, not diffs. Do not include tests, generated artifacts, logs, "
        "raw payloads, metadata, or files outside the allowed path list."
    )
    user = (
        f"Allowed edit paths:\n{allowed}\n\n"
        "Apply the benchmark task by returning replacement content for the "
        "needed allowed files.\n\n"
        f"{prompt}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _response_format_payload(
    response_format: str,
    allowed_paths: tuple[str, ...],
) -> dict[str, Any] | None:
    if response_format == "default":
        return None
    if response_format == "json_object":
        return {"type": "json_object"}
    if response_format == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "benchpack_direct_edit",
                "description": (
                    "Full-file replacements for the prepared benchmark workspace."
                ),
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["files", "summary"],
                    "properties": {
                        "files": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["path", "content"],
                                "properties": {
                                    "path": {
                                        "type": "string",
                                        "enum": list(allowed_paths),
                                    },
                                    "content": {"type": "string"},
                                },
                            },
                        },
                        "summary": {"type": "string"},
                    },
                },
            },
        }
    raise ValueError(f"unsupported response format: {response_format}")


def _call_chat_completion(
    *,
    endpoint: str,
    api_key: str,
    model: str,
    prompt: str,
    allowed_paths: tuple[str, ...],
    timeout_s: float,
    temperature: float,
    max_tokens: int,
    token_budget_field: str,
    response_format: str,
) -> tuple[dict[str, Any], float]:
    if token_budget_field not in {"max_tokens", "max_completion_tokens"}:
        raise ValueError(f"unsupported token budget field: {token_budget_field}")
    request_body = {
        "model": model,
        "messages": _build_messages(prompt, allowed_paths),
        "temperature": temperature,
        "stream": False,
        token_budget_field: max_tokens,
    }
    response_format_payload = _response_format_payload(response_format, allowed_paths)
    if response_format_payload is not None:
        request_body["response_format"] = response_format_payload
    data = json.dumps(request_body).encode("utf-8")
    request = urllib.request.Request(
        _chat_completions_url(endpoint),
        data=data,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise ValueError(f"chat completion failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"chat completion failed: {exc}") from exc
    duration_s = time.monotonic() - started
    try:
        return _object(json.loads(payload.decode("utf-8")), "chat response"), duration_s
    except UnicodeDecodeError as exc:
        raise ValueError("chat response must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"could not parse chat response JSON: {exc}") from exc


def _assistant_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("chat response.choices must be a non-empty array")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("chat response choice must be an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("chat response choice.message must be an object")
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal:
        raise ValueError(f"chat response message.refusal: {refusal[:180]}")
    return _string(message.get("content"), "chat response message.content")


def _finish_reason(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    reason = first.get("finish_reason")
    return reason if isinstance(reason, str) else ""


def _parse_edit_payload(content: str, *, finish_reason: str = "") -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1] == "```":
            text = "\n".join(lines[1:-1]).strip()
    try:
        return _object(json.loads(text), "assistant edit payload")
    except json.JSONDecodeError as exc:
        detail = f"could not parse assistant edit payload JSON: {exc}"
        if finish_reason:
            detail = f"chat finish_reason={finish_reason}; {detail}"
        raise ValueError(detail) from exc


def _apply_edits(
    workspace: Path,
    payload: dict[str, Any],
    allowed_paths: tuple[str, ...],
) -> tuple[int, str]:
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError("assistant edit payload.files must be an array")
    allowed = set(allowed_paths)
    changed = 0
    for index, item in enumerate(files, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"assistant edit payload.files[{index}] must be an object")
        path = _string(item.get("path"), f"assistant edit payload.files[{index}].path")
        if path not in allowed:
            raise ValueError(f"assistant attempted to edit disallowed path: {path}")
        content = item.get("content")
        if not isinstance(content, str):
            raise ValueError(
                f"assistant edit payload.files[{index}].content must be a string"
            )
        target = _workspace_path(workspace, path)
        if not target.is_file():
            raise ValueError(f"assistant edit target is not a file: {path}")
        target.write_text(content, encoding="utf-8")
        changed += 1
    summary = payload.get("summary")
    return changed, summary if isinstance(summary, str) and summary else ""


def _usage_tokens(response: dict[str, Any], key: str) -> int | None:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _write_telemetry(
    path: Path,
    *,
    model: str,
    endpoint: str,
    duration_s: float,
    ok: bool,
    response: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "schema_version": 1,
        "sequence": 1,
        "model": model,
        "ok": ok,
        "adapter": "openai-chat",
        "endpoint": _safe_endpoint_label(endpoint),
        "duration_s": round(duration_s, 6),
    }
    if response is not None:
        prompt_tokens = _usage_tokens(response, "prompt_tokens")
        output_tokens = _usage_tokens(response, "completion_tokens")
        if prompt_tokens is not None:
            payload["prompt_tokens"] = prompt_tokens
        if output_tokens is not None:
            payload["output_tokens"] = output_tokens
    if error:
        payload["error"] = error[:180]
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env", required=True)
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument(
        "--token-budget-field",
        choices=("max_tokens", "max_completion_tokens"),
        default="max_tokens",
        help=(
            "Chat-completions request field used for --max-tokens. Keep the "
            "portable default max_tokens for local OpenAI-compatible servers; "
            "use max_completion_tokens for endpoints/models that require the "
            "newer OpenAI-style field."
        ),
    )
    parser.add_argument(
        "--response-format",
        choices=("default", "json_object", "json_schema"),
        default="default",
        help=(
            "OpenAI-compatible response_format mode for the task model call. "
            "Use json_object or json_schema only with endpoints that support "
            "those structured-output modes."
        ),
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repetition", required=True)
    parser.add_argument("--context", required=True)
    args = parser.parse_args(argv)

    started = time.monotonic()
    model_call_log_path: Path | None = None
    response: dict[str, Any] | None = None
    try:
        workspace, _, model_call_log_path, prompt = _load_and_validate_context(args)
        api_key = os.environ.get(args.api_key_env, "")
        if not api_key:
            raise ValueError(f"API key environment variable is not set: {args.api_key_env}")
        allowed_paths = _allowed_paths(prompt)
        response, duration_s = _call_chat_completion(
            endpoint=args.endpoint,
            api_key=api_key,
            model=args.model,
            prompt=prompt,
            allowed_paths=allowed_paths,
            timeout_s=args.timeout_s,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            token_budget_field=args.token_budget_field,
            response_format=args.response_format,
        )
        payload = _parse_edit_payload(
            _assistant_content(response),
            finish_reason=_finish_reason(response),
        )
        changed, summary = _apply_edits(workspace, payload, allowed_paths)
        _write_telemetry(
            model_call_log_path,
            model=args.model,
            endpoint=args.endpoint,
            duration_s=duration_s,
            ok=True,
            response=response,
        )
    except (OSError, ValueError) as exc:
        try:
            if model_call_log_path is not None:
                _write_telemetry(
                    model_call_log_path,
                    model=args.model,
                    endpoint=args.endpoint,
                    duration_s=time.monotonic() - started,
                    ok=False,
                    response=response,
                    error=str(exc),
                )
        except OSError:
            pass
        return _fail(str(exc))

    print(
        f"openai-direct-edit-agent wrote {changed} file(s) for {args.case}"
        + (f": {summary}" if summary else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
