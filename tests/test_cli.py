"""End-to-end CLI smoke test using a mocked adapter."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from benchpack import adapters as adapters_pkg
from benchpack.adapters.openai_chat import OpenAIChatAdapter
from benchpack.cli import main


def _install_fake_adapter(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
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


def _write_smoke_pack(tmp_path: Path) -> None:
    pack_dir = tmp_path / "benchpacks" / "smoke-chat"
    pack_dir.mkdir(parents=True)
    (pack_dir / "benchpack.toml").write_text(
        """
[pack]
id = "smoke-chat"
version = "0.1.0"

[defaults]
temperature = 0
max_tokens = 32
stream = false

[[cases]]
id = "capital"
kind = "chat"
prompt = "What is the capital of France?"

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
