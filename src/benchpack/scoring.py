"""Deterministic scoring for benchpack cases.

Phase 1 implements only the ``none`` and ``contains`` modes.  The other modes
documented in ``docs/benchpack-format.md`` parse correctly via
:mod:`benchpack.packs` but raise :class:`NotImplementedError` here until later
slices add them.
"""

from __future__ import annotations

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

    raise NotImplementedError(
        f"scoring mode {scoring.mode!r} is not implemented in Phase 1"
    )
