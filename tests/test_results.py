"""Tests for benchpack.results (the reporter)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchpack.adapters import AdapterResult, RawPaths, Timing, Tokens
from benchpack.packs import Case, Pack, Scoring
from benchpack.results import RunReporter


def make_pack(tmp_path: Path, scoring: Scoring | None = None) -> Pack:
    return Pack(
        id="smoke-chat",
        version="0.1.0",
        description="test",
        defaults={},
        cases=[
            Case(
                id="capital",
                kind="chat",
                prompt="What is the capital of France?",
                scoring=None,
                raw={},
            )
        ],
        scoring=scoring,
        path=tmp_path / "pack",
    )


def make_adapter_result(out_dir: Path, output_text: str = "Paris.") -> AdapterResult:
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    req = raw_dir / "capital.request.json"
    resp = raw_dir / "capital.response.json"
    req.write_text("{}")
    resp.write_text("{}")
    return AdapterResult(
        adapter="ollama-generate",
        endpoint="http://localhost:11434/api/generate",
        model="qwen3-coder",
        ok=True,
        timing=Timing(wall_s=4.0, ttft_s=0.5, prefill_tps=950.0, decode_tps=42.0),
        tokens=Tokens(prompt=32768, output=192),
        raw=RawPaths(request_path=str(req), response_path=str(resp)),
        output_text=output_text,
        backend={"prompt_eval_count": 32768},
    )


def make_adapter_result_for_paths(
    request_path: Path,
    response_path: Path,
    output_text: str = "Paris.",
) -> AdapterResult:
    request_path.write_text("{}")
    response_path.write_text("{}")
    return AdapterResult(
        adapter="ollama-generate",
        endpoint="http://localhost:11434/api/generate",
        model="qwen3-coder",
        ok=True,
        timing=Timing(wall_s=4.0),
        tokens=Tokens(prompt=7, output=2),
        raw=RawPaths(
            request_path=str(request_path),
            response_path=str(response_path),
        ),
        output_text=output_text,
    )


def test_record_matches_documented_combined_shape(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path, scoring=Scoring(mode="contains", expected="Paris"))
    reporter = RunReporter(out, pack)
    ar = make_adapter_result(out)

    record = reporter.record(
        pack.cases[0],
        ar,
        sample={"memory_mb": 6234, "gpu_memory_mb": 14820},
    )

    # All fields from docs/architecture.md "Combined record" must be present.
    assert record["pack"] == {"id": "smoke-chat", "version": "0.1.0"}
    assert record["case"] == "capital"
    assert record["adapter"] == "ollama-generate"
    assert record["endpoint"] == "http://localhost:11434/api/generate"
    assert record["model"] == "qwen3-coder"
    assert record["ok"] is True

    timing = record["timing"]
    assert timing["wall_s"] == 4.0
    assert timing["ttft_s"] == 0.5
    assert timing["prefill_tps"] == 950.0
    assert timing["decode_tps"] == 42.0
    assert timing["total_tps"] == 48.0  # 192 / 4.0

    assert record["tokens"] == {
        "prompt": 32768,
        "output": 192,
        "cached_prompt": None,
    }
    assert record["resources"] == {"memory_mb": 6234, "gpu_memory_mb": 14820}
    assert record["scoring"] == {"mode": "contains", "passed": True}

    # raw paths are relative to the run dir per the spec example.
    assert record["raw"]["request_path"] == "raw/capital.request.json"
    assert record["raw"]["response_path"] == "raw/capital.response.json"

    # backend table from the adapter is preserved verbatim.
    assert record["backend"] == {"prompt_eval_count": 32768}


def test_record_appends_to_run_jsonl(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)
    reporter.record(
        pack.cases[0],
        make_adapter_result(out),
        sample={"memory_mb": None, "gpu_memory_mb": None},
    )

    lines = (out / "run.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["case"] == "capital"
    assert record["tokens"]["cached_prompt"] is None


def test_record_writes_cached_prompt_tokens_to_run_jsonl(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)
    adapter_result = make_adapter_result(out)
    adapter_result.tokens = Tokens(prompt=104, output=32, cached_prompt=103)

    reporter.record(
        pack.cases[0],
        adapter_result,
        sample={"memory_mb": None, "gpu_memory_mb": None},
    )

    record = json.loads((out / "run.jsonl").read_text())
    assert record["tokens"] == {
        "prompt": 104,
        "output": 32,
        "cached_prompt": 103,
    }


def test_record_uses_per_case_scoring_override(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = Pack(
        id="mix",
        version="0.1.0",
        description="",
        defaults={},
        cases=[
            Case(
                id="capital",
                kind="chat",
                prompt="x",
                scoring=Scoring(mode="contains", expected="London"),
                raw={},
            )
        ],
        scoring=Scoring(mode="contains", expected="Paris"),
        path=tmp_path / "pack",
    )
    reporter = RunReporter(out, pack)
    record = reporter.record(
        pack.cases[0],
        make_adapter_result(out, output_text="Paris."),
        sample={"memory_mb": None, "gpu_memory_mb": None},
    )
    # Per-case override wins; "London" not in "Paris." → passed False.
    assert record["scoring"] == {"mode": "contains", "passed": False}


def test_record_scoring_null_when_pack_has_none(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)  # no scoring at all
    reporter = RunReporter(out, pack)
    record = reporter.record(
        pack.cases[0],
        make_adapter_result(out),
        sample={"memory_mb": None, "gpu_memory_mb": None},
    )
    assert record["scoring"] is None


def test_record_can_include_verifier_fields_and_scoring_override(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    pack = make_pack(
        tmp_path,
        scoring=Scoring(mode="verify-script", script="verify/check.py"),
    )
    reporter = RunReporter(out, pack)

    record = reporter.record(
        pack.cases[0],
        make_adapter_result(out, output_text="not prompt-scored"),
        sample={"memory_mb": None, "gpu_memory_mb": None},
        verify={
            "path": "verify/capital/rep-001.json",
            "stdout_path": "verify/capital/rep-001.stdout.log",
            "stderr_path": "verify/capital/rep-001.stderr.log",
        },
        repo_task={"status": "passed", "verify_exit_code": 0},
        scoring_override={"mode": "verify-script", "passed": True},
    )

    assert record["verify"] == {
        "path": "verify/capital/rep-001.json",
        "stdout_path": "verify/capital/rep-001.stdout.log",
        "stderr_path": "verify/capital/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}


def test_total_tps_null_when_inputs_missing(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)
    raw_dir = out / "raw"  # already created by reporter
    req = raw_dir / "capital.request.json"
    resp = raw_dir / "capital.response.json"
    req.write_text("{}")
    resp.write_text("{}")
    ar = AdapterResult(
        adapter="openai-chat",
        endpoint="http://example.test/v1/chat/completions",
        model="m",
        ok=True,
        timing=Timing(wall_s=2.0),
        tokens=Tokens(prompt=None, output=None),
        raw=RawPaths(request_path=str(req), response_path=str(resp)),
        output_text="",
    )
    record = reporter.record(
        pack.cases[0],
        ar,
        sample={"memory_mb": None, "gpu_memory_mb": None},
    )
    assert record["timing"]["total_tps"] is None


def test_case_paths_inside_raw_subdir(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)
    req, resp = reporter.case_paths(pack.cases[0])
    assert req == out / "raw" / "capital.request.json"
    assert resp == out / "raw" / "capital.response.json"
    assert req.parent.exists()


def test_repetition_and_warmup_paths_use_stable_suffixes(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)

    req, resp = reporter.measured_paths(pack.cases[0], 1, 1)
    assert req == out / "raw" / "capital.request.json"
    assert resp == out / "raw" / "capital.response.json"

    req, resp = reporter.measured_paths(pack.cases[0], 2, 3)
    assert req == out / "raw" / "capital.rep-002.request.json"
    assert resp == out / "raw" / "capital.rep-002.response.json"

    req, resp = reporter.warmup_paths(pack.cases[0], 1)
    assert req == out / "raw" / "capital.warmup-001.request.json"
    assert resp == out / "raw" / "capital.warmup-001.response.json"


@pytest.mark.parametrize("repetition", [0, -1, True, "1"])
def test_measured_paths_rejects_invalid_repetition(
    tmp_path: Path,
    repetition: object,
) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)

    with pytest.raises(ValueError, match="repetition"):
        reporter.measured_paths(
            pack.cases[0],
            repetition,  # type: ignore[arg-type]
            1,
        )


@pytest.mark.parametrize("total_repetitions", [0, -1, True, "1"])
def test_measured_paths_rejects_invalid_total_repetitions(
    tmp_path: Path,
    total_repetitions: object,
) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)

    with pytest.raises(ValueError, match="total_repetitions"):
        reporter.measured_paths(
            pack.cases[0],
            1,
            total_repetitions,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("warmup_index", [0, -1, True, "1"])
def test_warmup_paths_rejects_invalid_warmup_index(
    tmp_path: Path,
    warmup_index: object,
) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)

    with pytest.raises(ValueError, match="warmup_index"):
        reporter.warmup_paths(
            pack.cases[0],
            warmup_index,  # type: ignore[arg-type]
        )


def test_record_can_include_reporter_owned_repetition(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)
    req, resp = reporter.measured_paths(pack.cases[0], 2, 2)
    ar = make_adapter_result_for_paths(req, resp)

    record = reporter.record(
        pack.cases[0],
        ar,
        sample={"memory_mb": None, "gpu_memory_mb": None},
        repetition=2,
    )

    assert record["repetition"] == 2
    assert record["raw"]["request_path"] == "raw/capital.rep-002.request.json"


def test_record_can_include_workspace_metadata(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)
    ar = make_adapter_result(out)

    record = reporter.record(
        pack.cases[0],
        ar,
        sample={"memory_mb": None, "gpu_memory_mb": None},
        workspace={
            "path": "workspace/capital/rep-001",
            "source_fixture_id": "repo",
            "source_path": "fixtures/repo",
        },
    )

    assert record["workspace"] == {
        "path": "workspace/capital/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    jsonl_record = json.loads((out / "run.jsonl").read_text())
    assert jsonl_record["workspace"] == record["workspace"]


def test_record_can_include_patch_metadata(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)
    ar = make_adapter_result(out)

    record = reporter.record(
        pack.cases[0],
        ar,
        sample={"memory_mb": None, "gpu_memory_mb": None},
        patch={"path": "patch/capital/rep-001.diff"},
    )

    assert record["patch"] == {"path": "patch/capital/rep-001.diff"}
    jsonl_record = json.loads((out / "run.jsonl").read_text())
    assert jsonl_record["patch"] == record["patch"]


def test_record_can_include_task_metadata(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)
    ar = make_adapter_result(out)

    record = reporter.record(
        pack.cases[0],
        ar,
        sample={"memory_mb": None, "gpu_memory_mb": None},
        task={
            "stdout_path": "task/capital/rep-001.stdout.log",
            "stderr_path": "task/capital/rep-001.stderr.log",
        },
    )

    assert record["task"] == {
        "stdout_path": "task/capital/rep-001.stdout.log",
        "stderr_path": "task/capital/rep-001.stderr.log",
    }
    jsonl_record = json.loads((out / "run.jsonl").read_text())
    assert jsonl_record["task"] == record["task"]


@pytest.mark.parametrize("repetition", [0, -1, True, "1"])
def test_record_rejects_invalid_repetition(
    tmp_path: Path,
    repetition: object,
) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)

    with pytest.raises(ValueError, match="repetition"):
        reporter.record(
            pack.cases[0],
            make_adapter_result(out),
            sample={"memory_mb": None, "gpu_memory_mb": None},
            repetition=repetition,  # type: ignore[arg-type]
        )


def test_write_hardware_writes_json(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path)
    reporter = RunReporter(out, pack)
    reporter.write_hardware({"hostname": "h", "platform": "darwin", "gpus": []})
    data = json.loads((out / "hardware.json").read_text())
    assert data["hostname"] == "h"


def test_write_summary_includes_pack_and_case(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path, scoring=Scoring(mode="contains", expected="Paris"))
    reporter = RunReporter(out, pack)
    reporter.record(
        pack.cases[0],
        make_adapter_result(out),
        sample={"memory_mb": None, "gpu_memory_mb": None},
    )
    reporter.write_summary({"hostname": "h", "platform": "darwin"})
    text = (out / "summary.md").read_text()
    assert "smoke-chat" in text
    assert "capital" in text
    assert "ollama-generate" in text


def test_write_summary_distinguishes_repetitions(tmp_path: Path) -> None:
    out = tmp_path / "run"
    pack = make_pack(tmp_path, scoring=Scoring(mode="contains", expected="Paris"))
    reporter = RunReporter(out, pack)
    for repetition in (1, 2):
        req, resp = reporter.measured_paths(pack.cases[0], repetition, 2)
        reporter.record(
            pack.cases[0],
            make_adapter_result_for_paths(req, resp),
            sample={"memory_mb": None, "gpu_memory_mb": None},
            repetition=repetition,
        )

    reporter.write_summary({"hostname": "h", "platform": "darwin"})
    text = (out / "summary.md").read_text()

    assert "capital#1" in text
    assert "capital#2" in text
