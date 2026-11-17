"""Unique decoded object members at the core provider response boundary."""

from typing import Any


class DuplicateJSONMemberError(ValueError):
    """An upstream object has more than one interpretation."""


def unique_response_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            # Never copy provider-controlled names into result diagnostics.
            raise DuplicateJSONMemberError("duplicate JSON member")
        result[key] = value
    return result
