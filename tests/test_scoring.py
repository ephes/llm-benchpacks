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


def test_unsupported_modes_raise_not_implemented() -> None:
    for mode in ("equals", "regex", "json-schema", "verify-script", "llm-judge"):
        with pytest.raises(NotImplementedError):
            evaluate(Scoring(mode=mode), "x")
