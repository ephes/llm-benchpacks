"""Tests for the local result registry importer."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from benchpack.registry import RegistryError, import_result_dirs


def _record(case: str = "short") -> dict:
    return {
        "pack": {"id": "runtime-sweep", "version": "0.1.0"},
        "case": case,
        "adapter": "openai-chat",
        "endpoint": "http://example.test/v1/chat/completions",
        "model": "test-model",
        "ok": True,
        "timing": {
            "wall_s": 1.25,
            "ttft_s": 0.2,
            "prefill_tps": 100.0,
            "decode_tps": 40.0,
            "total_tps": 30.0,
        },
        "tokens": {"prompt": 10, "output": 60, "cached_prompt": 0},
        "resources": {"memory_mb": None, "gpu_memory_mb": None},
        "scoring": None,
        "raw": {
            "request_path": "raw/short.request.json",
            "response_path": "raw/short.response.json",
        },
    }


def _write_result_dir(path: Path, records: list[dict] | None = None) -> None:
    path.mkdir(parents=True)
    rows = records or [_record()]
    (path / "run.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in rows),
        encoding="utf-8",
    )


def test_registry_import_indexes_result_rows_and_metadata(tmp_path: Path) -> None:
    result_dir = tmp_path / "results" / "run-a"
    record = _record()
    record["repetition"] = 2
    record["scoring"] = {"mode": "contains", "passed": True}
    record["repo_task"] = {"status": "passed", "verify_exit_code": 0}
    _write_result_dir(result_dir, [record])
    (result_dir / "hardware.json").write_text(
        json.dumps({"hostname": "atlas", "platform": "Darwin"}) + "\n",
        encoding="utf-8",
    )
    (result_dir / "run-metadata.json").write_text(
        json.dumps(
            {
                "runtime": {"name": "llama-server", "version": "9030"},
                "model": {"id": "gemma4-e2b-q4km", "quantization": "Q4_K_M"},
                "notes": "unit",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "registry.sqlite"
    before_names = {path.name for path in result_dir.iterdir()}

    summaries = import_result_dirs([result_dir], db_path)

    assert summaries[0].rows_imported == 1
    assert {path.name for path in result_dir.iterdir()} == before_names

    with sqlite3.connect(db_path) as conn:
        run = conn.execute(
            """
            SELECT label, row_count, host_hostname, host_platform, runtime_name,
                   runtime_version, model_metadata_id, model_quantization
            FROM runs
            """
        ).fetchone()
        assert run == (
            "run-a",
            1,
            "atlas",
            "Darwin",
            "llama-server",
            "9030",
            "gemma4-e2b-q4km",
            "Q4_K_M",
        )
        row = conn.execute(
            """
            SELECT pack_id, pack_version, case_id, repetition, adapter, model,
                   endpoint, ok, wall_s, prompt_tokens, cached_prompt_tokens,
                   scoring_mode, scoring_passed, repo_task_status,
                   verify_exit_code
            FROM result_rows
            """
        ).fetchone()
        assert row == (
            "runtime-sweep",
            "0.1.0",
            "short",
            2,
            "openai-chat",
            "test-model",
            "http://example.test/v1/chat/completions",
            1,
            1.25,
            10,
            0,
            "contains",
            1,
            "passed",
            0,
        )


def test_registry_import_replaces_rows_for_same_result_dir(tmp_path: Path) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir, [_record("short"), _record("long")])
    db_path = tmp_path / "registry.sqlite"

    first = import_result_dirs([result_dir], db_path)[0]
    (result_dir / "run.jsonl").write_text(
        json.dumps(_record("short")) + "\n",
        encoding="utf-8",
    )
    second = import_result_dirs([result_dir], db_path)[0]

    assert second.run_id == first.run_id
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM result_rows").fetchone()[0] == 1
        assert conn.execute("SELECT row_count FROM runs").fetchone()[0] == 1


def test_registry_import_treats_optional_metadata_as_absent(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"

    import_result_dirs([result_dir], db_path)

    with sqlite3.connect(db_path) as conn:
        run = conn.execute(
            """
            SELECT hardware_json, run_metadata_json, host_hostname,
                   host_platform, runtime_name, runtime_version,
                   model_metadata_id, model_quantization
            FROM runs
            """
        ).fetchone()

    assert run == (None, None, None, None, None, None, None, None)


def test_registry_import_rejects_malformed_result_row(tmp_path: Path) -> None:
    result_dir = tmp_path / "run-a"
    bad_record = _record()
    bad_record["ok"] = "yes"
    _write_result_dir(result_dir, [bad_record])

    with pytest.raises(RegistryError, match="field 'ok' must be boolean"):
        import_result_dirs([result_dir], tmp_path / "registry.sqlite")

    assert not (tmp_path / "registry.sqlite").exists()


def test_registry_import_validates_all_inputs_before_writing_db(
    tmp_path: Path,
) -> None:
    good_dir = tmp_path / "run-good"
    bad_dir = tmp_path / "run-bad"
    _write_result_dir(good_dir)
    bad_record = _record()
    bad_record["timing"]["wall_s"] = "slow"
    _write_result_dir(bad_dir, [bad_record])
    db_path = tmp_path / "registry.sqlite"

    with pytest.raises(RegistryError, match="field 'wall_s'"):
        import_result_dirs([good_dir, bad_dir], db_path)

    assert not db_path.exists()


def test_registry_import_rejects_malformed_optional_metadata(tmp_path: Path) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    (result_dir / "hardware.json").write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(RegistryError, match="could not parse"):
        import_result_dirs([result_dir], tmp_path / "registry.sqlite")
