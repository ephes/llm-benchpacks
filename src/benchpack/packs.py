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


class DuplicateFixtureIdError(PackError):
    """Raised when two fixtures share an id."""


class InvalidIdError(PackError):
    """Raised when a pack or case id violates :data:`ID_PATTERN`."""


class UnknownScoringModeError(PackError):
    """Raised when a scoring mode is not in the documented set."""


class InvalidDefaultError(PackError):
    """Raised when a manifest default has the wrong type or range."""


class InvalidPromptSourceError(PackError):
    """Raised when a case prompt or prompt_file entry is invalid."""


class InvalidFixtureError(PackError):
    """Raised when a fixture declaration is invalid."""


class InvalidFixtureRefError(PackError):
    """Raised when a case fixture reference is invalid."""


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
    fixture_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Fixture:
    id: str
    kind: str
    path: Path
    description: str
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
    fixtures: list[Fixture] = field(default_factory=list)


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


def _resolve_pack_relative_path(
    raw_path: str,
    *,
    resolved_pack_dir: Path,
    subject: str,
    error_type: type[PackError],
) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise error_type(f"{subject} must be relative to the pack directory")

    try:
        resolved_path = (resolved_pack_dir / candidate).resolve(strict=False)
    except OSError as exc:
        raise error_type(f"{subject} {raw_path!r} could not be resolved") from exc

    if not resolved_path.is_relative_to(resolved_pack_dir):
        raise error_type(f"{subject} {raw_path!r} escapes the pack directory")

    return resolved_path


def _prompt_from_case_entry(
    entry: dict[str, Any],
    *,
    case_id: str,
    resolved_pack_dir: Path,
) -> str | None:
    has_prompt = "prompt" in entry
    has_prompt_file = "prompt_file" in entry

    if has_prompt and has_prompt_file:
        raise InvalidPromptSourceError(
            f"case {case_id!r} cannot define both 'prompt' and 'prompt_file'"
        )
    if not has_prompt and not has_prompt_file:
        raise InvalidPromptSourceError(
            f"case {case_id!r} must define either 'prompt' or 'prompt_file'"
        )
    if has_prompt:
        return entry["prompt"]

    prompt_file = entry["prompt_file"]
    if not isinstance(prompt_file, str):
        raise InvalidPromptSourceError(
            f"case {case_id!r} prompt_file must be a string"
        )

    resolved_prompt_path = _resolve_pack_relative_path(
        prompt_file,
        resolved_pack_dir=resolved_pack_dir,
        subject=f"case {case_id!r} prompt_file",
        error_type=InvalidPromptSourceError,
    )

    try:
        return resolved_prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InvalidPromptSourceError(
            f"case {case_id!r} prompt_file {prompt_file!r} could not be read"
        ) from exc


def _fixtures_from_entries(
    raw_fixtures: Any,
    *,
    resolved_pack_dir: Path,
    pack_id: str,
) -> list[Fixture]:
    if raw_fixtures is None:
        return []
    if not isinstance(raw_fixtures, list):
        raise InvalidFixtureError("[[fixtures]] must be an array of tables")

    fixtures: list[Fixture] = []
    seen: set[str] = set()
    for entry in raw_fixtures:
        if not isinstance(entry, dict):
            raise InvalidFixtureError("fixture entries must be tables")

        fixture_id = _validate_id(entry.get("id"), "fixture")
        if fixture_id in seen:
            raise DuplicateFixtureIdError(
                f"duplicate fixture id {fixture_id!r} in pack {pack_id!r}"
            )
        seen.add(fixture_id)

        kind = entry.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise InvalidFixtureError(
                f"fixture {fixture_id!r} kind must be a non-empty string"
            )

        fixture_path = entry.get("path")
        if not isinstance(fixture_path, str):
            raise InvalidFixtureError(
                f"fixture {fixture_id!r} path must be a string"
            )
        resolved_fixture_path = _resolve_pack_relative_path(
            fixture_path,
            resolved_pack_dir=resolved_pack_dir,
            subject=f"fixture {fixture_id!r} path",
            error_type=InvalidFixtureError,
        )
        if resolved_fixture_path == resolved_pack_dir:
            raise InvalidFixtureError(
                f"fixture {fixture_id!r} path {fixture_path!r} must not resolve "
                "to the pack directory"
            )
        if not resolved_fixture_path.exists():
            raise InvalidFixtureError(
                f"fixture {fixture_id!r} path {fixture_path!r} does not exist"
            )
        if not (resolved_fixture_path.is_file() or resolved_fixture_path.is_dir()):
            raise InvalidFixtureError(
                f"fixture {fixture_id!r} path {fixture_path!r} must be a file "
                "or directory"
            )

        description = entry.get("description", "")
        if not isinstance(description, str):
            raise InvalidFixtureError(
                f"fixture {fixture_id!r} description must be a string"
            )

        fixtures.append(
            Fixture(
                id=fixture_id,
                kind=kind,
                path=resolved_fixture_path,
                description=description,
                raw=dict(entry),
            )
        )

    return fixtures


