"""Tests for read-only Markdown report rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchpack.report import (
    ReportError,
    load_report_runs,
    load_report_set,
    render_report,
)


def _write_run(
    path: Path,
    *,
    pack_id: str = "runtime-sweep",
    version: str = "0.1.0",
    hardware: dict | None = None,
    metadata: dict | None = None,
    rows: list[dict] | None = None,
) -> None:
    path.mkdir(parents=True)
    records = rows or [_record("short", pack_id=pack_id, version=version)]
    (path / "run.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    if hardware is not None:
        (path / "hardware.json").write_text(
            json.dumps(hardware) + "\n",
            encoding="utf-8",
        )
    if metadata is not None:
        (path / "run-metadata.json").write_text(
            json.dumps(metadata) + "\n",
            encoding="utf-8",
        )


def _record(
    case: str,
    *,
    pack_id: str = "runtime-sweep",
    version: str = "0.1.0",
    ok: bool = True,
    wall_s: float = 1.0,
    prefill_tps: float = 100.0,
    prompt_tokens: int = 10,
    cached_prompt: int | None = None,
    scoring: dict | None = None,
    patch: dict | None = None,
    repo_task: dict | None = None,
    repetition: int | None = None,
) -> dict:
    record = {
        "pack": {"id": pack_id, "version": version},
        "case": case,
        "adapter": "openai-chat",
        "endpoint": "http://example.test/v1/chat/completions",
        "model": "model",
        "ok": ok,
        "timing": {
            "wall_s": wall_s,
            "ttft_s": 0.2,
            "prefill_tps": prefill_tps,
            "decode_tps": 40.0,
            "total_tps": 30.0,
        },
        "tokens": {
            "prompt": prompt_tokens,
            "output": 60,
            "cached_prompt": cached_prompt,
        },
        "resources": {"memory_mb": None, "gpu_memory_mb": None},
        "scoring": scoring,
        "raw": {
            "request_path": "raw/short.request.json",
            "response_path": "raw/short.response.json",
        },
    }
    if patch is not None:
        record["patch"] = patch
    if repo_task is not None:
        record["repo_task"] = repo_task
    if repetition is not None:
        record["repetition"] = repetition
    return record


def test_report_renders_comparable_medians_and_hardware(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(
        run_a,
        hardware={
            "hostname": "atlas.local",
            "chip": "Apple M5 Max",
            "hardware_model": "Mac17,7",
            "hardware_model_name": "MacBook Pro",
            "ram_mb": 65536,
            "os": "macOS-test",
            "gpus": [{"model": "Apple M5 Max"}],
        },
        rows=[
            _record("short", wall_s=1.0, cached_prompt=8, prefill_tps=90.0),
            _record("short", wall_s=3.0, cached_prompt=8, prefill_tps=110.0),
        ],
    )
    _write_run(
        run_b,
        hardware={"hostname": "studio", "chip": "Apple M4 Max"},
        rows=[_record("short", wall_s=2.0, cached_prompt=8, prefill_tps=120.0)],
    )

    output = render_report(load_report_runs([run_a, run_b]))

    assert "# benchpack report" in output
    assert "hostname=atlas.local; chip=Apple M5 Max; hardware_model=Mac17,7" in output
    assert "gpus=Apple M5 Max" in output
    assert (
        "| run-a | short | 2 | 2 | 2.000 | 0.200 | 100.00 | 40.00 | "
        "30.00 | 60 | 10 | 8 | 2/2 | comparable |"
    ) in output
    assert (
        "| run-b | short | 1 | 1 | 2.000 | 0.200 | 120.00 | 40.00 | "
        "30.00 | 60 | 10 | 8 | 1/1 | comparable |"
    ) in output


def test_report_uses_compare_cache_missing_behavior(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    row_a = _record("short")
    row_a["tokens"].pop("cached_prompt")
    _write_run(run_a, rows=[row_a])
    _write_run(run_b, rows=[_record("short", cached_prompt=8)])

    output = render_report(load_report_runs([run_a, run_b]))

    assert "WARNING: cache metadata incomplete for case `short`" in output
    assert (
        "| run-a | short | 1 | 1 | 1.000 | 0.200 | — | 40.00 | 30.00 | "
        "60 | 10 | — | 0/1 | cache-missing |"
    ) in output
    assert (
        "| run-b | short | 1 | 1 | 1.000 | 0.200 | — | 40.00 | 30.00 | "
        "60 | 10 | 8 | 1/1 | cache-missing |"
    ) in output


def test_report_tolerates_missing_hardware_json(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_run(run_a)

    output = render_report(load_report_runs([run_a]))

    assert "| run-a | runtime-sweep 0.1.0 | openai-chat | model |" in output
    assert "hardware.json missing" in output


def test_report_renders_user_supplied_runtime_metadata(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_run(
        run_a,
        metadata={
            "runtime": {
                "name": "llama-server",
                "version": "9010",
                "command": "llama-server --model <model>",
                "options": {"ctx_size": 4096},
            },
            "model": {
                "id": "qwen2.5-0.5b-instruct-q4_k_m",
                "quantization": "Q4_K_M",
                "sha256": "abc123",
            },
            "operating_conditions": {
                "power": "not captured",
                "thermal": "not captured",
                "background_load": "no intentional throttling setup",
            },
            "notes": "unit report note",
        },
    )

    output = render_report(load_report_runs([run_a]))

    assert "## User-Supplied Runtime Metadata" in output
    assert "name=llama-server" in output
    assert "ctx_size" in output
    assert "quantization=Q4_K_M" in output
    assert "thermal=not captured" in output
    assert "unit report note" in output


def test_report_renders_external_agent_model_call_summary(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_run(run_a)
    model_calls = run_a / "task" / "edit-repo" / "rep-001.model-calls.jsonl"
    model_calls.parent.mkdir(parents=True)
    model_calls.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema_version": 1,
                        "sequence": 1,
                        "model": "test-model",
                        "ok": True,
                        "adapter": "example-local-http",
                        "endpoint": "local-http",
                        "duration_s": 0.1,
                        "prompt_tokens": 3,
                        "output_tokens": 5,
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "sequence": 2,
                        "model": "test-model",
                        "ok": False,
                        "error": "short deterministic error",
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "sequence": 3,
                        "model": "test-model",
                        "ok": True,
                        "request": {"prompt": "not safe for summaries"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output = render_report(load_report_runs([run_a]))

    assert "## External-Agent Model Calls" in output
    assert (
        "| run-a | edit-repo | 1 | 3 | 2 | 1 | 1 | 1 | 1 | test-model | "
        "example-local-http | local-http | 0.100000 | 3 | 5 | — |"
    ) in output
    assert "not safe for summaries" not in output


def test_report_renders_repo_task_outcomes(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_run(
        run_a,
        pack_id="patch-from-failure-external-agent",
        rows=[
            _record(
                "fix-greeting",
                pack_id="patch-from-failure-external-agent",
                scoring={"mode": "verify-script", "passed": True},
                patch={"path": "patch/fix-greeting/rep-001.diff"},
                repo_task={"status": "passed", "verify_exit_code": 0},
                repetition=1,
            ),
            _record(
                "fix-dashboard-regressions",
                pack_id="patch-from-failure-external-agent",
                scoring={"mode": "verify-script", "passed": False},
                patch={"path": "patch/fix-dashboard-regressions/rep-001.diff"},
                repo_task={"status": "failed", "verify_exit_code": 1},
                repetition=1,
            ),
        ],
    )
    patch = run_a / "patch" / "fix-greeting" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff --git a/greeter.py b/greeter.py\n", encoding="utf-8")
    empty_patch = run_a / "patch" / "fix-dashboard-regressions" / "rep-001.diff"
    empty_patch.parent.mkdir(parents=True)
    empty_patch.write_text("", encoding="utf-8")

    output = render_report(load_report_runs([run_a]))

    assert "## Repo-Task Outcomes" in output
    assert (
        "| run-a | fix-greeting | 1 | passed | 0 | verify-script:pass | "
        "37 | passed |"
    ) in output
    assert (
        "| run-a | fix-dashboard-regressions | 1 | failed | 1 | "
        "verify-script:fail | 0 | failed-no-mutation |"
    ) in output


def test_report_tolerates_missing_run_metadata_json(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_run(run_a)

    output = render_report(load_report_runs([run_a]))

    assert "| run-a | run-metadata.json missing | — | — | — |" in output
    assert "## External-Agent Model Calls" not in output


def test_report_rejects_malformed_run_metadata_json(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_run(run_a)
    (run_a / "run-metadata.json").write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(ReportError, match="could not parse run metadata"):
        render_report(load_report_runs([run_a]))


def test_report_counts_scoring_pass_fail_and_unscored(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_run(
        run_a,
        rows=[
            _record("short", scoring={"mode": "contains", "passed": True}),
            _record("short", ok=False, scoring={"mode": "contains", "passed": False}),
            _record("short", scoring=None),
        ],
    )

    output = render_report(load_report_runs([run_a]))

    assert "| run-a | short | 3 | 2 | 1 | 1 | 1 |" in output


def test_report_warns_on_pack_version_mismatch(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, version="0.1.0")
    _write_run(run_b, version="0.2.0")

    output = render_report(load_report_runs([run_a, run_b]))

    assert "WARNING: compared records use different pack ids or versions" in output


def test_report_rejects_malformed_hardware_json(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_run(run_a)
    (run_a / "hardware.json").write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(ReportError, match="could not parse"):
        render_report(load_report_runs([run_a]))


def test_load_report_set_expands_relative_paths_from_manifest_dir(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest = manifest_dir / "qwen.toml"
    manifest.write_text(
        "\n".join(
            [
                "version = 1",
                "result_dirs = [",
                '  "../results/run-a",',
                '  "/tmp/absolute-run",',
                "]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert load_report_set(manifest) == [
        manifest_dir / "../results/run-a",
        Path("/tmp/absolute-run"),
    ]


def test_load_report_set_allows_omitted_version(tmp_path: Path) -> None:
    manifest = tmp_path / "qwen.toml"
    manifest.write_text('result_dirs = ["results/run-a"]\n', encoding="utf-8")

    assert load_report_set(manifest) == [tmp_path / "results/run-a"]


def test_load_report_set_rejects_malformed_toml(tmp_path: Path) -> None:
    manifest = tmp_path / "bad.toml"
    manifest.write_text("version = [\n", encoding="utf-8")

    with pytest.raises(ReportError, match="could not parse report set manifest"):
        load_report_set(manifest)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("version = 1\n", "requires result_dirs"),
        ('version = 1\nresult_dirs = "results/run-a"\n', "non-empty list"),
        ("version = 1\nresult_dirs = []\n", "must not be empty"),
        ("version = 1\nresult_dirs = [1]\n", "entries must be strings"),
        ('version = 1\nresult_dirs = [""]\n', "entries must not be empty"),
        ('version = "1"\nresult_dirs = ["results/run-a"]\n', "version must be"),
        ("version = 2\nresult_dirs = [\"results/run-a\"]\n", "version must be 1"),
    ],
)
def test_load_report_set_rejects_invalid_schema(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    manifest = tmp_path / "bad.toml"
    manifest.write_text(content, encoding="utf-8")

    with pytest.raises(ReportError, match=message):
        load_report_set(manifest)
