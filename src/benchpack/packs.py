"""Benchpack manifest loader.

Parses ``benchpack.toml`` per ``docs/benchpack-format.md`` into typed dataclasses.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Pack and case ids are used as filesystem path components and as stable keys
# in result records.  Constrain them up-front so the reporter can trust them
# and so cross-tool comparisons stay sane.
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


KNOWN_SCORING_MODES = frozenset(
    {
        "none",
        "contains",
        "equals",
        "regex",
        "json-schema",
        "verify-script",
        "llm-judge",
    }
)


class PackError(Exception):
    """Base error for manifest problems."""


class DuplicateCaseIdError(PackError):
    """Raised when two cases share an id."""


class InvalidIdError(PackError):
    """Raised when a pack or case id violates :data:`ID_PATTERN`."""


class UnknownScoringModeError(PackError):
    """Raised when a scoring mode is not in the documented set."""


class InvalidDefaultError(PackError):
    """Raised when a manifest default has the wrong type or range."""


def _validate_id(value: object, role: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.match(value):
        raise InvalidIdError(
            f"invalid {role} id {value!r}; must match {ID_PATTERN.pattern}"
        )
    return value


@dataclass(frozen=True)
class Scoring:
    mode: str
    expected: str | None = None
    pattern: str | None = None
    schema: str | None = None
    script: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Case:
    id: str
    kind: str
    prompt: str | None
    scoring: Scoring | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class Pack:
    id: str
    version: str
    description: str
    defaults: dict[str, Any]
    cases: list[Case]
    scoring: Scoring | None
    path: Path


def _scoring_from_dict(data: dict[str, Any] | None) -> Scoring | None:
    if not data:
        return None
    mode = data.get("mode")
    if mode is None:
        raise PackError("scoring entry missing 'mode'")
    if mode not in KNOWN_SCORING_MODES:
        raise UnknownScoringModeError(
            f"unknown scoring mode {mode!r}; expected one of "
            f"{sorted(KNOWN_SCORING_MODES)}"
        )
    known = {"mode", "expected", "pattern", "schema", "script"}
    extra = {k: v for k, v in data.items() if k not in known}
    return Scoring(
        mode=mode,
        expected=data.get("expected"),
        pattern=data.get("pattern"),
        schema=data.get("schema"),
        script=data.get("script"),
        extra=extra,
    )


def _validated_int_default(
    defaults: dict[str, Any],
    key: str,
    fallback: int,
    minimum: int,
) -> int:
    if key not in defaults:
        return fallback
    value = defaults[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidDefaultError(
            f"defaults.{key} must be an integer >= {minimum}; got {value!r}"
        )
    if value < minimum:
        raise InvalidDefaultError(
            f"defaults.{key} must be an integer >= {minimum}; got {value!r}"
        )
    return value


def repetitions_from_defaults(defaults: dict[str, Any]) -> int:
    """Return the measured repetition count requested by pack defaults."""

    return _validated_int_default(defaults, "repetitions", fallback=1, minimum=1)


def warmup_from_defaults(defaults: dict[str, Any]) -> int:
    """Return the warmup execution count requested by pack defaults."""

    return _validated_int_default(defaults, "warmup", fallback=0, minimum=0)


def _defaults_from_dict(data: Any) -> dict[str, Any]:
    if data is None:
        defaults: dict[str, Any] = {}
    elif isinstance(data, dict):
        defaults = dict(data)
    else:
        raise PackError("[defaults] must be a table")

    repetitions_from_defaults(defaults)
    warmup_from_defaults(defaults)
    return defaults


def load_pack(path: Path | str) -> Pack:
    pack_dir = Path(path)
    manifest_path = pack_dir / "benchpack.toml"
    with manifest_path.open("rb") as fh:
        data = tomllib.load(fh)

    pack_section = data.get("pack") or {}
    pack_id_raw = pack_section.get("id")
    pack_version = pack_section.get("version")
    if not pack_id_raw or not pack_version:
        raise PackError("[pack] section must define 'id' and 'version'")
    pack_id = _validate_id(pack_id_raw, "pack")

    raw_cases = data.get("cases") or []
    cases: list[Case] = []
    seen: set[str] = set()
    for entry in raw_cases:
        case_id = _validate_id(entry.get("id"), "case")
        if case_id in seen:
            raise DuplicateCaseIdError(
                f"duplicate case id {case_id!r} in pack {pack_id!r}"
            )
        seen.add(case_id)
        cases.append(
            Case(
                id=case_id,
                kind=entry.get("kind", "chat"),
                prompt=entry.get("prompt"),
                scoring=_scoring_from_dict(entry.get("scoring")),
                raw=dict(entry),
            )
        )

    defaults = _defaults_from_dict(data.get("defaults"))

    return Pack(
        id=pack_id,
        version=pack_version,
        description=pack_section.get("description", ""),
        defaults=defaults,
        cases=cases,
        scoring=_scoring_from_dict(data.get("scoring")),
        path=pack_dir,
    )