def _fixture_refs_from_case_entry(
    entry: dict[str, Any],
    *,
    case_id: str,
    fixture_ids: set[str],
) -> list[str]:
    if "fixture_refs" not in entry:
        return []

    raw_refs = entry["fixture_refs"]
    if not isinstance(raw_refs, list):
        raise InvalidFixtureRefError(
            f"case {case_id!r} fixture_refs must be a list of fixture ids"
        )

    fixture_refs: list[str] = []
    seen: set[str] = set()
    for raw_ref in raw_refs:
        if not isinstance(raw_ref, str):
            raise InvalidFixtureRefError(
                f"case {case_id!r} fixture_refs entries must be strings"
            )
        if not ID_PATTERN.match(raw_ref):
            raise InvalidIdError(
                f"case {case_id!r} fixture_refs entry {raw_ref!r} must match "
                f"{ID_PATTERN.pattern}"
            )
        ref = raw_ref
        if ref in seen:
            raise InvalidFixtureRefError(
                f"case {case_id!r} references fixture {ref!r} more than once"
            )
        if ref not in fixture_ids:
            raise InvalidFixtureRefError(
                f"case {case_id!r} references unknown fixture {ref!r}"
            )
        seen.add(ref)
        fixture_refs.append(ref)

    return fixture_refs


def _append_referenced_file_fixtures(
    prompt: str,
    *,
    fixture_refs: list[str],
    fixtures_by_id: dict[str, Fixture],
    case_id: str,
) -> str:
    assembled = prompt
    for fixture_id in fixture_refs:
        fixture = fixtures_by_id[fixture_id]
        if fixture.path.is_dir():
            continue

        fixture_path = fixture.raw["path"]
        try:
            fixture_contents = fixture.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise InvalidFixtureError(
                f"case {case_id!r} fixture {fixture_id!r} file "
                f"{fixture_path!r} could not be read"
            ) from exc

        header = (
            f"--- BEGIN FIXTURE {fixture.id} "
            f"({fixture.kind}, {fixture_path}) ---"
        )
        footer = f"--- END FIXTURE {fixture.id} ---"
        fixture_block = f"{header}\n{fixture_contents}"
        if not fixture_block.endswith("\n"):
            fixture_block += "\n"
        fixture_block += footer
        assembled = f"{assembled}\n\n{fixture_block}"

    return assembled


def load_pack(path: Path | str) -> Pack:
    pack_dir = Path(path)
    manifest_path = pack_dir / "benchpack.toml"
    with manifest_path.open("rb") as fh:
        data = tomllib.load(fh)
    resolved_pack_dir = pack_dir.resolve(strict=True)

    pack_section = data.get("pack") or {}
    pack_id_raw = pack_section.get("id")
    pack_version = pack_section.get("version")
    if not pack_id_raw or not pack_version:
        raise PackError("[pack] section must define 'id' and 'version'")
    pack_id = _validate_id(pack_id_raw, "pack")

    fixtures = _fixtures_from_entries(
        data.get("fixtures"),
        resolved_pack_dir=resolved_pack_dir,
        pack_id=pack_id,
    )
    fixture_ids = {fixture.id for fixture in fixtures}
    fixtures_by_id = {fixture.id: fixture for fixture in fixtures}

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
        prompt = _prompt_from_case_entry(
            entry,
            case_id=case_id,
            resolved_pack_dir=resolved_pack_dir,
        )
        fixture_refs = _fixture_refs_from_case_entry(
            entry,
            case_id=case_id,
            fixture_ids=fixture_ids,
        )
        if fixture_refs:
            prompt = _append_referenced_file_fixtures(
                prompt,
                fixture_refs=fixture_refs,
                fixtures_by_id=fixtures_by_id,
                case_id=case_id,
            )
        cases.append(
            Case(
                id=case_id,
                kind=entry.get("kind", "chat"),
                prompt=prompt,
                scoring=_scoring_from_dict(entry.get("scoring")),
                raw=dict(entry),
                fixture_refs=fixture_refs,
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
        fixtures=fixtures,
    )
