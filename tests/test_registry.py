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
    export_registry_static_site,
    find_registry_duplicate_runs,
    import_agent_wrap_results,
    import_result_bundles,
    import_result_dirs,
    load_registry_report_runs,
    query_agent_wrap_results,
    query_registry_results,
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

    with pytest.raises(RegistryError, match="requires schema version 3"):
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


def test_registry_duplicates_finds_runs_with_same_run_jsonl(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    run_c = tmp_path / "run-c"
    _write_result_dir(run_a, [_record("short")])
    _write_result_dir(run_b, [_record("short")])
    _write_result_dir(run_c, [_record("long")])
    db_path = tmp_path / "registry.sqlite"
    summaries = import_result_dirs([run_a, run_b, run_c], db_path)

    groups = find_registry_duplicate_runs(db_path)

    assert len(groups) == 1
    assert len(groups[0].run_jsonl_sha256) == 64
    assert [run.run_id for run in groups[0].runs] == [
        summaries[0].run_id,
        summaries[1].run_id,
    ]
    assert [run.label for run in groups[0].runs] == ["run-a", "run-b"]
    assert [run.result_dir for run in groups[0].runs] == [
        run_a.resolve(),
        run_b.resolve(),
    ]


def test_registry_duplicates_cli_reports_groups(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_result_dir(run_a)
    _write_result_dir(run_b)
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([run_a, run_b], db_path)

    assert main(["registry", "duplicates", "--db", str(db_path)]) == 0

    output = capsys.readouterr().out
    assert "duplicate run.jsonl sha256" in output
    assert "run_id=1 label=run-a rows=1" in output
    assert "run_id=2 label=run-b rows=1" in output


def test_registry_duplicates_cli_reports_no_duplicates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_result_dir(run_a, [_record("short")])
    _write_result_dir(run_b, [_record("long")])
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([run_a, run_b], db_path)

    assert main(["registry", "duplicates", "--db", str(db_path)]) == 0

    assert capsys.readouterr().out == "no duplicate run.jsonl artifacts found\n"


def test_registry_duplicates_rejects_missing_database(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="database not found"):
        find_registry_duplicate_runs(tmp_path / "missing.sqlite")


def test_registry_query_filters_normalized_rows(tmp_path: Path) -> None:
    passed = _record("short")
    passed["scoring"] = {"mode": "contains", "passed": True}
    failed = _record("long")
    failed["ok"] = False
    failed["scoring"] = {"mode": "contains", "passed": False}
    failed["repo_task"] = {"status": "failed", "verify_exit_code": 1}
    run_a = tmp_path / "run-a"
    _write_result_dir(run_a, [passed, failed])
    (run_a / "hardware.json").write_text(
        json.dumps({"hostname": "atlas", "platform": "Darwin"}) + "\n",
        encoding="utf-8",
    )
    (run_a / "run-metadata.json").write_text(
        json.dumps(
            {
                "comparison_mode": "strict-same-gguf",
                "host": {"label": "m5-max", "repo_commit": "abc1234"},
                "runtime": {"name": "llama-server", "version": "9030"},
                "model": {
                    "id": "gemma4-e2b-q4km",
                    "quantization": "Q4_K_M",
                    "artifact_repo": "bartowski/google_gemma-4-E2B-it-GGUF",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_b = tmp_path / "run-b"
    other = _record("short")
    other["model"] = "other-model"
    _write_result_dir(run_b, [other])
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([run_a, run_b], db_path)

    rows = query_registry_results(
        db_path,
        labels=["run-a"],
        host_label="m5-max",
        runtime_name="llama-server",
        model_quantization="Q4_K_M",
        scoring_passed=False,
    )

    assert len(rows) == 1
    data = rows[0]
    assert data["label"] == "run-a"
    assert data["case"] == "long"
    assert data["ok"] is False
    assert data["scoring"] == {"mode": "contains", "passed": False}
    assert data["repo_task"] == {"status": "failed", "verify_exit_code": 1}
    assert data["host"] == {
        "label": "m5-max",
        "platform": "Darwin",
        "repo_commit": "abc1234",
    }
    assert data["runtime"] == {
        "name": "llama-server",
        "version": "9030",
        "endpoint": None,
    }
    assert data["model_metadata"]["quantization"] == "Q4_K_M"


def test_registry_query_cli_outputs_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_a = tmp_path / "run-a"
    _write_result_dir(run_a, [_record("short"), _record("long")])
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([run_a], db_path)

    assert (
        main(
            [
                "registry",
                "query",
                "--db",
                str(db_path),
                "--case",
                "long",
                "--ok",
                "true",
                "--limit",
                "1",
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert len(output) == 1
    assert output[0]["label"] == "run-a"
    assert output[0]["case"] == "long"
    assert output[0]["timing"]["wall_s"] == 1.25


def test_registry_query_rejects_invalid_limit(tmp_path: Path) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)

    with pytest.raises(RegistryError, match="--limit"):
        query_registry_results(db_path, limit=0)


def test_registry_query_returns_empty_list_when_row_filters_match_nothing(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)

    rows = query_registry_results(db_path, labels=["run-a"], case_id="missing")

    assert rows == []


def test_registry_agent_wrap_import_queries_normalized_rows(tmp_path: Path) -> None:
    data_path = Path(__file__).resolve().parents[1] / "data" / "agent-wrap-oneshot-results.json"
    db_path = tmp_path / "registry.sqlite"

    summary = import_agent_wrap_results(data_path, db_path)
    second = import_agent_wrap_results(data_path, db_path)

    assert summary.rows_imported == 21
    assert second.rows_imported == 21
    rows = query_agent_wrap_results(
        db_path,
        status="pass",
        harness="pipy",
        model="gpt-5.5",
        thinking="off",
    )
    assert len(rows) == 1
    assert rows[0]["label"] == "pipy-gpt55-django-resume-030-off"
    assert rows[0]["provider"]["id"] == "openai-codex"
    assert rows[0]["timing"]["wall_seconds"] == 1003.5

    pass_rows = query_agent_wrap_results(db_path, status="pass")
    assert len(pass_rows) == 17
    assert pass_rows[0]["label"] == "gpt55-pi-django-resume-030-off"
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM agent_wrap_runs").fetchone()[0]
        fastest = conn.execute(
            "SELECT label FROM agent_wrap_runs ORDER BY wall_seconds LIMIT 1"
        ).fetchone()[0]
    assert count == 21
    assert fastest == "gpt55-pi-django-resume-030-off"


def test_registry_agent_wrap_import_prunes_removed_dataset_rows(
    tmp_path: Path,
) -> None:
    data_path = Path(__file__).resolve().parents[1] / "data" / "agent-wrap-oneshot-results.json"
    db_path = tmp_path / "registry.sqlite"
    import_agent_wrap_results(data_path, db_path)
    dataset = json.loads(data_path.read_text(encoding="utf-8"))
    removed_label = dataset["rows"][-1]["label"]
    dataset["rows"] = dataset["rows"][:-1]
    pruned_path = tmp_path / "agent-wrap-pruned.json"
    pruned_path.write_text(json.dumps(dataset), encoding="utf-8")

    import_agent_wrap_results(pruned_path, db_path)

    rows = query_agent_wrap_results(db_path)
    assert len(rows) == 20
    assert removed_label not in {row["label"] for row in rows}


def test_registry_schema_setup_backfills_missing_case_stats(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM result_case_stats")
    data_path = Path(__file__).resolve().parents[1] / "data" / "agent-wrap-oneshot-results.json"

    import_agent_wrap_results(data_path, db_path)

    with sqlite3.connect(db_path) as conn:
        stats = conn.execute(
            """
            SELECT pack_id, case_id, row_count, ok_count
            FROM result_case_stats
            """
        ).fetchall()
    assert stats == [("runtime-sweep", "short", 1, 1)]


def test_registry_agent_wrap_cli_import_and_query(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_path = Path(__file__).resolve().parents[1] / "data" / "agent-wrap-oneshot-results.json"
    db_path = tmp_path / "registry.sqlite"

    assert main(
        [
            "registry",
            "agent-wrap",
            "import",
            "--db",
            str(db_path),
            str(data_path),
        ]
    ) == 0
    assert "imported 21 agent-wrap rows" in capsys.readouterr().out

    assert main(
        [
            "registry",
            "agent-wrap",
            "query",
            "--db",
            str(db_path),
            "--harness",
            "claude-yolo",
            "--provider",
            "anthropic",
            "--thinking",
            "medium",
            "--limit",
            "1",
        ]
    ) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["label"] == "opus48-claude-yolo-django-resume-030-medium"


def test_registry_query_rejects_run_id_and_label_together(tmp_path: Path) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)

    with pytest.raises(RegistryError, match="registry query accepts either"):
        query_registry_results(db_path, run_ids=[1], labels=["run-a"])


def test_registry_query_missing_selection_error_names_query(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)

    with pytest.raises(RegistryError, match="registry query run_id not found"):
        query_registry_results(db_path, run_ids=[999])


def test_registry_site_missing_selection_error_names_site(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)

    with pytest.raises(RegistryError, match="registry site label not found"):
        export_registry_static_site(db_path, tmp_path / "site", labels=["missing"])


def test_registry_static_site_export_writes_snapshot_without_source_artifacts(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "results" / "run-a"
    rows = [_record("short"), _record("long")]
    _write_result_dir(result_dir, rows)
    (result_dir / "hardware.json").write_text(
        json.dumps({"hostname": "atlas", "platform": "Darwin"}) + "\n",
        encoding="utf-8",
    )
    (result_dir / "run-metadata.json").write_text(
        json.dumps(
            {
                "comparison_mode": "strict-same-gguf",
                "host": {"label": "m5-max", "repo_commit": "abc1234"},
                "runtime": {
                    "name": "llama-server",
                    "version": "9030",
                    "endpoint": "http://127.0.0.1:8081/v1",
                },
                "model": {
                    "id": "gemma4-e2b-q4km",
                    "artifact_repo": "bartowski/google_gemma-4-E2B-it-GGUF",
                    "artifact_file": "google_gemma-4-E2B-it-Q4_K_M.gguf",
                    "revision": "b5e99bd",
                    "quantization": "Q4_K_M",
                    "sha256": "b5310340b3a23d31655d7119d100d5df1b2d8ee17b3ca8b0a23ad7e9eb5fa705",
                },
                "operating_conditions": {"power": "plugged in"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)
    shutil.rmtree(result_dir)

    summary = export_registry_static_site(db_path, tmp_path / "site")

    assert summary.runs == 1
    assert summary.files == 3
    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    report = (tmp_path / "site" / "report.md").read_text(encoding="utf-8")
    snapshot = json.loads(
        (tmp_path / "site" / "snapshot.json").read_text(encoding="utf-8")
    )
    assert "benchpack registry snapshot" in html
    assert 'href="snapshot.json"' in html
    assert "<h2>Browse Filters</h2>" in html
    assert 'id="filter-search"' in html
    assert 'id="filter-pack"' in html
    assert '<option value="runtime-sweep">runtime-sweep</option>' in html
    assert '<option value="short">short</option>' in html
    assert '<option value="atlas">atlas</option>' in html
    assert '<option value="m5-max">m5-max</option>' in html
    assert '<option value="llama-server">llama-server</option>' in html
    assert '<option value="test-model">test-model</option>' in html
    assert '<option value="gemma4-e2b-q4km">gemma4-e2b-q4km</option>' in html
    assert '<option value="q4_k_m">Q4_K_M</option>' in html
    assert 'data-table="comparison"' in html
    assert 'data-registry-section="comparison"' in html
    assert 'data-registry-section="cases"' in html
    assert 'data-pack="[&quot;runtime-sweep&quot;]"' in html
    assert 'data-host="[&quot;m5-max&quot;,&quot;atlas&quot;,&quot;darwin&quot;]"' in html
    assert 'data-runtime="[&quot;llama-server&quot;]"' in html
    assert 'data-model="[&quot;gemma4-e2b-q4km&quot;,&quot;test-model&quot;]"' in html
    assert "JSON.parse(row.dataset[id]||'[]')" in html
    assert "function applyFilters()" in html
    assert "<td>run-a</td>" in html
    assert "<td>runtime-sweep 0.1.0</td>" in html
    assert "<td>openai-chat</td>" in html
    assert "<td>test-model</td>" in html
    assert "<td>http://example.test/v1/chat/completions</td>" in html
    assert "<td>llama-server; 9030; http://127.0.0.1:8081/v1</td>" in html
    assert "<td>gemma4-e2b-q4km</td>" in html
    assert "<td>Q4_K_M</td>" in html
    assert (
        "<td>bartowski/google_gemma-4-E2B-it-GGUF; "
        "google_gemma-4-E2B-it-Q4_K_M.gguf</td>"
    ) in html
    assert "<td>b5e99bd</td>" in html
    assert "<td>b5310340b3a23d31655d7119d100d5df1b2d8ee17b3ca8b0a23ad7e9eb5fa705</td>" in html
    assert "<td>m5-max; atlas; Darwin</td>" in html
    assert "<td>strict-same-gguf</td>" in html
    assert "<td>abc1234</td>" in html
    assert "<td>plugged in</td>" in html
    assert "<h2>Comparison Matrix</h2>" in html
    assert "<th>decode TPS med</th>" in html
    assert "<td>m5-max; Darwin</td>" in html
    assert "<td>llama-server</td>" in html
    assert "<td>gemma4-e2b-q4km</td>" in html
    # Matrix medians from the fixture rows: total_tps and output_tokens.
    assert "<td>30.00</td>" in html
    assert "<td>60.00</td>" in html
    assert "<td>long</td>" in html
    assert "# benchpack report" in report
    assert "| run-a | short | 1 | 1 | 1.250 |" in report
    assert snapshot["schema_version"] == 1
    assert snapshot["registry_schema_version"] == 3
    assert snapshot["source_database"] == "registry.sqlite"
    assert snapshot["report_path"] == "report.md"
    assert snapshot["runs"][0]["label"] == "run-a"
    assert snapshot["runs"][0]["packs"] == [
        {"id": "runtime-sweep", "version": "0.1.0"}
    ]
    assert snapshot["runs"][0]["pack_versions"] == ["0.1.0"]
    assert snapshot["runs"][0]["runtime"]["name"] == "llama-server"
    assert snapshot["runs"][0]["model_metadata"]["quantization"] == "Q4_K_M"
    assert snapshot["comparison_matrix"][0]["run_id"] == snapshot["runs"][0]["id"]
    assert snapshot["comparison_matrix"][0]["run"] == "run-a"
    assert snapshot["comparison_matrix"][0]["host"] == {
        "label": "m5-max",
        "hostname": "atlas",
        "platform": "Darwin",
    }
    assert snapshot["comparison_matrix"][0]["model"] == "test-model"
    assert snapshot["comparison_matrix"][0]["medians"]["total_tps"] == 30.0
    assert snapshot["comparison_matrix"][0]["medians"]["output_tokens"] == 60.0
    assert snapshot["case_metrics"][0]["run_id"] == snapshot["runs"][0]["id"]
    assert snapshot["case_metrics"][0]["prompt_tokens"] == {
        "rows": 1,
        "median": 10.0,
    }
    assert snapshot["case_metrics"][0]["host"] == {
        "label": "m5-max",
        "hostname": "atlas",
        "platform": "Darwin",
    }
    assert snapshot["case_metrics"][0]["runtime"] == {"name": "llama-server"}
    assert snapshot["case_metrics"][0]["models"] == ["test-model"]
    assert snapshot["case_metrics"][0]["model_metadata"] == {
        "id": "gemma4-e2b-q4km",
        "quantization": "Q4_K_M",
    }
    assert snapshot["agent_wrap_runs"] == []


def test_registry_static_site_exports_agent_wrap_rows_without_run_jsonl(
    tmp_path: Path,
) -> None:
    data_path = Path(__file__).resolve().parents[1] / "data" / "agent-wrap-oneshot-results.json"
    db_path = tmp_path / "registry.sqlite"
    import_agent_wrap_results(data_path, db_path)

    summary = export_registry_static_site(db_path, tmp_path / "site")

    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    report = (tmp_path / "site" / "report.md").read_text(encoding="utf-8")
    snapshot = json.loads(
        (tmp_path / "site" / "snapshot.json").read_text(encoding="utf-8")
    )
    assert summary.runs == 0
    assert "<h2>Agent Wrap One-Shot Runs</h2>" in html
    assert 'data-table="agent-wrap"' in html
    assert '<option value="gpt-5.5">gpt-5.5</option>' in html
    assert '<option value="claude-opus-4.8">claude-opus-4.8</option>' in html
    assert "Pipy / openai-codex" in html
    assert "filter-harness" in html
    assert "No imported benchpack result rows are selected." in report
    assert len(snapshot["agent_wrap_runs"]) == 21
    assert snapshot["agent_wrap_runs"][0]["label"] == "gpt55-pi-django-resume-030-off"


def test_registry_static_site_export_requires_force_for_existing_output(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "old.txt").write_text("old\n", encoding="utf-8")

    with pytest.raises(RegistryError, match="already exists"):
        export_registry_static_site(db_path, site_dir)

    summary = export_registry_static_site(db_path, site_dir, force=True)

    assert summary.runs == 1
    assert not (site_dir / "old.txt").exists()
    assert (site_dir / "index.html").is_file()


def test_registry_static_site_force_keeps_existing_output_on_read_failure(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "missing.sqlite"
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "old.txt").write_text("old\n", encoding="utf-8")

    with pytest.raises(RegistryError, match="database not found"):
        export_registry_static_site(db_path, site_dir, force=True)

    assert (site_dir / "old.txt").read_text(encoding="utf-8") == "old\n"


def test_registry_static_site_rejects_invalid_programmatic_selection(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)

    with pytest.raises(RegistryError, match="--run-id requires at least one value"):
        export_registry_static_site(db_path, tmp_path / "empty-run-ids", run_ids=[])

    with pytest.raises(RegistryError, match="--label requires at least one value"):
        export_registry_static_site(db_path, tmp_path / "empty-labels", labels=[])

    with pytest.raises(RegistryError, match="values must be integers"):
        export_registry_static_site(
            db_path,
            tmp_path / "bad-run-id",
            run_ids=["1"],  # type: ignore[list-item]
        )

    with pytest.raises(RegistryError, match="values must be non-empty"):
        export_registry_static_site(
            db_path,
            tmp_path / "bad-label",
            labels=[1],  # type: ignore[list-item]
        )


def test_registry_static_site_renders_versions_for_multi_pack_runs(
    tmp_path: Path,
) -> None:
    run_a = _record("short")
    run_a["pack"] = {"id": "pack-a", "version": "0.2.0"}
    run_b = _record("long")
    run_b["pack"] = {"id": "pack-b", "version": "0.1.0"}
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir, [run_a, run_b])
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)

    export_registry_static_site(db_path, tmp_path / "site")

    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "<td>pack-a, pack-b (versions: 0.1.0, 0.2.0)</td>" in html


def test_registry_static_site_distinguishes_unscored_from_zero_passes(
    tmp_path: Path,
) -> None:
    unscored_a = _record("unscored")
    unscored_b = _record("unscored")
    failed_a = _record("scored")
    failed_b = _record("scored")
    failed_a["scoring"] = {"mode": "contains", "passed": False}
    failed_b["scoring"] = {"mode": "contains", "passed": False}
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir, [unscored_a, unscored_b, failed_a, failed_b])
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([result_dir], db_path)

    export_registry_static_site(db_path, tmp_path / "site")

    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert (
        "<td>unscored</td><td>—</td><td>—</td><td>—</td><td>—</td>"
        "<td>2</td><td>2</td><td>—</td>"
    ) in html
    assert (
        "<td>scored</td><td>—</td><td>—</td><td>—</td><td>—</td>"
        "<td>2</td><td>2</td><td>0/2</td>"
    ) in html


def test_registry_static_site_cli_writes_selected_runs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_result_dir(run_a, [_record("short")])
    _write_result_dir(run_b, [_record("long")])
    db_path = tmp_path / "registry.sqlite"
    import_result_dirs([run_a, run_b], db_path)
    site_dir = tmp_path / "site"

    assert (
        main(
            [
                "registry",
                "site",
                "--db",
                str(db_path),
                "--out",
                str(site_dir),
                "--label",
                "run-b",
            ]
        )
        == 0
    )

    assert "created registry site" in capsys.readouterr().out
    html = (site_dir / "index.html").read_text(encoding="utf-8")
    assert "<td>run-b</td>" in html
    assert "<td>long</td>" in html
    assert "<td>run-a</td>" not in html


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
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
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
        agent_wrap_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'agent_wrap_runs'"
        ).fetchone()
    assert run == (
        "runtime-and-format",
        "https://example.test/v1",
        '{"tensor_parallel_size":1}',
        "google/gemma-4-E2B-it",
        "main",
    )
    assert stats_count == 1
    assert agent_wrap_table == ("agent_wrap_runs",)


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


def test_registry_bundle_import_indexes_validated_compact_runs(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "results" / "run-a"
    record = _record()
    record["patch"] = {"path": "patch/short/rep-001.diff"}
    _write_result_dir(result_dir, [record])
    (result_dir / "hardware.json").write_text(
        json.dumps({"hostname": "atlas", "platform": "Darwin"}) + "\n",
        encoding="utf-8",
    )
    (result_dir / "run-metadata.json").write_text(
        json.dumps(
            {
                "comparison_mode": "strict-same-gguf",
                "runtime": {"name": "llama-server"},
                "model": {"id": "gemma4-e2b-q4km"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (result_dir / "patch" / "short").mkdir(parents=True)
    (result_dir / "patch" / "short" / "rep-001.diff").write_text(
        "--- a/app.py\n+++ b/app.py\n",
        encoding="utf-8",
    )
    bundle_dir = tmp_path / "bundle"
    create_result_bundle([result_dir], bundle_dir, provenance="operator-curated")
    shutil.rmtree(result_dir)
    db_path = tmp_path / "registry.sqlite"

    summaries = import_result_bundles([bundle_dir], db_path)
    runs = load_registry_report_runs(db_path, labels=["run-a"])

    assert summaries[0].rows_imported == 1
    assert summaries[0].result_dir == bundle_dir / "runs" / "run-001-run-a"
    assert runs[0].label == "run-a"
    assert runs[0].records[0]["case"] == "short"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT label, host_hostname, comparison_mode, runtime_name,
                   model_metadata_id
            FROM runs
            """
        ).fetchone()
    assert row == (
        "run-a",
        "atlas",
        "strict-same-gguf",
        "llama-server",
        "gemma4-e2b-q4km",
    )


def test_registry_bundle_import_validates_all_inputs_before_writing_db(
    tmp_path: Path,
) -> None:
    good_result = tmp_path / "run-good"
    _write_result_dir(good_result)
    good_bundle = tmp_path / "bundle-good"
    create_result_bundle([good_result], good_bundle)
    bad_result = tmp_path / "run-bad"
    _write_result_dir(bad_result)
    bad_bundle = tmp_path / "bundle-bad"
    create_result_bundle([bad_result], bad_bundle)
    manifest_path = bad_bundle / BUNDLE_MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runs"][0]["files"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    db_path = tmp_path / "registry.sqlite"

    with pytest.raises(RegistryError, match="hash mismatch"):
        import_result_bundles([good_bundle, bad_bundle], db_path)

    assert not db_path.exists()


def test_registry_bundle_import_replaces_same_bundled_run_on_reimport(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "run-a"
    _write_result_dir(result_dir)
    bundle_dir = tmp_path / "bundle"
    create_result_bundle([result_dir], bundle_dir)
    db_path = tmp_path / "registry.sqlite"

    first = import_result_bundles([bundle_dir], db_path)
    second = import_result_bundles([bundle_dir], db_path)

    assert first[0].run_id == second[0].run_id
    assert second[0].rows_imported == 1
    with sqlite3.connect(db_path) as conn:
        row_count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        result_rows = conn.execute("SELECT COUNT(*) FROM result_rows").fetchone()[0]
    assert row_count == 1
    assert result_rows == 1


def test_registry_bundle_import_accepts_multiple_bundles_in_one_call(
    tmp_path: Path,
) -> None:
    result_a = tmp_path / "run-a"
    result_b = tmp_path / "run-b"
    _write_result_dir(result_a, [_record("short")])
    _write_result_dir(result_b, [_record("long")])
    bundle_a = tmp_path / "bundle-a"
    bundle_b = tmp_path / "bundle-b"
    create_result_bundle([result_a], bundle_a)
    create_result_bundle([result_b], bundle_b)
    db_path = tmp_path / "registry.sqlite"

    summaries = import_result_bundles([bundle_a, bundle_b], db_path)

    assert [summary.rows_imported for summary in summaries] == [1, 1]
    with sqlite3.connect(db_path) as conn:
        labels = [
            row[0]
            for row in conn.execute("SELECT label FROM runs ORDER BY label").fetchall()
        ]
        cases = [
            row[0]
            for row in conn.execute(
                "SELECT case_id FROM result_rows ORDER BY case_id"
            ).fetchall()
        ]
    assert labels == ["run-a", "run-b"]
    assert cases == ["long", "short"]


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
