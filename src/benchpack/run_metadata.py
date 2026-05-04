"""User-supplied runtime/run metadata artifact helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RUN_METADATA_FILENAME = "run-metadata.json"
KNOWN_OBJECT_SECTIONS = ("runtime", "model", "operating_conditions")


class RunMetadataError(ValueError):
    """Raised when user-supplied run metadata cannot be loaded."""


def load_run_metadata(path: Path | str) -> dict[str, Any]:
    """Load and validate a user-supplied run metadata JSON object."""

    metadata_path = Path(path)
    try:
        text = metadata_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RunMetadataError(
            f"could not read run metadata file {metadata_path}: {exc.strerror}"
        ) from exc

    try:
        metadata = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RunMetadataError(
            f"could not parse run metadata file {metadata_path}: {exc.msg}"
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

    return dict(metadata)


def write_run_metadata(output_dir: Path | str, metadata: dict[str, Any]) -> Path:
    """Write normalized run metadata beside the result artifacts."""

    output_path = Path(output_dir) / RUN_METADATA_FILENAME
    output_path.write_text(
        json.dumps(validate_run_metadata(metadata), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path
