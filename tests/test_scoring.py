"""Tests for benchpack.scoring."""

from __future__ import annotations

import pytest

from benchpack.packs import Scoring
from benchpack.scoring import evaluate


def test_evaluate_none_when_no_scoring() -> None:
    assert evaluate(None, "anything") is None


def test_evaluate_none_when_mode_is_none() -> None:
    assert evaluate(Scoring(mode="none"), "anything") is None


def test_contains_passes_when_substring_present() -> None:
    result = evaluate(Scoring(mode="contains", expected="Paris"), "Paris is the capital.")
    assert result == {"mode": "contains", "passed": True}


def test_contains_fails_when_substring_missing() -> None:
    result = evaluate(Scoring(mode="contains", expected="Paris"), "London.")
    assert result == {"mode": "contains", "passed": False}


def test_contains_requires_expected() -> None:
    with pytest.raises(ValueError):
        evaluate(Scoring(mode="contains"), "anything")


def test_regex_passes_when_pattern_matches() -> None:
    output = "DDS_WRAP_PLAN\nInspect: review settings\nVerification: run smoke"
    result = evaluate(
        Scoring(
            mode="regex",
            pattern=r"^DDS_WRAP_PLAN\nInspect: .+\nVerification: .+",
        ),
        output,
    )
    assert result == {"mode": "regex", "passed": True}


def test_regex_fails_when_pattern_does_not_match() -> None:
    result = evaluate(
        Scoring(mode="regex", pattern=r"^DDS_WRAP_PLAN\nInspect: .+"),
        "Intro\nDDS_WRAP_PLAN\nInspect: review settings",
    )
    assert result == {"mode": "regex", "passed": False}


def test_regex_requires_pattern() -> None:
    with pytest.raises(ValueError):
        evaluate(Scoring(mode="regex"), "anything")


def test_json_schema_passes_for_matching_object() -> None:
    result = evaluate(
        Scoring(
            mode="json-schema",
            schema="inline",
            schema_data={
                "type": "object",
                "required": ["tool", "arguments"],
                "additionalProperties": False,
                "properties": {
                    "tool": {"const": "create_ticket"},
                    "arguments": {
                        "type": "object",
                        "required": ["severity", "due_days"],
                        "additionalProperties": False,
                        "properties": {
                            "severity": {"enum": ["medium"]},
                            "due_days": {"type": "integer", "minimum": 1},
                        },
                    },
                },
            },
        ),
        '{"tool":"create_ticket","arguments":{"severity":"medium","due_days":3}}',
    )

    assert result == {"mode": "json-schema", "passed": True}


def test_json_schema_fails_for_invalid_json() -> None:
    result = evaluate(
        Scoring(mode="json-schema", schema="inline", schema_data={"type": "object"}),
        "```json\n{}\n```",
    )

    assert result is not None
    assert result["mode"] == "json-schema"
    assert result["passed"] is False
    assert "invalid JSON" in result["error"]


def test_json_schema_fails_for_shape_mismatch() -> None:
    result = evaluate(
        Scoring(
            mode="json-schema",
            schema="inline",
            schema_data={
                "type": "object",
                "required": ["name"],
                "additionalProperties": False,
                "properties": {"name": {"const": "Ada"}},
            },
        ),
        '{"name":"Grace","extra":true}',
    )

    assert result is not None
    assert result["mode"] == "json-schema"
    assert result["passed"] is False
    assert result["error"] in {
        "$.name must equal 'Ada'",
        "$ has unsupported properties ['extra']",
    }


def test_json_schema_const_distinguishes_boolean_from_integer() -> None:
    result = evaluate(
        Scoring(
            mode="json-schema",
            schema="inline",
            schema_data={"const": 1},
        ),
        "true",
    )

    assert result == {
        "mode": "json-schema",
        "passed": False,
        "error": "$ must equal 1",
    }


def test_json_schema_enum_distinguishes_boolean_from_integer() -> None:
    result = evaluate(
        Scoring(
            mode="json-schema",
            schema="inline",
            schema_data={"enum": [0, 1]},
        ),
        "false",
    )

    assert result == {
        "mode": "json-schema",
        "passed": False,
        "error": "$ must be one of [0, 1]",
    }


def test_json_schema_const_uses_json_equality_inside_arrays() -> None:
    result = evaluate(
        Scoring(
            mode="json-schema",
            schema="inline",
            schema_data={"const": [1]},
        ),
        "[true]",
    )

    assert result == {
        "mode": "json-schema",
        "passed": False,
        "error": "$ must equal [1]",
    }


def test_json_schema_requires_schema() -> None:
    with pytest.raises(ValueError):
        evaluate(Scoring(mode="json-schema"), "{}")


def test_unsupported_modes_raise_not_implemented() -> None:
    for mode in ("equals", "verify-script", "llm-judge"):
        with pytest.raises(NotImplementedError):
            evaluate(Scoring(mode=mode), "x")
