"""Deterministic scoring for benchpack cases."""

from __future__ import annotations

import json
import re
from typing import Any

from .packs import Scoring


def evaluate(scoring: Scoring | None, output: str) -> dict[str, Any] | None:
    """Run the configured scoring mode and return the scoring envelope.

    Returns ``None`` when no scoring is configured or mode is ``none`` so the
    reporter writes ``scoring: null`` per ``docs/architecture.md``.
    """
    if scoring is None or scoring.mode == "none":
        return None

    if scoring.mode == "contains":
        if scoring.expected is None:
            raise ValueError("scoring mode 'contains' requires 'expected'")
        return {"mode": "contains", "passed": scoring.expected in output}

    if scoring.mode == "regex":
        if scoring.pattern is None:
            raise ValueError("scoring mode 'regex' requires 'pattern'")
        return {
            "mode": "regex",
            "passed": re.search(scoring.pattern, output) is not None,
        }

    if scoring.mode == "json-schema":
        if scoring.schema_data is None:
            raise ValueError("scoring mode 'json-schema' requires 'schema'")
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError as exc:
            return {
                "mode": "json-schema",
                "passed": False,
                "error": f"invalid JSON: {exc.msg}",
            }
        error = _validate_json_schema(parsed, scoring.schema_data)
        return {
            "mode": "json-schema",
            "passed": error is None,
            **({} if error is None else {"error": error}),
        }

    raise NotImplementedError(
        f"scoring mode {scoring.mode!r} is not implemented"
    )


def _validate_json_schema(
    value: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> str | None:
    """Validate a compact JSON Schema subset used by bundled packs.

    This intentionally supports the deterministic keywords this repo needs
    without pulling in a broad dependency: type, required, properties,
    additionalProperties, items, enum, const, string lengths, and numeric bounds.
    Unknown keywords are ignored, matching JSON Schema's extension-friendly
    behavior closely enough for pack-local shape checks.
    """
    if "const" in schema and not _json_values_equal(value, schema["const"]):
        return f"{path} must equal {schema['const']!r}"

    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list):
            return f"{path} schema enum must be an array"
        if not any(_json_values_equal(value, enum_value) for enum_value in enum):
            return f"{path} must be one of {enum!r}"

    expected_type = schema.get("type")
    if expected_type is not None:
        type_error = _validate_json_type(value, expected_type, path)
        if type_error is not None:
            return type_error

    if isinstance(value, dict):
        required = schema.get("required", [])
        if not isinstance(required, list) or any(
            not isinstance(item, str) for item in required
        ):
            return f"{path} schema required must be an array of strings"
        for key in required:
            if key not in value:
                return f"{path}.{key} is required"

        properties = schema.get("properties", {})
        if properties is not None and not isinstance(properties, dict):
            return f"{path} schema properties must be an object"
        properties = properties or {}
        for key, property_schema in properties.items():
            if not isinstance(property_schema, dict):
                return f"{path} schema property {key!r} must be an object"
            if key in value:
                error = _validate_json_schema(
                    value[key],
                    property_schema,
                    f"{path}.{key}",
                )
                if error is not None:
                    return error

        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                return f"{path} has unsupported properties {extra!r}"

    if isinstance(value, list) and "items" in schema:
        item_schema = schema["items"]
        if not isinstance(item_schema, dict):
            return f"{path} schema items must be an object"
        for index, item in enumerate(value):
            error = _validate_json_schema(item, item_schema, f"{path}[{index}]")
            if error is not None:
                return error

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            return f"{path} must have length >= {min_length}"
        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and len(value) > max_length:
            return f"{path} must have length <= {max_length}"

    if _is_json_number(value):
        minimum = schema.get("minimum")
        if _is_json_number(minimum) and value < minimum:
            return f"{path} must be >= {minimum}"
        maximum = schema.get("maximum")
        if _is_json_number(maximum) and value > maximum:
            return f"{path} must be <= {maximum}"

    return None


def _validate_json_type(value: Any, expected_type: Any, path: str) -> str | None:
    allowed_types = expected_type if isinstance(expected_type, list) else [expected_type]
    if any(_matches_json_type(value, item) for item in allowed_types):
        return None
    return f"{path} must be {expected_type!r}"


def _matches_json_type(value: Any, expected_type: Any) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return _is_json_number(value)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return False


def _is_json_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _json_values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if _is_json_number(left) and _is_json_number(right):
        return left == right
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(
                _json_values_equal(left_item, right_item)
                for left_item, right_item in zip(left, right, strict=True)
            )
        )
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and set(left) == set(right)
            and all(_json_values_equal(left[key], right[key]) for key in left)
        )
    return left == right
