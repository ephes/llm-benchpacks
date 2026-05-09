"""Tests for the local result registry importer."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

import benchpack.registry as registry
from benchpack.cli import main
from benchpack.report import render_report
from benchpack.registry import (
    BUNDLE_MANIFEST_FILENAME,
    RegistryError,
    create_result_bundle,
    import_result_dirs,
    load_registry_report_runs,
    validate_result_bundle,
)


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
                "comparison_mode": "strict-same-gguf-llama-server",
                "host": {"label": "m5-max", "repo_commit": "abc1234"},
                "runtime": {"name": "llama-server", "version": "9030"},
                "model": {
                    "id": "gemma4-e2b-q4km",
                    "artifact_repo": "bartowski/google_gemma-4-E2B-it-GGUF",
                    "artifact_file": "google_gemma-4-E2B-it-Q4_K_M.gguf",
                    "revision": "b5e99bd",
                    "quantization": "Q4_K_M",
                    "sha256": "b5310340b3a23d31655d7119d100d5df1b2d8ee17b3ca8b0a23ad7e9eb5fa705",
                },
                "operating_conditions": {
                    "power": "plugged in",
                    "thermal": "cool",
                    "background_load": "idle",
                },
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
            SELECT label, row_count, host_hostname, host_platform, host_label,
                   host_repo_commit, comparison_mode, runtime_name,
                   runtime_version, model_metadata_id, model_quantization,
                   model_artifact_repo, model_artifact_file, model_revision,
                   model_sha256, operating_power, operating_thermal,
                   operating_background_load
            FROM runs
            """
        ).fetchone()
        assert run == (
            "run-a",
            1,
            "atlas",
            "Darwin",
            "m5-max",
            "abc1234",
            "strict-same-gguf-llama-server",
            "llama-server",
            "9030",
            "gemma4-e2b-q4km",
            "Q4_K_M",
            "bartowski/google_gemma-4-E2B-it-GGUF",
            "google_gemma-4-E2B-it-Q4_K_M.gguf",
            "b5e99bd",
            "b5310340b3a23d31655d7119d100d5df1b2d8ee17b3ca8b0a23ad7e9eb5fa705",
            "plugged in",
            "cool",
            "idle",
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
        stats = conn.execute(
            """
            SELECT pack_id, pack_version, case_id, row_count, ok_count,
                   prompt_token_rows, prompt_token_median,
                   cached_prompt_token_rows, cached_prompt_token_median,
                   prefill_tps_rows, prefill_tps_median
            FROM result_case_stats
            """
        ).fetchone()
        assert stats == (
            "runtime-sweep",
            "0.1.0",
            "short",
            1,
            1,
            1,
            10.0,
            1,
            0.0,
            1,
            100.0,
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
        assert conn.execute("SELECT COUNT(*) FROM result_case_stats").fetchone()[0] == 1


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


def test_registry_import_indexes_repo_commit_fallback_and_nullable_anchors(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    (result_dir / "run-metadata.json").write_text(
        json.dumps(
            {
                "comparison_mode": "",
                "repo": {"commit": "def5678"},
                "runtime": {"name": "llama-server", "options": ["not", "an", "object"]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "registry.sqlite"

    import_result_dirs([result_dir], db_path)

    with sqlite3.connect(db_path) as conn:
        run = conn.execute(
            """
            SELECT host_repo_commit, comparison_mode, runtime_options_json
            FROM runs
            """
        ).fetchone()

    assert run == ("def5678", None, None)


def test_registry_report_loads_indexed_runs_without_source_artifacts(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "results" / "run-a"
    rows = [
        _record("short"),
        _record("short"),
    ]
    _write_result_dir(result_dir, rows)
    (result_dir / "hardware.json").write_text(
        json.dumps({"hostname": "atlas", "chip": "Apple M5 Max"}) + "\n",
        encoding="utf-8",
    )
    (result_dir / "run-metadata.json").write_text(
        json.dumps(
            {
                "runtime": {"name": "llama-server", "version": "9030"},
                "model": {"id": "gemma4-e2b-q4km", "quantization": "Q4_K_M"},
                "operating_conditions": {"power": "plugged in"},
                "notes": "indexed report",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)
    shutil.rmtree(result_dir)

    runs = load_registry_report_runs(db_path)
    output = render_report(runs)

    assert runs[0].artifact_root is None
    assert "| run-a | runtime-sweep 0.1.0 | openai-chat | test-model |" in output
    assert "hostname=atlas; chip=Apple M5 Max" in output
    assert "name=llama-server" in output
    assert "indexed report" in output
    assert (
        "| run-a | short | 2 | 2 | 1.250 | 0.200 | 100.00 | 40.00 | "
        "30.00 | 60 | 10 | 0 | 2/2 | comparable |"
    ) in output


def test_registry_report_filters_by_run_id_or_label(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_result_dir(run_a, [_record("short")])
    _write_result_dir(run_b, [_record("long")])
    db_path = tmp_path / "registry.sqlite"
    summaries = import_result_dirs([run_a, run_b], db_path)

    by_id = load_registry_report_runs(db_path, run_ids=[summaries[1].run_id])
    by_label = load_registry_report_runs(db_path, labels=["run-a"])

    assert [run.label for run in by_id] == ["run-b"]
    assert by_id[0].records[0]["case"] == "long"
    assert [run.label for run in by_label] == ["run-a"]
    assert by_label[0].records[0]["case"] == "short"


def test_registry_report_rejects_missing_selection(tmp_path: Path) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)

    with pytest.raises(RegistryError, match="run_id not found"):
        load_registry_report_runs(db_path, run_ids=[999])

    with pytest.raises(RegistryError, match="either --run-id or --label"):
        load_registry_report_runs(db_path, run_ids=[1], labels=["run-a"])

    with pytest.raises(RegistryError, match="--run-id requires at least one value"):
        load_registry_report_runs(db_path, run_ids=[])

    with pytest.raises(RegistryError, match="--label requires at least one value"):
        load_registry_report_runs(db_path, labels=[])


def test_registry_report_rejects_stale_schema_database(tmp_path: Path) -> None:
    db_path = tmp_path / "registry-v1.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE registry_meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            INSERT INTO registry_meta(key, value) VALUES ('schema_version', '1');
            PRAGMA user_version = 1;
            """
        )

    with pytest.raises(RegistryError, match="requires schema version 2"):
        load_registry_report_runs(db_path)


def test_registry_report_rejects_corrupt_indexed_json(tmp_path: Path) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE result_rows SET raw_json = ?", ("{bad json}",))

    with pytest.raises(RegistryError, match="could not parse indexed raw_json"):
        load_registry_report_runs(db_path)


def test_registry_report_rejects_corrupt_indexed_metadata(tmp_path: Path) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    (result_dir / "hardware.json").write_text(
        json.dumps({"hostname": "atlas"}) + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE runs SET hardware_json = ?", ("[]",))

    with pytest.raises(RegistryError, match="indexed hardware_json"):
        load_registry_report_runs(db_path)


def test_registry_report_cli_renders_indexed_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)

    assert main(["registry", "report", "--db", str(db_path), "--label", "run-a"]) == 0

    output = capsys.readouterr().out
    assert "# benchpack report" in output
    assert "| run-a | short | 1 | 1 | 1.250 |" in output


def test_registry_report_cli_rejects_run_id_and_label_together(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "registry.sqlite"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "registry",
                "report",
                "--db",
                str(db_path),
                "--run-id",
                "1",
                "--label",
                "run-a",
            ]
        )

    assert exc_info.value.code == 2


def test_registry_import_upgrades_schema_v1_database(tmp_path: Path) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    (result_dir / "run-metadata.json").write_text(
        json.dumps(
            {
                "comparison_mode": "runtime-and-format",
                "runtime": {
                    "name": "vllm",
                    "endpoint": "https://example.test/v1",
                    "options": {"tensor_parallel_size": 1},
                },
                "model": {
                    "id": "google/gemma-4-E2B-it",
                    "artifact_repo": "google/gemma-4-E2B-it",
                    "revision": "main",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "registry.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE registry_meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            INSERT INTO registry_meta(key, value) VALUES ('schema_version', '1');
            CREATE TABLE runs (
              id INTEGER PRIMARY KEY,
              result_dir TEXT NOT NULL UNIQUE,
              label TEXT NOT NULL,
              imported_at TEXT NOT NULL,
              row_count INTEGER NOT NULL,
              run_jsonl_sha256 TEXT NOT NULL,
              pack_ids_json TEXT NOT NULL,
              pack_versions_json TEXT NOT NULL,
              adapters_json TEXT NOT NULL,
              models_json TEXT NOT NULL,
              endpoints_json TEXT NOT NULL,
              hardware_json TEXT,
              run_metadata_json TEXT,
              host_hostname TEXT,
              host_platform TEXT,
              runtime_name TEXT,
              runtime_version TEXT,
              model_metadata_id TEXT,
              model_quantization TEXT
            );
            CREATE TABLE result_rows (
              id INTEGER PRIMARY KEY,
              run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
              row_index INTEGER NOT NULL,
              pack_id TEXT NOT NULL,
              pack_version TEXT NOT NULL,
              case_id TEXT NOT NULL,
              repetition INTEGER,
              adapter TEXT NOT NULL,
              model TEXT NOT NULL,
              endpoint TEXT NOT NULL,
              ok INTEGER NOT NULL,
              wall_s REAL,
              ttft_s REAL,
              prefill_tps REAL,
              decode_tps REAL,
              total_tps REAL,
              prompt_tokens INTEGER,
              output_tokens INTEGER,
              cached_prompt_tokens INTEGER,
              scoring_mode TEXT,
              scoring_passed INTEGER,
              repo_task_status TEXT,
              verify_exit_code INTEGER,
              raw_json TEXT NOT NULL,
              UNIQUE(run_id, row_index)
            );
            PRAGMA user_version = 1;
            """
        )

    import_result_dirs([result_dir], db_path)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        run = conn.execute(
            """
            SELECT comparison_mode, runtime_endpoint, runtime_options_json,
                   model_artifact_repo, model_revision
            FROM runs
            """
        ).fetchone()
        stats_count = conn.execute(
            "SELECT COUNT(*) FROM result_case_stats"
        ).fetchone()[0]
    assert run == (
        "runtime-and-format",
        "https://example.test/v1",
        '{"tensor_parallel_size":1}',
        "google/gemma-4-E2B-it",
        "main",
    )
    assert stats_count == 1


def test_registry_import_rolls_back_schema_upgrade_on_sqlite_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE registry_meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            INSERT INTO registry_meta(key, value) VALUES ('schema_version', '1');
            CREATE TABLE runs (
              id INTEGER PRIMARY KEY,
              result_dir TEXT NOT NULL UNIQUE,
              label TEXT NOT NULL,
              imported_at TEXT NOT NULL,
              row_count INTEGER NOT NULL,
              run_jsonl_sha256 TEXT NOT NULL,
              pack_ids_json TEXT NOT NULL,
              pack_versions_json TEXT NOT NULL,
              adapters_json TEXT NOT NULL,
              models_json TEXT NOT NULL,
              endpoints_json TEXT NOT NULL,
              hardware_json TEXT,
              run_metadata_json TEXT,
              host_hostname TEXT,
              host_platform TEXT,
              runtime_name TEXT,
              runtime_version TEXT,
              model_metadata_id TEXT,
              model_quantization TEXT
            );
            CREATE TABLE result_rows (
              id INTEGER PRIMARY KEY,
              run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
              row_index INTEGER NOT NULL,
              pack_id TEXT NOT NULL,
              pack_version TEXT NOT NULL,
              case_id TEXT NOT NULL,
              repetition INTEGER,
              adapter TEXT NOT NULL,
              model TEXT NOT NULL,
              endpoint TEXT NOT NULL,
              ok INTEGER NOT NULL,
              wall_s REAL,
              ttft_s REAL,
              prefill_tps REAL,
              decode_tps REAL,
              total_tps REAL,
              prompt_tokens INTEGER,
              output_tokens INTEGER,
              cached_prompt_tokens INTEGER,
              scoring_mode TEXT,
              scoring_passed INTEGER,
              repo_task_status TEXT,
              verify_exit_code INTEGER,
              raw_json TEXT NOT NULL,
              UNIQUE(run_id, row_index)
            );
            PRAGMA user_version = 1;
            """
        )

    def fail_import(*args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("forced import failure")

    monkeypatch.setattr(registry, "_import_run", fail_import)

    with pytest.raises(RegistryError, match="forced import failure"):
        import_result_dirs([result_dir], db_path)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert conn.execute(
            "SELECT value FROM registry_meta WHERE key = 'schema_version'"
        ).fetchone()[0] == "1"
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        case_stats = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'result_case_stats'
            """
        ).fetchone()
    assert "comparison_mode" not in columns
    assert case_stats is None


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


def test_registry_bundle_create_copies_compact_public_artifacts(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    record = _record()
    record["patch"] = {"path": "patch/short/rep-001.diff"}
    _write_result_dir(result_dir, [record])
    (result_dir / "hardware.json").write_text(
        json.dumps({"hostname": "atlas", "platform": "Darwin"}) + "\n",
        encoding="utf-8",
    )
    (result_dir / "run-metadata.json").write_text(
        json.dumps({"runtime": {"name": "llama-server"}, "notes": "shareable"}) + "\n",
        encoding="utf-8",
    )
    (result_dir / "raw").mkdir()
    (result_dir / "raw" / "short.request.json").write_text(
        '{"prompt":"private prompt omitted"}\n',
        encoding="utf-8",
    )
    (result_dir / "raw" / "short.response.json").write_text(
        '{"content":"private response omitted"}\n',
        encoding="utf-8",
    )
    (result_dir / "patch" / "short").mkdir(parents=True)
    (result_dir / "patch" / "short" / "rep-001.diff").write_text(
        "--- a/app.py\n+++ b/app.py\n",
        encoding="utf-8",
    )
    bundle_dir = tmp_path / "bundle"

    summary = create_result_bundle(
        [result_dir],
        bundle_dir,
        provenance="operator-curated",
    )
    validated = validate_result_bundle(bundle_dir)

    assert summary.runs == 1
    assert summary.provenance == "operator-curated"
    assert validated.files == summary.files
    manifest = json.loads((bundle_dir / BUNDLE_MANIFEST_FILENAME).read_text())
    run = manifest["runs"][0]
    assert run["source_result_name"] == "run-a"
    assert "source_result_dir" not in run
    copied_paths = {entry["path"] for entry in run["files"]}
    assert copied_paths == {
        "runs/run-001-run-a/run.jsonl",
        "runs/run-001-run-a/hardware.json",
        "runs/run-001-run-a/run-metadata.json",
        "runs/run-001-run-a/patch/short/rep-001.diff",
    }
    assert not (bundle_dir / "runs" / "run-001-run-a" / "raw").exists()
    omitted = {entry["path"]: entry for entry in run["omitted_artifacts"]}
    assert omitted["raw/short.request.json"]["reason"] == "raw-payload-omitted"
    assert len(omitted["raw/short.request.json"]["sha256"]) == 64


def test_registry_bundle_create_rejects_possible_secret(tmp_path: Path) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    (result_dir / "run-metadata.json").write_text(
        json.dumps({"notes": "Authorization: Bearer sk-test-secret-value"}) + "\n",
        encoding="utf-8",
    )
    bundle_dir = tmp_path / "bundle"

    with pytest.raises(RegistryError, match="possible secret"):
        create_result_bundle([result_dir], bundle_dir)

    assert not bundle_dir.exists()


def test_registry_bundle_create_rejects_output_inside_result_dir(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)

    with pytest.raises(RegistryError, match="disjoint"):
        create_result_bundle([result_dir], result_dir / "bundle", force=True)

    assert not (result_dir / "bundle").exists()


def test_registry_bundle_create_rejects_output_parent_of_result_dir(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    result_dir = results_dir / "run-a"
    _write_result_dir(result_dir)

    with pytest.raises(RegistryError, match="disjoint"):
        create_result_bundle([result_dir], results_dir, force=True)

    assert result_dir.exists()
    assert (result_dir / "run.jsonl").exists()


def test_registry_bundle_accepts_patch_case_named_task(tmp_path: Path) -> None:
    result_dir = tmp_path / "run-a"
    record = _record("task")
    record["patch"] = {"path": "patch/task/rep-001.diff"}
    _write_result_dir(result_dir, [record])
    (result_dir / "patch" / "task").mkdir(parents=True)
    (result_dir / "patch" / "task" / "rep-001.diff").write_text(
        "--- a/app.py\n+++ b/app.py\n",
        encoding="utf-8",
    )
    bundle_dir = tmp_path / "bundle"

    create_result_bundle([result_dir], bundle_dir)
    summary = validate_result_bundle(bundle_dir)

    assert summary.runs == 1
    manifest = json.loads((bundle_dir / BUNDLE_MANIFEST_FILENAME).read_text())
    paths = {entry["path"] for entry in manifest["runs"][0]["files"]}
    assert "runs/run-001-run-a/patch/task/rep-001.diff" in paths


def test_registry_bundle_omits_malformed_model_call_log_name(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    model_call_dir = result_dir / "task" / "case"
    model_call_dir.mkdir(parents=True)
    (model_call_dir / "rep-X.model-calls.jsonl").write_text(
        json.dumps({"schema_version": 1, "sequence": 1, "model": "m", "ok": True})
        + "\n",
        encoding="utf-8",
    )
    bundle_dir = tmp_path / "bundle"

    create_result_bundle([result_dir], bundle_dir)

    manifest = json.loads((bundle_dir / BUNDLE_MANIFEST_FILENAME).read_text())
    omitted = {entry["path"]: entry for entry in manifest["runs"][0]["omitted_artifacts"]}
    assert omitted["task/case/rep-X.model-calls.jsonl"]["reason"] == (
        "unsafe-model-call-log-omitted"
    )


def test_registry_bundle_create_rejects_non_utf8_copied_file(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    record = _record()
    record["patch"] = {"path": "patch/short/rep-001.diff"}
    _write_result_dir(result_dir, [record])
    (result_dir / "patch" / "short").mkdir(parents=True)
    (result_dir / "patch" / "short" / "rep-001.diff").write_bytes(b"\xff")
    bundle_dir = tmp_path / "bundle"

    with pytest.raises(RegistryError, match="could not decode bundle file"):
        create_result_bundle([result_dir], bundle_dir)

    assert not bundle_dir.exists()


def test_registry_bundle_validate_rejects_non_utf8_copied_file(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    record = _record()
    record["patch"] = {"path": "patch/short/rep-001.diff"}
    _write_result_dir(result_dir, [record])
    (result_dir / "patch" / "short").mkdir(parents=True)
    (result_dir / "patch" / "short" / "rep-001.diff").write_text(
        "--- a/app.py\n+++ b/app.py\n",
        encoding="utf-8",
    )
    bundle_dir = tmp_path / "bundle"
    create_result_bundle([result_dir], bundle_dir)
    bundled_patch = bundle_dir / "runs" / "run-001-run-a" / "patch" / "short" / "rep-001.diff"
    bundled_patch.write_bytes(b"\xff")
    manifest_path = bundle_dir / BUNDLE_MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["runs"][0]["files"]:
        if entry["path"] == "runs/run-001-run-a/patch/short/rep-001.diff":
            entry["sha256"] = hashlib.sha256(b"\xff").hexdigest()
            entry["bytes"] = 1
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(RegistryError, match="could not decode bundle file"):
        validate_result_bundle(bundle_dir)


def test_registry_bundle_validate_rejects_unlisted_files(tmp_path: Path) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    bundle_dir = tmp_path / "bundle"
    create_result_bundle([result_dir], bundle_dir)
    leaked = bundle_dir / "runs" / "run-001-run-a" / "raw" / "request.json"
    leaked.parent.mkdir()
    leaked.write_text('{"prompt":"not in manifest"}\n', encoding="utf-8")

    with pytest.raises(RegistryError, match="unlisted file"):
        validate_result_bundle(bundle_dir)
