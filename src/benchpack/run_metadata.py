"""User-supplied runtime/run metadata artifact helpers."""

from __future__ import annotations

import json
import re
import stat
import uuid
from pathlib import Path
from typing import Any

from .compare import unique_json_object


RUN_METADATA_FILENAME = "run-metadata.json"
KNOWN_OBJECT_SECTIONS = ("host", "runtime", "model", "operating_conditions")


class RunMetadataError(ValueError):
    """Raised for invalid run metadata or an unsupported output destination."""


def load_run_metadata(path: Path | str) -> dict[str, Any]:
    """Load and validate a user-supplied run metadata JSON object."""

    metadata = _load_run_metadata(Path(path), optional=False)
    assert metadata is not None
    return metadata


def _load_run_metadata(metadata_path: Path, *, optional: bool) -> dict[str, Any] | None:
    try:
        text = metadata_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RunMetadataError(
            f"run metadata file {metadata_path} is not valid UTF-8"
        ) from exc
    except OSError as exc:
        if optional and isinstance(exc, FileNotFoundError):
            return None
        raise RunMetadataError(
            f"could not read run metadata file {metadata_path}: {exc.strerror}"
        ) from exc

    return parse_run_metadata(text, source=metadata_path)


def parse_run_metadata(text: str, *, source: Path | str) -> dict[str, Any]:
    """Decode and validate run metadata from admitted text."""
    try:
        metadata = json.loads(text, object_pairs_hook=unique_json_object)
    except RecursionError as exc:
        raise RunMetadataError(
            f"run metadata file {source} exceeds JSON nesting limit"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RunMetadataError(
            f"could not parse run metadata file {source}: {exc.msg}"
        ) from exc
    except ValueError as exc:
        raise RunMetadataError(
            f"could not parse run metadata file {source}: invalid JSON domain"
        ) from exc

    return validate_run_metadata(metadata, source=source)


def load_optional_run_metadata(result_dir: Path | str) -> dict[str, Any] | None:
    """Load optional ``run-metadata.json`` from a result directory."""

    return _load_run_metadata(Path(result_dir) / RUN_METADATA_FILENAME, optional=True)


def validate_run_metadata(
    metadata: Any,
    *,
    source: Path | str = RUN_METADATA_FILENAME,
) -> dict[str, Any]:
    """Validate the permissive run metadata object shape."""

    if not isinstance(metadata, dict):
        raise RunMetadataError(f"expected JSON object in run metadata file {source}")

    for section in KNOWN_OBJECT_SECTIONS:
        value = metadata.get(section)
        if value is not None and not isinstance(value, dict):
            raise RunMetadataError(
                f"run metadata field {section!r} must be a JSON object in {source}"
            )

    notes = metadata.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise RunMetadataError(
            f"run metadata field 'notes' must be a string in {source}"
        )

    for section, fields in (
        ("host", ("identity", "display")),
        ("model", ("canonical_id", "display_name")),
    ):
        values = metadata.get(section)
        if not isinstance(values, dict):
            continue
        for field in fields:
            value = values.get(field)
            if value is not None and (
                not isinstance(value, str) or value.strip() == ""
            ):
                raise RunMetadataError(
                    f"run metadata field {section}.{field} must be a non-empty "
                    f"string in {source}"
                )
            if (
                field in {"identity", "canonical_id"}
                and isinstance(value, str)
                and re.search(r"[A-Za-z0-9]", value) is None
            ):
                raise RunMetadataError(
                    f"run metadata field {section}.{field} must contain a letter "
                    f"or number in {source}"
                )

    try:
        # Strict serialization validates the entire extension tree, including
        # overflowed exponent literals; decoding returns normalized JSON values.
        text = json.dumps(metadata, allow_nan=False)
        return json.loads(text, object_pairs_hook=unique_json_object)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise RunMetadataError(f"invalid JSON domain in run metadata file {source}") from exc


def write_run_metadata(output_dir: Path | str, metadata: dict[str, Any]) -> Path:
    """Atomically publish normalized run metadata beside the result artifacts."""

    output_path = Path(output_dir) / RUN_METADATA_FILENAME
    text = json.dumps(validate_run_metadata(metadata), indent=2, sort_keys=True, allow_nan=False) + "\n"
    try:
        destination_mode = output_path.lstat().st_mode
    except FileNotFoundError:
        destination_mode = None
    if destination_mode is not None and not stat.S_ISREG(destination_mode):
        raise RunMetadataError(f"run metadata destination must be a regular file: {output_path}")

    temporary_path = output_path.with_name(f".{RUN_METADATA_FILENAME}.{uuid.uuid4().hex}.tmp")
    owned = False
    primary_error: BaseException | None = None
    try:
        with temporary_path.open("x", encoding="utf-8") as temporary:
            owned = True
            if destination_mode is not None:
                temporary_path.chmod(stat.S_IMODE(destination_mode))
            temporary.write(text)
        temporary_path.replace(output_path)
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        if owned:
            try:
                temporary_path.unlink(missing_ok=True)
            except BaseException:
                if primary_error is None:
                    raise
                primary_error.add_note("run metadata staging cleanup failed")
    return output_path
