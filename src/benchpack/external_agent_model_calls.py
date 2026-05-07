"""Safe summaries for external-agent model-call JSONL artifacts."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MODEL_CALL_LOG_PATTERN = "task/*/rep-*.model-calls.jsonl"
_MODEL_CALL_LOG_RE = re.compile(r"^rep-(?P<repetition>[0-9]{3,})\.model-calls\.jsonl$")
_ALLOWED_KEYS = {
    "schema_version",
    "sequence",
    "model",
    "ok",
    "started_at",
    "ended_at",
    "duration_s",
    "adapter",
    "endpoint",
    "prompt_tokens",
    "output_tokens",
    "cached_prompt_tokens",
    "error",
}
_STRING_KEYS = ("model", "adapter", "endpoint")
_TOKEN_KEYS = ("prompt_tokens", "output_tokens", "cached_prompt_tokens")


class ModelCallLogError(ValueError):
    """Raised when model-call artifacts cannot be read safely."""


@dataclass(frozen=True)
class ModelCallSummary:
    """Aggregate safe telemetry for one external-agent model-call JSONL file."""

    case: str
    repetition: int
    path: Path
    relative_path: str
    calls: int
    valid: int
    invalid: int
    ok: int
    failed: int
    error_count: int
    models: tuple[str, ...]
    adapters: tuple[str, ...]
    endpoints: tuple[str, ...]
    duration_s: float | None
    prompt_tokens: int | None
    output_tokens: int | None
    cached_prompt_tokens: int | None


def summarize_model_call_logs(result_dir: Path | str) -> list[ModelCallSummary]:
    """Load and summarize external-agent model-call logs under ``result_dir``.

    The parser accepts only the documented safe telemetry fields. It never
    returns prompt text, response text, request bodies, headers, credentials, or
    arbitrary unknown keys from the harness-owned artifact.
    """

    root = Path(result_dir)
    summaries: list[ModelCallSummary] = []
    for path in sorted(root.glob(MODEL_CALL_LOG_PATTERN)):
        match = _MODEL_CALL_LOG_RE.match(path.name)
        if match is None:
            continue
        case = path.parent.name
        if case == "":
            continue
        try:
            relative_path = path.relative_to(root).as_posix()
        except ValueError:
            relative_path = path.as_posix()
        summaries.append(
            _summarize_one_log(
                path=path,
                case=case,
                repetition=int(match.group("repetition")),
                relative_path=relative_path,
            )
        )
    return summaries


def _summarize_one_log(
    *,
    path: Path,
    case: str,
    repetition: int,
    relative_path: str,
) -> ModelCallSummary:
    calls = 0
    valid = 0
    invalid = 0
    ok = 0
    failed = 0
    error_count = 0
    models: list[str] = []
    adapters: list[str] = []
    endpoints: list[str] = []
    duration_values: list[float] = []
    token_totals: dict[str, int] = {key: 0 for key in _TOKEN_KEYS}
    token_seen: dict[str, bool] = {key: False for key in _TOKEN_KEYS}

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ModelCallLogError(
            f"could not decode model-call log {relative_path}"
        ) from exc
    except OSError as exc:
        raise ModelCallLogError(
            f"could not read model-call log {relative_path}"
        ) from exc

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        calls += 1
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if not _is_valid_call(value):
            invalid += 1
            continue

        valid += 1
        if value["ok"]:
            ok += 1
        else:
            failed += 1
        if isinstance(value.get("error"), str) and value["error"] != "":
            error_count += 1
        _append_unique(models, value["model"])
        for field, destination in (("adapter", adapters), ("endpoint", endpoints)):
            if isinstance(value.get(field), str) and value[field] != "":
                _append_unique(destination, value[field])
        duration = value.get("duration_s")
        if _is_nonnegative_number(duration):
            duration_values.append(float(duration))
        for key in _TOKEN_KEYS:
            token_value = value.get(key)
            if _is_nonnegative_int(token_value):
                token_totals[key] += int(token_value)
                token_seen[key] = True

    return ModelCallSummary(
        case=case,
        repetition=repetition,
        path=path,
        relative_path=relative_path,
        calls=calls,
        valid=valid,
        invalid=invalid,
        ok=ok,
        failed=failed,
        error_count=error_count,
        models=tuple(models),
        adapters=tuple(adapters),
        endpoints=tuple(endpoints),
        duration_s=round(sum(duration_values), 6) if duration_values else None,
        prompt_tokens=token_totals["prompt_tokens"]
        if token_seen["prompt_tokens"]
        else None,
        output_tokens=token_totals["output_tokens"]
        if token_seen["output_tokens"]
        else None,
        cached_prompt_tokens=token_totals["cached_prompt_tokens"]
        if token_seen["cached_prompt_tokens"]
        else None,
    )


def _is_valid_call(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if any(not isinstance(key, str) or key not in _ALLOWED_KEYS for key in value):
        return False
    if value.get("schema_version") != 1:
        return False
    if not _is_positive_int(value.get("sequence")):
        return False
    if not _is_safe_string(value.get("model"), required=True):
        return False
    if not isinstance(value.get("ok"), bool):
        return False
    for key in _STRING_KEYS:
        if key in value and not _is_safe_string(
            value.get(key),
            required=(key == "model"),
        ):
            return False
    endpoint = value.get("endpoint")
    if isinstance(endpoint, str) and any(
        marker in endpoint for marker in ("://", "?", "@")
    ):
        return False
    for key in ("started_at", "ended_at"):
        if key in value and not _is_safe_string(value.get(key), required=False):
            return False
    if "duration_s" in value and not _is_nonnegative_number(value.get("duration_s")):
        return False
    for key in _TOKEN_KEYS:
        if key in value and not _is_nonnegative_int(value.get(key)):
            return False
    if "error" in value and not _is_safe_string(value.get("error"), required=False):
        return False
    return True


def _is_safe_string(value: Any, *, required: bool) -> bool:
    if value is None and not required:
        return True
    if not isinstance(value, str):
        return False
    if required and value == "":
        return False
    if len(value) > 200:
        return False
    for ch in value:
        if ch == " ":
            continue
        if unicodedata.category(ch)[0] in {"C", "Z"}:
            return False
    return True


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_nonnegative_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value)) and float(value) >= 0


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
