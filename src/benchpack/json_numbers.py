"""JSON decoder hooks for finite native numeric values."""

import math
from typing import Never


def reject_json_constant(value: str) -> Never:
    raise ValueError("nonfinite JSON number")


def parse_finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("nonfinite JSON number")
    return parsed
