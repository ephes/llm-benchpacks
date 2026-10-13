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
                    "canonical_id": "qwen2.5-0.5b-instruct",
                    "display_name": "Qwen2.5 0.5B Instruct",
                    "quantization": "Q4_K_M",
                },
                "host": {
                    "identity": "apple-m4-max-studio-128gb",
                    "display": "Apple M4 Max Mac Studio (128 GB)",
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
    assert metadata["model"]["canonical_id"] == "qwen2.5-0.5b-instruct"
    assert metadata["host"]["display"] == "Apple M4 Max Mac Studio (128 GB)"
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


@pytest.mark.parametrize(
    "metadata,field",
    [
        ({"host": {"identity": 42}}, "host.identity"),
        ({"host": {"identity": "   "}}, "host.identity"),
        ({"host": {"display": "   "}}, "host.display"),
        ({"model": {"canonical_id": "---"}}, "model.canonical_id"),
        ({"model": {"display_name": "   "}}, "model.display_name"),
    ],
)
def test_load_run_metadata_rejects_invalid_canonical_identity(
    tmp_path: Path,
    metadata: dict,
    field: str,
) -> None:
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(RunMetadataError, match=field):
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


@pytest.mark.parametrize("failure", ["write", "replace"])
def test_write_run_metadata_preserves_previous_artifact_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:

    path = tmp_path / RUN_METADATA_FILENAME
    previous = b'{"notes":"previous provenance"}\n'
    path.write_bytes(previous)
    unrelated = tmp_path / ".run-metadata.json.unrelated.tmp"
    unrelated.write_bytes(b"another writer")
    injected = []
    original_open = Path.open

    class PartialWriter:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.handle.close()

        def write(self, text):
            self.handle.write(text[:5])
            self.handle.flush()
            injected.append("write")
            raise OSError("injected partial write failure")

    def failing_open(self, mode="r", *args, **kwargs):
        handle = original_open(self, mode, *args, **kwargs)
        return PartialWriter(handle) if mode == "x" else handle

    def failing_replace(self, target):
        assert Path(target) == path
        assert self.read_text(encoding="utf-8").endswith("\n")
        injected.append("replace")
        raise OSError("injected replace failure")

    if failure == "write":
        monkeypatch.setattr(Path, "open", failing_open)
    else:
        monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(OSError, match="injected"):
        write_run_metadata(tmp_path, {"notes": "new provenance"})

    assert injected == [failure]
    assert path.read_bytes() == previous
    assert unrelated.read_bytes() == b"another writer"
    assert set(tmp_path.iterdir()) == {path, unrelated}


@pytest.mark.parametrize("metadata", [{"notes": []}, {"extra": object()}])
def test_write_run_metadata_validates_and_serializes_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, metadata: dict,
) -> None:

    path = tmp_path / RUN_METADATA_FILENAME
    path.write_bytes(b"previous")

    original_open = Path.open

    def checked_open(self, mode="r", *args, **kwargs):
        if mode == "x":
            pytest.fail("opened temporary file before validation/serialization")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", checked_open)
    with pytest.raises((RunMetadataError, TypeError)):
        write_run_metadata(tmp_path, metadata)
    assert path.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("existing", [False, True])
def test_write_run_metadata_success_preserves_permissions_and_cleans_staging(
    tmp_path: Path, existing: bool,
) -> None:
    import stat

    path = tmp_path / RUN_METADATA_FILENAME
    unrelated = tmp_path / ".run-metadata.json.other.tmp"
    unrelated.write_bytes(b"other writer")
    expected_mode = stat.S_IMODE(unrelated.stat().st_mode)
    if existing:
        path.write_bytes(b"previous")
        path.chmod(0o640)
        expected_mode = 0o640
    assert write_run_metadata(tmp_path, {"notes": "new"}) == path
    assert load_run_metadata(path) == {"notes": "new"}
    assert path.read_bytes() == b'{\n  "notes": "new"\n}\n'
    assert stat.S_IMODE(path.stat().st_mode) == expected_mode
    assert set(tmp_path.iterdir()) == {path, unrelated}
    assert unrelated.read_bytes() == b"other writer"


@pytest.mark.parametrize("payload,category", [
    (b'{"sentinel": "\xff"}', "UTF-8"),
    (("[" * 100000 + "0" + "]" * 100000).encode(), "nesting"),
], ids=["invalid-utf8", "excessive-nesting"])
def test_load_run_metadata_normalizes_decode_errors(tmp_path, payload, category):
    path = tmp_path / "metadata.json"
    path.write_bytes(payload)
    with pytest.raises(RunMetadataError, match=category) as error:
        load_run_metadata(path)
    assert "sentinel" not in str(error.value)
    assert len(str(error.value)) < len(str(path)) + 100
