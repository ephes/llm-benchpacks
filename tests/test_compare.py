"""Tests for read-only comparison helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchpack.compare import (
    CompareError,
    _prefill_parity_statuses,
    load_result_run,
    render_comparison,
    summarize_runs,
)


_UNSET = object()


def _write_run(
    path: Path,
    *,
    pack_id: str = "runtime-sweep",
    version: str = "0.1.0",
    rows: list[dict] | None = None,
) -> None:
    path.mkdir(parents=True)
    records = rows or [
        _record("short", pack_id=pack_id, version=version, wall_s=1.0),
        _record("short", pack_id=pack_id, version=version, wall_s=3.0),
    ]
    (path / "run.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records)
    )


def _prefill_statuses(*run_dirs: Path) -> dict[str, str]:
    return _prefill_parity_statuses(
        summarize_runs([load_result_run(run_dir) for run_dir in run_dirs])
    )


def _record(
    case: str,
    *,
    pack_id: str = "runtime-sweep",
    version: str = "0.1.0",
    ok: bool = True,
    wall_s: float | None = 1.0,
    ttft_s: float | None = 0.2,
    decode_tps: float | None = 40.0,
    total_tps: float | None = 30.0,
    prompt_tokens: object = 10,
    output_tokens: int | None = 60,
    cached_prompt: object = _UNSET,
) -> dict:
    tokens = {"output": output_tokens}
    if prompt_tokens is not _UNSET:
        tokens["prompt"] = prompt_tokens
    if cached_prompt is not _UNSET:
        tokens["cached_prompt"] = cached_prompt
    return {
        "pack": {"id": pack_id, "version": version},
        "case": case,
        "adapter": "openai-chat",
        "endpoint": "http://example.test/v1/chat/completions",
        "model": "model",
        "ok": ok,
        "timing": {
            "wall_s": wall_s,
            "ttft_s": ttft_s,
            "prefill_tps": 100.0,
            "decode_tps": decode_tps,
            "total_tps": total_tps,
        },
        "tokens": tokens,
        "resources": {"memory_mb": None, "gpu_memory_mb": None},
        "scoring": None,
        "raw": {
            "request_path": "raw/short.request.json",
            "response_path": "raw/short.response.json",
        },
    }


def test_load_result_run_reads_jsonl_from_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    _write_run(run_dir)

    run = load_result_run(run_dir)

    assert run.label == "run-a"
    assert run.path == run_dir
    assert len(run.records) == 2


def test_load_result_run_rejects_missing_empty_and_malformed_inputs(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    missing.mkdir()
    with pytest.raises(CompareError, match="missing run.jsonl"):
        load_result_run(missing)

    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "run.jsonl").write_text("")
    with pytest.raises(CompareError, match="has no records"):
        load_result_run(empty)

    whitespace = tmp_path / "whitespace"
    whitespace.mkdir()
    (whitespace / "run.jsonl").write_text("\n  \n")
    with pytest.raises(CompareError, match="has no records"):
        load_result_run(whitespace)

    malformed = tmp_path / "malformed"
    malformed.mkdir()
    (malformed / "run.jsonl").write_text("{bad json}\n")
    with pytest.raises(CompareError, match="could not parse"):
        load_result_run(malformed)


def test_summarize_runs_groups_by_case_and_ignores_null_metrics(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(
        run_a,
        rows=[
            _record("short", wall_s=1.0, ttft_s=None, output_tokens=None),
            _record("short", wall_s=3.0, ttft_s=0.4, output_tokens=80),
            _record("long", ok=False, wall_s=5.0, output_tokens=120),
        ],
    )
    _write_run(run_b, rows=[_record("short", wall_s=2.0, output_tokens=70)])

    summaries = summarize_runs([load_result_run(run_a), load_result_run(run_b)])

    assert [(item.run_label, item.case, item.rows, item.ok) for item in summaries] == [
        ("run-a", "short", 2, 2),
        ("run-b", "short", 1, 1),
        ("run-a", "long", 1, 0),
        ("run-b", "long", 0, 0),
    ]
    assert summaries[0].wall_s == 2.0
    assert summaries[0].ttft_s == 0.4
    assert summaries[0].output_tokens == 80.0
    assert summaries[0].prompt_tokens == 10.0
    assert summaries[0].prompt_rows == 2
    assert summaries[3].wall_s is None
    assert summaries[3].prompt_tokens is None
    assert summaries[3].prompt_rows == 0
    assert summaries[0].cached_prompt_tokens is None
    assert summaries[0].cache_rows == 0


def test_summarize_runs_reports_prompt_token_median(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_run(
        run_a,
        rows=[
            _record("short", prompt_tokens=8),
            _record("short", prompt_tokens=10),
            _record("short", prompt_tokens=12),
        ],
    )

    summaries = summarize_runs([load_result_run(run_a)])

    assert summaries[0].prompt_tokens == 10.0
    assert summaries[0].prompt_rows == 3


def test_summarize_runs_handles_old_rows_without_prompt_token_field(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    rows = [_record("short", prompt_tokens=_UNSET), _record("short")]
    _write_run(run_a, rows=rows)

    summaries = summarize_runs([load_result_run(run_a)])

    assert summaries[0].prompt_tokens == 10.0
    assert summaries[0].prompt_rows == 1


def test_summarize_runs_ignores_invalid_prompt_token_values(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    rows = [
        _record("short", prompt_tokens=float("nan")),
        _record("short", prompt_tokens=float("inf")),
        _record("short", prompt_tokens=float("-inf")),
        _record("short", prompt_tokens=None),
        _record("short", prompt_tokens=True),
        _record("short", prompt_tokens="10"),
        _record("short", prompt_tokens=6),
        _record("short", prompt_tokens=8.0),
        _record("short"),
        _record("short"),
    ]
    rows[-2]["tokens"] = None
    rows[-1].pop("tokens")
    _write_run(run_a, rows=rows)

    summaries = summarize_runs([load_result_run(run_a)])

    assert summaries[0].prompt_tokens == 7.0
    assert summaries[0].prompt_rows == 2


def test_summarize_runs_reports_cached_prompt_median_and_coverage(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    _write_run(
        run_a,
        rows=[
            _record("short", cached_prompt=8),
            _record("short", cached_prompt=10),
            _record("short"),
        ],
    )

    summaries = summarize_runs([load_result_run(run_a)])

    assert summaries[0].cached_prompt_tokens == 9.0
    assert summaries[0].cache_rows == 2


def test_summarize_runs_ignores_invalid_cached_prompt_values(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    rows = [
        _record("short", cached_prompt=float("nan")),
        _record("short", cached_prompt=float("inf")),
        _record("short", cached_prompt=float("-inf")),
        _record("short", cached_prompt=None),
        _record("short", cached_prompt=True),
        _record("short", cached_prompt="10"),
        _record("short", cached_prompt=6),
        _record("short", cached_prompt=8.0),
        _record("short"),
        _record("short"),
    ]
    rows[-2]["tokens"] = None
    rows[-1].pop("tokens")
    _write_run(run_a, rows=rows)

    summaries = summarize_runs([load_result_run(run_a)])

    assert summaries[0].cached_prompt_tokens == 7.0
    assert summaries[0].cache_rows == 2


def test_compare_handles_old_rows_without_cached_prompt_field(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, rows=[_record("short")])
    _write_run(run_b, rows=[_record("short", wall_s=2.0)])

    output = render_comparison([load_result_run(run_a), load_result_run(run_b)])

    assert (
        "| run-a | short | 1 | 1 | 1.000 | 0.200 | 40.00 | 30.00 | "
        "60 | 10 | — | 0/1 | cache-missing |"
        in output
    )
    assert (
        "| run-b | short | 1 | 1 | 2.000 | 0.200 | 40.00 | 30.00 | "
        "60 | 10 | — | 0/1 | cache-missing |"
        in output
    )
    assert "WARNING: cache metadata incomplete for case `short`" in output


def test_prefill_parity_status_comparable_when_prompt_and_cache_match(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(
        run_a,
        rows=[
            _record("short", prompt_tokens=10, cached_prompt=8),
            _record("short", prompt_tokens=10, cached_prompt=8),
        ],
    )
    _write_run(run_b, rows=[_record("short", prompt_tokens=10, cached_prompt=8)])

    output = render_comparison([load_result_run(run_a), load_result_run(run_b)])

    assert _prefill_statuses(run_a, run_b) == {"short": "comparable"}
    assert "prefill parity" in output
    assert (
        "| run-a | short | 2 | 2 | 1.000 | 0.200 | 40.00 | 30.00 | "
        "60 | 10 | 8 | 2/2 | comparable |"
    ) in output
    assert (
        "| run-b | short | 1 | 1 | 1.000 | 0.200 | 40.00 | 30.00 | "
        "60 | 10 | 8 | 1/1 | comparable |"
    ) in output


def test_prefill_parity_status_missing_case_when_run_lacks_case(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, rows=[_record("short", cached_prompt=8)])
    _write_run(run_b, rows=[_record("long", cached_prompt=8)])

    assert _prefill_statuses(run_a, run_b) == {
        "short": "missing-case",
        "long": "missing-case",
    }


def test_prefill_parity_status_prompt_missing_when_prompt_coverage_incomplete(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, rows=[_record("short", prompt_tokens=_UNSET, cached_prompt=8)])
    _write_run(run_b, rows=[_record("short", prompt_tokens=10, cached_prompt=8)])

    assert _prefill_statuses(run_a, run_b) == {"short": "prompt-missing"}


def test_prefill_parity_status_prompt_diff_when_complete_prompt_medians_differ(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, rows=[_record("short", prompt_tokens=10, cached_prompt=8)])
    _write_run(run_b, rows=[_record("short", prompt_tokens=12, cached_prompt=8)])

    assert _prefill_statuses(run_a, run_b) == {"short": "prompt-diff"}


def test_prefill_parity_status_cache_missing_when_prompt_parity_holds(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, rows=[_record("short", prompt_tokens=10)])
    _write_run(run_b, rows=[_record("short", prompt_tokens=10, cached_prompt=8)])

    assert _prefill_statuses(run_a, run_b) == {"short": "cache-missing"}


def test_prefill_parity_status_cache_diff_when_complete_cached_medians_differ(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, rows=[_record("short", prompt_tokens=10, cached_prompt=8)])
    _write_run(run_b, rows=[_record("short", prompt_tokens=10, cached_prompt=10)])

    assert _prefill_statuses(run_a, run_b) == {"short": "cache-diff"}


def test_prefill_parity_status_priority_keeps_prompt_issues_before_cache(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    run_c = tmp_path / "run-c"
    _write_run(
        run_a,
        rows=[
            _record("short", prompt_tokens=_UNSET),
            _record("medium", prompt_tokens=10),
            _record("long", prompt_tokens=10),
        ],
    )
    _write_run(
        run_b,
        rows=[
            _record("short", prompt_tokens=12, cached_prompt=10),
            _record("medium", prompt_tokens=12),
            _record("missing", prompt_tokens=_UNSET),
        ],
    )
    _write_run(
        run_c,
        rows=[
            _record("short", prompt_tokens=12, cached_prompt=12),
            _record("medium", prompt_tokens=12, cached_prompt=12),
            _record("long", prompt_tokens=_UNSET),
        ],
    )

    assert _prefill_statuses(run_a, run_b, run_c) == {
        "short": "prompt-missing",
        "medium": "prompt-diff",
        "long": "missing-case",
        "missing": "missing-case",
    }


def test_render_comparison_shows_partial_cache_coverage(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(
        run_a,
        rows=[
            _record("short", cached_prompt=8),
            _record("short", cached_prompt=10),
            _record("short"),
        ],
    )
    _write_run(run_b, rows=[_record("short", cached_prompt=9)])

    output = render_comparison([load_result_run(run_a), load_result_run(run_b)])

    assert (
        "| run-a | short | 3 | 3 | 1.000 | 0.200 | 40.00 | 30.00 | 60 | "
        "10 | 9 | 2/3 | cache-missing |"
    ) in output
    assert (
        "| run-b | short | 1 | 1 | 1.000 | 0.200 | 40.00 | 30.00 | 60 | "
        "10 | 9 | 1/1 | cache-missing |"
    ) in output
    assert "WARNING: cache metadata incomplete for case `short`" in output


def test_render_comparison_shows_prompt_token_median(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, rows=[_record("short", prompt_tokens=10)])
    _write_run(run_b, rows=[_record("short", prompt_tokens=12)])

    output = render_comparison([load_result_run(run_a), load_result_run(run_b)])

    assert "prompt_tokens med" in output
    assert (
        "| run-a | short | 1 | 1 | 1.000 | 0.200 | 40.00 | 30.00 | 60 | "
        "10 | — | 0/1 | prompt-diff |"
    ) in output
    assert (
        "| run-b | short | 1 | 1 | 1.000 | 0.200 | 40.00 | 30.00 | 60 | "
        "12 | — | 0/1 | prompt-diff |"
    ) in output


def test_render_comparison_warns_on_differing_prompt_token_medians(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    run_c = tmp_path / "run-c"
    _write_run(run_a, rows=[_record("short", prompt_tokens=10, cached_prompt=8)])
    _write_run(run_b, rows=[_record("short", prompt_tokens=10, cached_prompt=8)])
    _write_run(run_c, rows=[_record("short", prompt_tokens=12, cached_prompt=8)])

    output = render_comparison(
        [load_result_run(run_a), load_result_run(run_b), load_result_run(run_c)]
    )

    assert (
        "WARNING: prompt-token medians differ for case `short`; cache parity is "
        "not comparable across different prompts."
    ) in output
    assert "cached prompt-token medians differ" not in output
    assert "cache metadata incomplete" not in output


def test_render_comparison_suppresses_prompt_mismatch_with_partial_prompt_coverage(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(
        run_a,
        rows=[
            _record("short", prompt_tokens=10, cached_prompt=8),
            _record("short", prompt_tokens=_UNSET, cached_prompt=8),
        ],
    )
    _write_run(
        run_b,
        rows=[
            _record("short", prompt_tokens=12, cached_prompt=8),
            _record("short", prompt_tokens=12, cached_prompt=8),
        ],
    )

    output = render_comparison([load_result_run(run_a), load_result_run(run_b)])

    assert (
        "| run-a | short | 2 | 2 | 1.000 | 0.200 | 40.00 | 30.00 | 60 | "
        "10 | 8 | 2/2 | prompt-missing |"
    ) in output
    assert "prompt-token medians differ" not in output
    assert "cache metadata incomplete" not in output


def test_render_comparison_suppresses_prompt_mismatch_with_missing_prompt_median(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(
        run_a,
        rows=[
            _record("short", prompt_tokens=None, cached_prompt=8),
            _record("short", prompt_tokens=True, cached_prompt=8),
        ],
    )
    _write_run(
        run_b,
        rows=[
            _record("short", prompt_tokens=12, cached_prompt=8),
            _record("short", prompt_tokens=12, cached_prompt=8),
        ],
    )

    output = render_comparison([load_result_run(run_a), load_result_run(run_b)])

    assert (
        "| run-a | short | 2 | 2 | 1.000 | 0.200 | 40.00 | 30.00 | 60 | "
        "— | 8 | 2/2 | prompt-missing |"
    ) in output
    assert "prompt-token medians differ" not in output
    assert "cache metadata incomplete" not in output


def test_render_comparison_keeps_prompt_then_cached_warning_order(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, rows=[_record("short", prompt_tokens=10, cached_prompt=8)])
    _write_run(run_b, rows=[_record("short", prompt_tokens=12, cached_prompt=10)])

    output = render_comparison([load_result_run(run_a), load_result_run(run_b)])

    assert output.index("prompt-token medians differ") < output.index(
        "cached prompt-token medians differ"
    )


def test_render_comparison_warns_on_differing_complete_cached_prompt_medians(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, rows=[_record("short", cached_prompt=8)])
    _write_run(run_b, rows=[_record("short", cached_prompt=10)])

    output = render_comparison([load_result_run(run_a), load_result_run(run_b)])

    assert (
        "WARNING: cached prompt-token medians differ for case `short`; "
        "do not compare prefill speed."
    ) in output
    assert "cache metadata incomplete" not in output


def test_render_comparison_suppresses_prompt_and_cache_mismatch_for_missing_case(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, rows=[_record("short", prompt_tokens=10, cached_prompt=8)])
    _write_run(run_b, rows=[_record("long", prompt_tokens=12, cached_prompt=10)])

    output = render_comparison([load_result_run(run_a), load_result_run(run_b)])

    assert (
        "| run-b | short | 0 | 0 | — | — | — | — | — | — | — | 0/0 | "
        "missing-case |"
    ) in output
    assert (
        "| run-a | long | 0 | 0 | — | — | — | — | — | — | — | 0/0 | "
        "missing-case |"
    ) in output
    assert "prompt-token medians differ" not in output
    assert "cached prompt-token medians differ" not in output


def test_render_comparison_warns_on_pack_version_mismatch(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, version="0.1.0")
    _write_run(run_b, version="0.2.0")

    output = render_comparison([load_result_run(run_a), load_result_run(run_b)])

    assert "WARNING: compared records use different pack ids or versions" in output
    assert "prefill_tps` is intentionally omitted" in output
    assert "tokens.cached_prompt" in output
    assert (
        "| run | case | rows | ok | wall_s med | ttft_s med | decode_tps med | "
        "total_tps med | output_tokens med | prompt_tokens med | "
        "cached_prompt med | cache rows | prefill parity |"
    ) in output


def test_render_comparison_shows_single_pack_line_and_separate_note(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a)
    _write_run(run_b)

    output = render_comparison([load_result_run(run_a), load_result_run(run_b)])

    assert "Pack: `runtime-sweep` version `0.1.0`\n\nNote:" in output


def test_render_comparison_disambiguates_duplicate_basenames(tmp_path: Path) -> None:
    first = tmp_path / "first" / "run-x"
    second = tmp_path / "second" / "run-x"
    _write_run(first)
    _write_run(second)

    output = render_comparison([load_result_run(first), load_result_run(second)])

    assert "`first/run-x`:" in output
    assert "`second/run-x`:" in output
    assert "| first/run-x | short |" in output
    assert "| second/run-x | short |" in output


def test_render_comparison_pluralizes_single_input_row(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_run(run_a, rows=[_record("short")])
    _write_run(run_b)

    output = render_comparison([load_result_run(run_a), load_result_run(run_b)])

    assert "`run-a`: `" in output
    assert "(1 row)" in output
