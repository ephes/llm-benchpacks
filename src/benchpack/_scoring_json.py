"""Numeric decoding shared by scoring schemas and model output."""

import math
from decimal import Decimal, InvalidOperation


def reject_json_constant(value: str) -> Decimal:
    raise ValueError("non-finite JSON number")


def parse_json_decimal(value: str) -> Decimal:
    # Preserve the existing overflow limit without comparing rounded floats.
    if not math.isfinite(float(value)):
        raise ValueError("JSON number exceeds finite float range")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("JSON number exceeds decimal representation limits") from exc
    if not number.is_finite():
        raise ValueError("JSON number exceeds decimal representation limits")
    return number
