"""End-to-end CLI smoke test using a mocked adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from benchpack import adapters as adapters_pkg
from benchpack.adapters import (
    AdapterRequest,
    AdapterResult,
    RawPaths,
    Timing,
    Tokens,
)
from benchpack.adapters.openai_chat import OpenAIChatAdapter
from benchpack.cli import main


def _install_fake_adapter(monkeypatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Paris."}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 2},
            },
        )

    transport = httpx.MockTransport(handler)

    class FakeAdapter(OpenAIChatAdapter):
        def __init__(self) -> None:
            super().__init__(transport=transport)

    monkeypatch.setitem(adapters_pkg.ADAPTERS, "openai-chat", FakeAdapter)
    return calls


def _install_recording_adapter(monkeypatch) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []

    class RecordingAdapter:
        name = "openai-chat"

        def run(self, request: AdapterRequest) -> AdapterResult:
            calls.append(
                {
                    "prompt": request.prompt,
                    "request_path": request.request_path.name,
                    "response_path": request.response_path.name,
                }
            )
            request.request_path.write_text(json.dumps({"prompt": request.prompt}))
            request.response_path.write_text(
                json.dumps(
                    {
                        "choices": [
                            {"message": {"role": "assistant", "content": "Paris."}}
                        ],
                        "usage": {"prompt_tokens": 7, "completion_tokens": 2},
                    }
                )
            )
            return AdapterResult(
                adapter=self.name,
                endpoint="http://example.test/v1/chat/completions",
                model=request.model,
                ok=True,
                timing=Timing(wall_s=1.0),
                tokens=Tokens(prompt=7, output=2),
                raw=RawPaths(
                    request_path=str(request.request_path),
                    response_path=str(request.response_path),
                ),
                output_text="Paris.",
            )

    monkeypatch.setitem(adapters_pkg.ADAPTERS, "openai-chat", RecordingAdapter)
    return calls


def _write_smoke_pack(tmp_path: Path, defaults_extra: str = "") -> None:
    pack_dir = tmp_path / "benchpacks" / "smoke-chat"
    pack_dir.mkdir(parents=True)
    (pack_dir / "benchpack.toml").write_text(
        f"""
[pack]
id = "smoke-chat"
version = "0.1.0"

[defaults]
temperature = 0
max_tokens = 32
stream = false
{defaults_extra}

[[cases]]
id = "capital"
kind = "chat"
prompt = "What is the capital of France?"

[scoring]
mode = "contains"
expected = "Paris"
"""
    )


def _write_two_case_pack(tmp_path: Path, defaults_extra: str = "") -> None:
    pack_dir = tmp_path / "benchpacks" / "smoke-chat"
    pack_dir.mkdir(parents=True)
    (pack_dir / "benchpack.toml").write_text(
        f"""
[pack]
id = "smoke-chat"
version = "0.1.0"

[defaults]
temperature = 0
max_tokens = 32
stream = false
{defaults_extra}

[[cases]]
id = "alpha"
kind = "chat"
prompt = "Prompt A"

[[cases]]
id = "beta"
kind = "chat"
prompt = "Prompt B"

