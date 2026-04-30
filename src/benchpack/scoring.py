"""Deterministic scoring for benchpack cases."""

from __future__ import annotations

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

    raise NotImplementedError(
        f"scoring mode {scoring.mode!r} is not implemented"
    )
