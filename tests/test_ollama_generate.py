"""Tests for the ollama-generate adapter."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from benchpack.adapters import AdapterRequest
from benchpack.adapters.ollama_generate import OllamaGenerateAdapter


def make_request(tmp_path: Path, **overrides) -> AdapterRequest:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    base = {
        "prompt": "What is the capital of France?",
        "model": "test-model",
        "endpoint": "http://example.test",
        "defaults": {"temperature": 0, "max_tokens": 64, "stream": False},
        "request_path": raw_dir / "case-001.request.json",
        "response_path": raw_dir / "case-001.response.json",
    }
    base.update(overrides)
    return AdapterRequest(**base)


def test_ollama_generate_derives_tps_from_native_durations(tmp_path: Path) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "response": "Paris.",
                "done": True,
                "total_duration": 5_000_000_000,
                "load_duration": 100_000_000,
                "prompt_eval_count": 8,
                "prompt_eval_duration": 200_000_000,  # 0.2s -> 40 tps
                "eval_count": 50,
                "eval_duration": 1_000_000_000,  # 1.0s -> 50 tps
            },
        )

    transport = httpx.MockTransport(handler)
    adapter = OllamaGenerateAdapter(transport=transport)
    req = make_request(tmp_path)

    result = adapter.run(req)

    assert result.ok is True
    assert result.adapter == "ollama-generate"
    assert result.endpoint == "http://example.test/api/generate"
    assert result.tokens.prompt == 8
    assert result.tokens.output == 50
    assert result.tokens.cached_prompt is None
    assert result.tokens.to_dict() == {
        "prompt": 8,
        "output": 50,
        "cached_prompt": None,
    }
    assert result.timing.prefill_tps == 40.0
    assert result.timing.decode_tps == 50.0
    assert result.timing.ttft_s is None
    assert result.timing.wall_s > 0

    assert result.backend is not None
    assert result.backend["prompt_eval_count"] == 8
    assert result.backend["prompt_eval_duration"] == 200_000_000
    assert result.backend["eval_count"] == 50
    assert result.backend["eval_duration"] == 1_000_000_000
    assert result.backend["total_duration"] == 5_000_000_000

    assert captured["url"] == "http://example.test/api/generate"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["prompt"] == "What is the capital of France?"
    assert captured["body"]["stream"] is False
    assert captured["body"]["options"]["temperature"] == 0
    assert captured["body"]["options"]["num_predict"] == 64

    assert json.loads(req.request_path.read_text())["prompt"].startswith("What")
    assert json.loads(req.response_path.read_text())["response"] == "Paris."


def test_ollama_generate_handles_missing_durations(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"response": "ok", "done": True}
        )

    adapter = OllamaGenerateAdapter(transport=httpx.MockTransport(handler))
    result = adapter.run(make_request(tmp_path))

    assert result.ok is True
    assert result.tokens.prompt is None
    assert result.tokens.output is None
    assert result.timing.prefill_tps is None
    assert result.timing.decode_tps is None


def test_ollama_generate_marks_failure_on_http_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    adapter = OllamaGenerateAdapter(transport=httpx.MockTransport(handler))
    result = adapter.run(make_request(tmp_path))

    assert result.ok is False
    assert "500" in (result.error or "")