[scoring]
mode = "contains"
expected = "Paris"
"""
    )


def _argv(extra: list[str] | None = None) -> list[str]:
    return [
        "run",
        "smoke-chat",
        "--adapter",
        "openai-chat",
        "--model",
        "test-model",
        "--endpoint",
        "http://example.test/v1",
        "--host-label",
        "unit-test",
        *(extra or []),
    ]


def test_cli_run_produces_full_artifact_tree(tmp_path: Path, monkeypatch) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)

    rc = main(_argv())
    assert rc == 0

    out_dirs = list((tmp_path / "results").iterdir())
    assert len(out_dirs) == 1
    out = out_dirs[0]
    assert out.name.endswith("-unit-test")

    assert (out / "run.jsonl").exists()
    assert (out / "summary.md").exists()
    assert (out / "hardware.json").exists()
    assert (out / "raw").is_dir()
    assert (out / "raw" / "capital.request.json").exists()
    assert (out / "raw" / "capital.response.json").exists()

    record = json.loads((out / "run.jsonl").read_text().strip())
    # The combined record must carry the documented fields.
    assert record["pack"] == {"id": "smoke-chat", "version": "0.1.0"}
    assert record["case"] == "capital"
    assert record["adapter"] == "openai-chat"
    assert record["endpoint"] == "http://example.test/v1/chat/completions"
    assert record["scoring"] == {"mode": "contains", "passed": True}
    assert record["raw"]["request_path"] == "raw/capital.request.json"
    assert record["resources"].keys() == {"memory_mb", "gpu_memory_mb"}
    assert "repetition" not in record


def test_cli_repetitions_write_distinct_measured_records(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path, defaults_extra="repetitions = 2")

    assert main(_argv()) == 0

    out = next((tmp_path / "results").iterdir())
    records = [
        json.loads(line)
        for line in (out / "run.jsonl").read_text().strip().splitlines()
    ]
    assert [record["repetition"] for record in records] == [1, 2]
    assert [record["raw"]["request_path"] for record in records] == [
        "raw/capital.rep-001.request.json",
        "raw/capital.rep-002.request.json",
    ]
    assert (out / "raw" / "capital.rep-001.request.json").exists()
    assert (out / "raw" / "capital.rep-001.response.json").exists()
    assert (out / "raw" / "capital.rep-002.request.json").exists()
    assert (out / "raw" / "capital.rep-002.response.json").exists()
    assert not (out / "raw" / "capital.request.json").exists()

    summary = (out / "summary.md").read_text()
    assert "capital#1" in summary
    assert "capital#2" in summary


def test_cli_warmup_is_unrecorded_and_measured_repetitions_are_recorded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path, defaults_extra="warmup = 1\nrepetitions = 2")

    assert main(_argv()) == 0

    out = next((tmp_path / "results").iterdir())
    records = [
        json.loads(line)
        for line in (out / "run.jsonl").read_text().strip().splitlines()
    ]
    assert len(calls) == 3
    assert len(records) == 2
    assert [record["repetition"] for record in records] == [1, 2]
    assert (out / "raw" / "capital.warmup-001.request.json").exists()
    assert (out / "raw" / "capital.warmup-001.response.json").exists()
    assert all("warmup" not in record["raw"]["request_path"] for record in records)
    assert "warmup" not in (out / "summary.md").read_text()


def test_cli_repetitions_one_keeps_legacy_raw_paths_and_record_shape(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path, defaults_extra="repetitions = 1")

    assert main(_argv()) == 0

    out = next((tmp_path / "results").iterdir())
    assert (out / "raw" / "capital.request.json").exists()
    assert (out / "raw" / "capital.response.json").exists()
    assert not (out / "raw" / "capital.rep-001.request.json").exists()
    record = json.loads((out / "run.jsonl").read_text().strip())
    assert "repetition" not in record
    assert record["raw"] == {
        "request_path": "raw/capital.request.json",
        "response_path": "raw/capital.response.json",
    }


def test_cli_warmup_with_one_repetition_keeps_legacy_measured_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path, defaults_extra="warmup = 1\nrepetitions = 1")

    assert main(_argv()) == 0

    out = next((tmp_path / "results").iterdir())
    assert len(calls) == 2
    assert (out / "raw" / "capital.warmup-001.request.json").exists()
    assert (out / "raw" / "capital.warmup-001.response.json").exists()
    assert (out / "raw" / "capital.request.json").exists()
    assert (out / "raw" / "capital.response.json").exists()
    assert not (out / "raw" / "capital.rep-001.request.json").exists()

    record = json.loads((out / "run.jsonl").read_text().strip())
    assert "repetition" not in record
    assert record["raw"] == {
        "request_path": "raw/capital.request.json",
        "response_path": "raw/capital.response.json",
    }


def test_cli_runs_warmup_then_measured_per_case(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_two_case_pack(tmp_path, defaults_extra="warmup = 1\nrepetitions = 1")

    assert main(_argv()) == 0

    assert calls == [
        {
            "prompt": "Prompt A",
            "request_path": "alpha.warmup-001.request.json",
            "response_path": "alpha.warmup-001.response.json",
        },
        {
            "prompt": "Prompt A",
            "request_path": "alpha.request.json",
            "response_path": "alpha.response.json",
        },
        {
            "prompt": "Prompt B",
            "request_path": "beta.warmup-001.request.json",
            "response_path": "beta.warmup-001.response.json",
        },
        {
            "prompt": "Prompt B",
            "request_path": "beta.request.json",
            "response_path": "beta.response.json",
        },
    ]


def test_cli_refuses_to_overwrite_existing_run(tmp_path: Path, monkeypatch) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)

    assert main(_argv()) == 0
    with pytest.raises(SystemExit) as excinfo:
        main(_argv())
    assert "run.jsonl" in str(excinfo.value)
    assert "--force" in str(excinfo.value) or "--out" in str(excinfo.value)


def test_cli_force_replaces_existing_run(tmp_path: Path, monkeypatch) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)

    assert main(_argv()) == 0
    out_dirs = list((tmp_path / "results").iterdir())
    assert len(out_dirs) == 1
    out = out_dirs[0]

    # Drop a sentinel file in raw/ to confirm --force wipes it.
    sentinel = out / "raw" / "stale-from-prior-run.json"
    sentinel.write_text("{}")

    assert main(_argv(["--force"])) == 0
    assert not sentinel.exists()
    # New run.jsonl has exactly one record.
    lines = (out / "run.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
