"""User-supplied runtime/run metadata artifact helpers."""

from __future__ import annotations

import json
import re
import stat
import uuid
from pathlib import Path
from typing import Any


RUN_METADATA_FILENAME = "run-metadata.json"
MAX_METADATA_BYTES = 1024 * 1024
KNOWN_OBJECT_SECTIONS = ("host", "runtime", "model", "operating_conditions")


class RunMetadataError(ValueError):
    """Raised when user-supplied run metadata cannot be loaded."""


def read_metadata_text(
    path: Path, *, max_bytes: int | None = None, kind: str = "metadata"
) -> str:
    """Read UTF-8 metadata within an actual-byte ceiling on the opened file."""

    limit = MAX_METADATA_BYTES if max_bytes is None else max_bytes
    try:
        with path.open("rb") as source:
            data = source.read(limit + 1)
        if len(data) > limit:
            raise RunMetadataError(f"metadata byte limit ({limit}) exceeded: {path}")
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RunMetadataError(f"{kind} file {path} is not valid UTF-8") from exc
    except OSError as exc:
        raise RunMetadataError(f"could not read {kind} file {path}: {exc.strerror}") from exc


def load_run_metadata(path: Path | str) -> dict[str, Any]:
    """Load and validate a user-supplied run metadata JSON object."""

    metadata_path = Path(path)
    text = read_metadata_text(metadata_path, kind="run metadata")

    try:
        metadata = json.loads(text)
    except RecursionError as exc:
        raise RunMetadataError(
            f"run metadata file {metadata_path} exceeds JSON nesting limit"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RunMetadataError(
            f"could not parse run metadata file {metadata_path}: {exc.msg}"
        ) from exc
    except ValueError as exc:
        raise RunMetadataError(
            f"could not parse run metadata file {metadata_path}: invalid JSON number"
        ) from exc

    return validate_run_metadata(metadata, source=metadata_path)


def load_optional_run_metadata(result_dir: Path | str) -> dict[str, Any] | None:
    """Load optional ``run-metadata.json`` from a result directory."""

    metadata_path = Path(result_dir) / RUN_METADATA_FILENAME
    if not metadata_path.exists():
        return None
    return load_run_metadata(metadata_path)


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

    return dict(metadata)


def write_run_metadata(output_dir: Path | str, metadata: dict[str, Any]) -> Path:
    """Atomically publish normalized run metadata beside the result artifacts."""

    output_path = Path(output_dir) / RUN_METADATA_FILENAME
    text = json.dumps(validate_run_metadata(metadata), indent=2, sort_keys=True) + "\n"
    temporary_path = output_path.with_name(f".{RUN_METADATA_FILENAME}.{uuid.uuid4().hex}.tmp")
    owned = False
    try:
        with temporary_path.open("x", encoding="utf-8") as temporary:
            owned = True
            try:
                mode = stat.S_IMODE(output_path.stat().st_mode)
            except FileNotFoundError:
                pass
            else:
                temporary_path.chmod(mode)
            temporary.write(text)
        temporary_path.replace(output_path)
    finally:
        if owned:
            temporary_path.unlink(missing_ok=True)
    return output_path
