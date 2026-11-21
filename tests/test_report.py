"""Tests for read-only Markdown report rendering."""

from __future__ import annotations

import errno
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from benchpack import report
from benchpack.compare import ResultRun, load_result_run
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


@pytest.mark.parametrize("companion", ["hardware", "runtime"])
@pytest.mark.parametrize("via_alias", [False, True])
def test_report_refuses_companions_from_replaced_result_directory(
    tmp_path: Path, companion: str, via_alias: bool,
) -> None:
    source = tmp_path / "run"
    replacement = tmp_path / "replacement"
    _write_run(
        source, hardware={"hostname": "old-host"},
        metadata={"runtime": {"name": "old-runtime"}},
    )
    _write_run(
        replacement, hardware={"hostname": "new-host"},
        metadata={"runtime": {"name": "new-runtime"}},
    )
    if via_alias:
        alias = tmp_path / "alias"
        alias.symlink_to(source, target_is_directory=True)
        (run,) = load_report_runs([alias])
    else:
        run = load_result_run(source)

    if companion == "runtime":
        run = replace(run, hardware={"hostname": "old-host"})
    report = render_report([run])
    assert "old-host" in report and "old-runtime" in report

    if via_alias:
        alias.unlink()
        alias.symlink_to(replacement, target_is_directory=True)
    else:
        source.rename(tmp_path / "retired")
        replacement.rename(source)

    with pytest.raises(ReportError, match="result directory.*exchanged"):
        render_report([run])


def test_report_opens_companion_relative_to_verified_directory(tmp_path, monkeypatch):
    source, replacement = tmp_path / "run", tmp_path / "replacement"
    _write_run(source, hardware={"hostname": "old-host"})
    _write_run(replacement, hardware={"hostname": "new-host"})
    (run,) = load_report_runs([source])
    run = replace(run, run_metadata={"notes": "saved metadata"})
    original_open = os.open
    swapped = False

    def exchange_before_open(name, *args, **kwargs):
        nonlocal swapped
        if name == "hardware.json":
            source.rename(tmp_path / "retired")
            replacement.rename(source)
            swapped = True
        return original_open(name, *args, **kwargs)

    monkeypatch.setattr(os, "open", exchange_before_open)
    report = render_report([run])
    assert swapped
    assert "old-host" in report and "new-host" not in report


@pytest.mark.parametrize("sidecar", ["hardware.json", "run-metadata.json"])
def test_report_refuses_symlinked_sidecar(tmp_path: Path, sidecar: str) -> None:
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    target = tmp_path / "outside.json"
    target.write_text(json.dumps({"hostname": "outside-host"}) + "\n", encoding="utf-8")
    (run_dir / sidecar).symlink_to(target)

    with pytest.raises(ReportError, match="refusing symlinked sidecar"):
        render_report(load_report_runs([run_dir]))


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
                        "response_format": "json_object",
                        "token_budget_field": "max_tokens",
                        "finish_reason": "stop",
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
        "example-local-http | local-http | 0.100000 | 3 | 5 | — | "
        "json_object | max_tokens | stop |"
    ) in output
    assert "not safe for summaries" not in output


def test_report_renders_old_shape_model_call_labels_as_missing(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    _write_run(run_a)
    model_calls = run_a / "task" / "edit-repo" / "rep-001.model-calls.jsonl"
    model_calls.parent.mkdir(parents=True)
    model_calls.write_text(
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
        )
        + "\n",
        encoding="utf-8",
    )

    output = render_report(load_report_runs([run_a]))

    assert (
        "| run-a | edit-repo | 1 | 1 | 1 | 0 | 1 | 0 | 0 | test-model | "
        "example-local-http | local-http | 0.100000 | 3 | 5 | — | "
        "— | — | — |"
    ) in output


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

    assert "## Repo-Task Outcome Summary" in output
    assert "### Aggregate" in output
    assert "\n| 2 | 1 | 1 | 0 | 0 | 0 | 0 |\n" in output
    assert "### By Run" in output
    assert "| run-a | 2 | 1 | 1 | 0 | 0 | 0 | 0 |" in output
    assert "## Repo-Task Outcomes" in output
    assert (
        "| run-a | fix-greeting | 1 | passed | 0 | verify-script:pass | "
        "37 | passed |"
    ) in output
    assert (
        "| run-a | fix-dashboard-regressions | 1 | failed | 1 | "
        "verify-script:fail | 0 | failed-no-mutation |"
    ) in output


