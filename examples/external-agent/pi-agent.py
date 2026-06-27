#!/usr/bin/env python3
"""Run Pi as a benchpack public external-agent harness."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


_ALLOWED_PATH_HEADING_RE = re.compile(r"^Allowed repo-root paths? to edit:\s*$")
_ALLOWED_PATH_RE = re.compile(r"^- `([^`]+)`\s*$")


def _fail(message: str) -> int:
    print(f"pi-agent: {message}", file=sys.stderr)
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
        raise ValueError(f"unsafe workspace path: {relative_path!r}")
    parts = Path(relative_path).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe workspace path: {relative_path!r}")
    target = (workspace / relative_path).resolve(strict=False)
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(f"workspace path escapes workspace: {relative_path!r}") from exc
    return target


def _read_workspace_file(workspace: Path, relative_path: str) -> str:
    target = _workspace_path(workspace, relative_path)
    if not target.is_file():
        raise ValueError(f"workspace file is missing: {relative_path}")
    return target.read_text(encoding="utf-8")


def _data_context(workspace: Path) -> str:
    chunks: list[str] = []
    for relative_path in ["data/train.csv", "data/test_pairs.csv"]:
        target = workspace / relative_path
        if not target.is_file():
            continue
        text = target.read_text(encoding="utf-8")
        chunks.append(
            f"--- BEGIN READ-ONLY WORKSPACE FILE {relative_path} ---\n"
            f"{text}\n"
            f"--- END READ-ONLY WORKSPACE FILE {relative_path} ---"
        )
    return "\n\n".join(chunks)


def _allowed_file_context(workspace: Path, allowed_paths: tuple[str, ...]) -> str:
    chunks: list[str] = []
    for relative_path in allowed_paths:
        text = _read_workspace_file(workspace, relative_path)
        chunks.append(
            f"--- BEGIN EDITABLE WORKSPACE FILE {relative_path} ---\n"
            f"{text}\n"
            f"--- END EDITABLE WORKSPACE FILE {relative_path} ---"
        )
    return "\n\n".join(chunks)


def _build_prompt(
    *,
    case_id: str,
    prompt: str,
    workspace: Path,
    allowed_paths: tuple[str, ...],
) -> str:
    allowed = "\n".join(f"- {path}" for path in allowed_paths)
    return (
        "You are running as a benchpack external-agent harness inside a "
        "disposable benchmark workspace.\n\n"
        "You have no file-system tools in this run. Return only JSON, with no "
        "Markdown fences and no commentary. The JSON schema is: "
        '{"files":[{"path":"repo-relative path","content":"full UTF-8 file content"}],'
        '"summary":"short summary"}. Only include files that must be changed. '
        "Use full replacement file content, not diffs.\n\n"
        "The wrapper will apply only files whose path is in this allowed list:\n"
        f"{allowed}\n\n"
        "Do not request or mention edits outside the allowed path list. Do not "
        "hardcode hidden labels. Hidden verifier files are not provided.\n\n"
        f"Case id: {case_id}\n\n"
        "Task prompt:\n"
        f"{prompt}\n\n"
        f"{_allowed_file_context(workspace, allowed_paths)}\n\n"
        f"{_data_context(workspace)}\n"
    )


def _write_telemetry(
    path: Path,
    *,
    model: str,
    thinking: str,
    duration_s: float,
    ok: bool,
) -> None:
    payload: dict[str, object] = {
        "schema_version": 1,
        "sequence": 1,
        "model": model,
        "ok": ok,
        "adapter": "pi",
        "endpoint": "pi",
        "response_format": "direct_edit",
        "token_budget_field": "pi-default",
        "finish_reason": f"thinking-{thinking}",
        "duration_s": round(duration_s, 6),
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _parse_edit_payload(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1] == "```":
            text = "\n".join(lines[1:-1]).strip()
    try:
        return _object(json.loads(text), "pi edit payload")
    except json.JSONDecodeError as exc:
        raise ValueError(f"could not parse pi edit payload JSON: {exc}") from exc


def _apply_edits(
    workspace: Path,
    payload: dict[str, Any],
    allowed_paths: tuple[str, ...],
) -> tuple[int, str]:
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError("pi edit payload.files must be an array")
    allowed = set(allowed_paths)
    replacements: list[tuple[Path, str, str]] = []
    seen_paths: set[str] = set()
    for index, item in enumerate(files, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"pi edit payload.files[{index}] must be an object")
        path = _string(item.get("path"), f"pi edit payload.files[{index}].path")
        if path not in allowed:
            raise ValueError(f"pi attempted to edit disallowed path: {path}")
        if path in seen_paths:
            raise ValueError(f"pi edit payload duplicates path: {path}")
        seen_paths.add(path)
        content = item.get("content")
        if not isinstance(content, str):
            raise ValueError(f"pi edit payload.files[{index}].content must be a string")
        target = _workspace_path(workspace, path)
        if not target.is_file():
            raise ValueError(f"pi edit target is not a file: {path}")
        replacements.append((target, path, content))

    originals = {target: target.read_bytes() for target, _, _ in replacements}
    try:
        for target, _, content in replacements:
            target.write_text(content, encoding="utf-8")
    except OSError as exc:
        for target, original in originals.items():
            try:
                target.write_bytes(original)
            except OSError:
                pass
        raise ValueError(f"could not apply pi edit payload: {exc}") from exc

    summary = payload.get("summary")
    return len(replacements), summary if isinstance(summary, str) else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pi-bin", default="pi")
    parser.add_argument("--model", required=True)
    parser.add_argument("--thinking", default="off")
    parser.add_argument("--timeout-s", type=float, default=900.0)
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

    try:
        allowed_paths = _allowed_paths(prompt)
        pi_prompt = _build_prompt(
            case_id=args.case,
            prompt=prompt,
            workspace=workspace,
            allowed_paths=allowed_paths,
        )
    except (OSError, ValueError) as exc:
        return _fail(str(exc))

    prompt_temp = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        prefix="benchpack-pi-agent-",
        suffix=".md",
        delete=False,
    )
    try:
        prompt_temp.write(pi_prompt)
        prompt_temp.close()
        command = [
            args.pi_bin,
            "-p",
            "--no-session",
            "--no-context-files",
            "--model",
            args.model,
            "--thinking",
            args.thinking,
            "--no-tools",
            f"@{prompt_temp.name}",
        ]
    except OSError as exc:
        return _fail(f"could not write pi prompt temp file: {exc}")
    started = time.monotonic()
    completed: subprocess.CompletedProcess[str] | None = None
    try:
        completed = subprocess.run(
            command,
            check=False,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=args.timeout_s,
        )
        if completed.returncode != 0:
            print(completed.stdout, end="")
            print(completed.stderr, end="", file=sys.stderr)
            ok = False
            return_code = completed.returncode
        else:
            payload = _parse_edit_payload(completed.stdout)
            changed, summary = _apply_edits(workspace, payload, allowed_paths)
            print(f"pi-agent applied {changed} file replacement(s): {summary}")
            ok = True
            return_code = 0
    except subprocess.TimeoutExpired as exc:
        print(f"pi timed out after {args.timeout_s}s", file=sys.stderr)
        ok = False
        return_code = 124
    except OSError as exc:
        return _fail(f"could not run pi: {exc}")
    except ValueError as exc:
        if completed is not None:
            print(completed.stdout, end="")
            print(completed.stderr, end="", file=sys.stderr)
        ok = False
        return_code = _fail(str(exc))
    finally:
        try:
            Path(prompt_temp.name).unlink()
        except OSError:
            pass
    duration_s = time.monotonic() - started

    try:
        _write_telemetry(
            model_call_log_path,
            model=args.model,
            thinking=args.thinking,
            duration_s=duration_s,
            ok=ok,
        )
    except OSError as exc:
        return _fail(f"could not write model-call telemetry: {exc}")

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
