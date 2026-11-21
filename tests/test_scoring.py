"""Tests for benchpack.scoring."""

from __future__ import annotations

from decimal import Decimal

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


@pytest.mark.parametrize(
    ("schema", "output", "error"),
    [
        ({"minimum": Decimal("1.5")}, "1", "$ must be >= 1.5"),
        ({"maximum": Decimal("1E+300")}, "1e301", "$ must be <= 1e+300"),
        ({"enum": [Decimal("0.5"), 1]}, "2", "$ must be one of [0.5, 1]"),
        ({"const": Decimal("0.10")}, "0.2", "$ must equal 0.10"),
    ],
)
def test_json_schema_diagnostics_render_decimals_as_json_numbers(
    schema: dict[str, object], output: str, error: str
) -> None:
    result = evaluate(
        Scoring(mode="json-schema", schema="inline", schema_data=schema),
        output,
    )

    assert result == {"mode": "json-schema", "passed": False, "error": error}


def test_json_schema_diagnostics_bound_long_decimal_literals() -> None:
    literal = "0." + "1" * 500
    result = evaluate(
        Scoring(mode="json-schema", schema="inline", schema_data={"const": Decimal(literal)}),
        "1",
    )

    assert result is not None
    error = result["error"]
    assert error.startswith("$ must equal 0.111")
    assert "[truncated]" in error
    assert len(error) < 160


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


@pytest.mark.parametrize(
    "output, passed",
    [
        ("1", True),
        ("1.0", True),
        ("1e0", True),
        ("1.5", False),
        ("true", False),
        ("NaN", False),
        ("Infinity", False),
        ("-Infinity", False),
    ],
)
def test_integral_json_numbers(output, passed):
    schema = {"type": "integer", "const": 1, "enum": [1.0]}
    for text, shape in [
        (output, {"type": "integer"}),
        (output, schema),
        (
            '{"n":[' + output + "]}",
            {"type": "object", "properties": {"n": {"type": "array", "items": schema}}},
        ),
    ]:
        assert (
            evaluate(Scoring(mode="json-schema", schema_data=shape), text)["passed"]
            is passed
        )


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e999"])
@pytest.mark.parametrize("template", ["{}", '{{"n":{}}}', "[{}]"])
def test_nonfinite_json_output_fails(number, template):
    scoring = Scoring(mode="json-schema", schema_data={})
    result = evaluate(scoring, template.format(number))
    assert result["passed"] is False
    assert len(result["error"]) < 200
    assert evaluate(scoring, '{"n":1.5}')["passed"] is True


@pytest.mark.parametrize('output', [
    '{"answer":"wrong","answer":"good"}',
    '{"answer":"good","answer":"wrong"}',
    '{"nested":{"answer":1,"answer":1}}',
    '[{"answer":1,"answer":2}]',
])
def test_duplicate_model_json_members_fail(output):
    result = evaluate(Scoring(mode='json-schema', schema_data={}), output)
    assert result['passed'] is False
    assert 'duplicate' in result['error']
    assert evaluate(Scoring(mode='json-schema', schema_data={}),
                    '{"nested":{"answer":1}}')['passed'] is True


@pytest.mark.parametrize('schema, value', [
    ({'const': 'x' * 1_000_000}, '"wrong"'),
    ({'enum': ['x' * 1_000_000] * 10}, '"wrong"'),
    ({'additionalProperties': False}, '{"' + 'x' * 1_000_000 + '":1}'),
    ({'required': ['x' * 1_000_000]}, '{}'),
    ({'properties': {'x' * 1_000_000: {'const': 1}}},
     '{"' + 'x' * 1_000_000 + '":2}'),
], ids=['const', 'enum', 'extra', 'required', 'path'])
def test_schema_diagnostics_have_fixed_byte_envelope(schema, value):
    result = evaluate(Scoring(mode='json-schema', schema_data=schema), value)
    assert result['passed'] is False
    assert len(result['error'].encode('utf-8')) <= 1024
    assert '[truncated]' in result['error']


def test_mismatch_paths_escape_controls_and_bound_unicode():
    for key in ('line\n\x1b[31m', '😀' * 1000):
        result = evaluate(Scoring(mode='json-schema', schema_data={'required': [key]}), '{}')
        error = result['error']
        assert '\n' not in error and '\x1b' not in error
        assert len(error.encode('utf-8')) <= 1024
    assert '[truncated]' in error