def test_report_aggregates_repo_task_outcomes_across_runs(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(
        run_a,
        pack_id="patch-from-failure-external-agent",
        rows=[
            _record(
                "fix-greeting",
                pack_id="patch-from-failure-external-agent",
                scoring={"mode": "verify-script", "passed": False},
                patch={"path": "patch/fix-greeting/rep-001.diff"},
                repo_task={"status": "failed", "verify_exit_code": 1},
                repetition=1,
            )
        ],
    )
    _write_run(
        run_b,
        pack_id="python-regression-fix-external-agent",
        rows=[
            _record(
                "fix-task-summary",
                pack_id="python-regression-fix-external-agent",
                scoring={"mode": "verify-script", "passed": False},
                patch={"path": "patch/fix-task-summary/rep-001.diff"},
                repo_task={"status": "failed", "verify_exit_code": 1},
                repetition=1,
            )
        ],
    )
    empty_patch = run_a / "patch" / "fix-greeting" / "rep-001.diff"
    empty_patch.parent.mkdir(parents=True)
    empty_patch.write_text("", encoding="utf-8")
    changed_patch = run_b / "patch" / "fix-task-summary" / "rep-001.diff"
    changed_patch.parent.mkdir(parents=True)
    changed_patch.write_text(
        "diff --git a/task_summary.py b/task_summary.py\n",
        encoding="utf-8",
    )

    output = render_report(load_report_runs([run_a, run_b]))

    assert "| 2 | 0 | 1 | 1 | 0 | 0 | 0 |" in output
    assert "| run-a | 1 | 0 | 1 | 0 | 0 | 0 | 0 |" in output
    assert "| run-b | 1 | 0 | 0 | 1 | 0 | 0 | 0 |" in output


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


def test_report_distinguishes_missing_single_and_mixed_pack_identity(tmp_path: Path) -> None:
    empty = ResultRun(
        path=tmp_path / "empty", label="empty", records=[],
        run_metadata={"notes": "metadata only"},
    )
    single = tmp_path / "single"
    mixed = tmp_path / "mixed"
    _write_run(single)
    _write_run(mixed, rows=[_record("short", pack_id="smoke-chat"), _record("short")])

    output = render_report([empty, *load_report_runs([single, mixed])])

    assert "| empty | — | — | — | — | hardware.json missing |" in output
    assert "| single | runtime-sweep 0.1.0 | openai-chat |" in output
    assert "| mixed | mixed: runtime-sweep 0.1.0, smoke-chat 0.1.0 | openai-chat |" in output


@pytest.mark.parametrize("grows_after_stat", [False, True], ids=["oversized", "growing"])
def test_report_bounds_fallback_sidecar_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grows_after_stat: bool,
) -> None:
    source = tmp_path / "run"
    _write_run(source, hardware={"hostname": "synthetic"})
    path = source / "hardware.json"
    limit = path.stat().st_size
    monkeypatch.setattr(report, "MAX_RESULT_SIDECAR_BYTES", limit, raising=False)
    (run,) = load_report_runs([source])
    assert "hostname=synthetic" in render_report([run])

    identity = path.stat().st_ino
    target_fd = None
    stat_calls = 0
    read_sizes = []
    real_stat = os.fstat
    real_read = os.read

    def append_bytes():
        with path.open("ab") as stream:
            stream.write(b" " * limit)

    if not grows_after_stat:
        append_bytes()

    def growing_stat(fd):
        nonlocal stat_calls, target_fd
        info = real_stat(fd)
        if info.st_ino == identity:
            target_fd = fd
            stat_calls += 1
            if grows_after_stat and stat_calls == 2:
                append_bytes()
        return info

    def tracked_read(fd, size):
        if fd == target_fd:
            read_sizes.append(size)
        return real_read(fd, size)

    monkeypatch.setattr(os, "fstat", growing_stat)
    monkeypatch.setattr(os, "read", tracked_read)
    with pytest.raises(ReportError, match=r"sidecar byte limit exceeded: .*hardware\.json"):
        render_report([run])
    assert read_sizes == ([limit + 1] if grows_after_stat else [])


def test_report_rejects_malformed_hardware_json(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_run(run_a)
    (run_a / "hardware.json").write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(ReportError, match="could not parse"):
        render_report(load_report_runs([run_a]))


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        (b'{"chip":"\xff"}', r"hardware\.json.*not valid UTF-8"),
        (
            b'{"gpu":' + b"[" * 100_000 + b"0" + b"]" * 100_000 + b"}",
            r"hardware\.json.*nesting limit",
        ),
        (b'{"ram_mb":' + b"9" * 5000 + b"}", r"hardware\.json.*invalid JSON domain"),
    ],
    ids=["invalid-utf8", "nesting-limit", "integer-limit"],
)
def test_report_normalizes_hardware_decode_errors(
    tmp_path: Path, contents: bytes, message: str,
) -> None:
    run = tmp_path / "run"
    _write_run(run)
    (run / "hardware.json").write_bytes(contents)

    with pytest.raises(ReportError, match=message):
        render_report(load_report_runs([run]))


def test_report_normalizes_hardware_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    _write_run(run, hardware={"hostname": "synthetic"})
    original_open = os.open

    def fail_hardware_open(name, *args, **kwargs):
        if name == "hardware.json":
            raise OSError(errno.EIO, "Input/output error", name)
        return original_open(name, *args, **kwargs)

    monkeypatch.setattr(os, "open", fail_hardware_open)

    with pytest.raises(ReportError, match=r"could not read .*hardware\.json: Input/output error"):
        render_report(load_report_runs([run]))


@pytest.mark.parametrize(
    "hardware",
    [
        '{"hostname":"first","hostname":"second"}',
        r'{"gpus":[{"model":"first","m\u006fdel":"second"}]}',
    ],
    ids=["top-level", "nested-decoded-name"],
)
def test_report_rejects_duplicate_hardware_json_members(tmp_path: Path, hardware: str) -> None:
    run = tmp_path / "run"
    _write_run(run)
    (run / "hardware.json").write_text(hardware, encoding="utf-8")

    with pytest.raises(ReportError, match=r"could not parse .*hardware\.json: invalid JSON domain"):
        render_report(load_report_runs([run]))


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
