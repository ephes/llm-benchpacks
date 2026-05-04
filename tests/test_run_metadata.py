"""Tests for user-supplied run metadata artifact helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchpack.run_metadata import (
    RUN_METADATA_FILENAME,
    RunMetadataError,
    load_optional_run_metadata,
    load_run_metadata,
    write_run_metadata,
)


def test_load_run_metadata_accepts_documented_shape(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    path.write_text(
        json.dumps(
            {
                "runtime": {
                    "name": "llama-server",
                    "version": "9010",
                    "options": {"ctx_size": 4096},
                },
                "model": {
                    "id": "qwen2.5-0.5b-instruct-q4_k_m",
                    "quantization": "Q4_K_M",
                },
                "operating_conditions": {
                    "power": "not captured",
                    "thermal": "not captured",
                },
                "notes": "local run note",
            }
        ),
        encoding="utf-8",
    )

    metadata = load_run_metadata(path)

    assert metadata["runtime"]["name"] == "llama-server"
    assert metadata["model"]["quantization"] == "Q4_K_M"
    assert metadata["operating_conditions"]["thermal"] == "not captured"


def test_load_run_metadata_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    path.write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(RunMetadataError, match="could not parse"):
        load_run_metadata(path)


def test_load_run_metadata_rejects_non_object_root(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(RunMetadataError, match="expected JSON object"):
        load_run_metadata(path)


def test_load_run_metadata_rejects_non_object_known_section(
    tmp_path: Path,
) -> None:
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"runtime": "llama-server"}), encoding="utf-8")

    with pytest.raises(RunMetadataError, match="runtime"):
        load_run_metadata(path)


def test_load_run_metadata_rejects_non_string_notes(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"notes": ["too", "much"]}), encoding="utf-8")

    with pytest.raises(RunMetadataError, match="notes"):
        load_run_metadata(path)


def test_load_run_metadata_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RunMetadataError, match="could not read"):
        load_run_metadata(tmp_path / "missing.json")


def test_write_run_metadata_writes_normalized_artifact(tmp_path: Path) -> None:
    write_run_metadata(
        tmp_path,
        {
            "runtime": {"name": "mlx-lm"},
            "model": {"id": "mlx-community/Qwen2.5-0.5B-Instruct-4bit"},
        },
    )

    path = tmp_path / RUN_METADATA_FILENAME
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "runtime": {"name": "mlx-lm"},
        "model": {"id": "mlx-community/Qwen2.5-0.5B-Instruct-4bit"},
    }


def test_load_optional_run_metadata_tolerates_missing_artifact(
    tmp_path: Path,
) -> None:
    assert load_optional_run_metadata(tmp_path) is None
