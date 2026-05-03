"""Tests for read-only Markdown report rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchpack.report import ReportError, load_report_runs, render_report


def _write_run(
    path: Path,
    *,
    pack_id: str = "runtime-sweep",
    version: str = "0.1.0",
    hardware: dict | None = None,
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
) -> dict:
    return {
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
