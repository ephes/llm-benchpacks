"""Tests for safe external-agent model-call telemetry summaries."""

from __future__ import annotations

import json
import math
from pathlib import Path

from benchpack.external_agent_model_calls import summarize_model_call_logs


def test_summarize_model_call_logs_counts_only_safe_fields(tmp_path: Path) -> None:
    path = tmp_path / "task" / "edit-repo" / "rep-001.model-calls.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
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
                        "response_format": "json_schema",
                        "token_budget_field": "max_completion_tokens",
                        "finish_reason": "stop",
                        "duration_s": 0.125,
                        "prompt_tokens": 3,
                        "output_tokens": 5,
                        "cached_prompt_tokens": 1,
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
                        "prompt": "must not be accepted or reported",
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "sequence": 4,
                        "model": "test-model",
                        "ok": True,
                        "endpoint": "http://token@example.test/v1?key=secret",
                    }
                ),
                "{bad json}",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summaries = summarize_model_call_logs(tmp_path)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.case == "edit-repo"
    assert summary.repetition == 1
    assert summary.relative_path == "task/edit-repo/rep-001.model-calls.jsonl"
    assert summary.calls == 5
    assert summary.valid == 2
    assert summary.invalid == 3
    assert summary.ok == 1
    assert summary.failed == 1
    assert summary.error_count == 1
    assert summary.models == ("test-model",)
    assert summary.adapters == ("example-local-http",)
    assert summary.endpoints == ("local-http",)
    assert summary.response_formats == ("json_schema",)
    assert summary.token_budget_fields == ("max_completion_tokens",)
    assert summary.finish_reasons == ("stop",)
    assert summary.duration_s == 0.125
    assert summary.prompt_tokens == 3
    assert summary.output_tokens == 5
    assert summary.cached_prompt_tokens == 1


def test_summarize_model_call_logs_rejects_unsafe_scalar_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "task" / "edit-repo" / "rep-001.model-calls.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema_version": 2,
                        "sequence": 1,
                        "model": "test-model",
                        "ok": True,
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "sequence": 2,
                        "model": "bad\u2028model",
                        "ok": True,
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "sequence": 3,
                        "model": "x" * 201,
                        "ok": True,
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "sequence": 4,
                        "model": "test-model",
                        "ok": True,
                        "prompt_tokens": -1,
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "sequence": 5,
                        "model": "test-model",
                        "ok": True,
                        "output_tokens": True,
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "sequence": 6,
                        "model": "test-model",
                        "ok": True,
                        "duration_s": math.inf,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = summarize_model_call_logs(tmp_path)[0]

    assert summary.calls == 6
    assert summary.valid == 0
    assert summary.invalid == 6


def test_summarize_model_call_logs_handles_empty_and_wide_repetition_logs(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "task" / "empty-case" / "rep-001.model-calls.jsonl"
    empty.parent.mkdir(parents=True)
    empty.write_text("", encoding="utf-8")
    wide = tmp_path / "task" / "bulk-case" / "rep-1000.model-calls.jsonl"
    wide.parent.mkdir(parents=True)
    wide.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sequence": 1,
                "model": "bulk-model",
                "ok": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summaries = summarize_model_call_logs(tmp_path)

    assert [(summary.case, summary.repetition) for summary in summaries] == [
        ("bulk-case", 1000),
        ("empty-case", 1),
    ]
    assert summaries[0].valid == 1
    assert summaries[0].response_formats == ()
    assert summaries[0].token_budget_fields == ()
    assert summaries[0].finish_reasons == ()
    assert summaries[1].calls == 0
