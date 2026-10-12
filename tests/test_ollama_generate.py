"""Tests for the ollama-generate adapter."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

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


@pytest.mark.parametrize("payload", [
    {"error": "backend failed", "done": True, "response": "partial"},
    {"response": "partial", "done": False},
    {"response": "partial"},
    {"response": "partial", "done": 1},
    {"done": True},
    {"response": None, "done": True},
    {"response": 42, "done": True},
])
def test_ollama_requires_logical_completion(tmp_path: Path, payload) -> None:
    adapter = OllamaGenerateAdapter(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    req = make_request(tmp_path)
    result = adapter.run(req)
    assert result.ok is False
    assert result.error and len(result.error) <= 250
    assert json.loads(req.response_path.read_text()) == payload


def test_ollama_rejects_non_json_success(tmp_path: Path) -> None:
    adapter = OllamaGenerateAdapter(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<html>oops</html>"))
    )
    req = make_request(tmp_path)
    result = adapter.run(req)
    assert result.ok is False
    assert result.error
    assert "<html>oops</html>" in req.response_path.read_text()


def test_ollama_completed_empty_answer_is_valid(tmp_path: Path) -> None:
    adapter = OllamaGenerateAdapter(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"done": True, "response": ""}))
    )
    result = adapter.run(make_request(tmp_path))
    assert result.ok is True
    assert result.output_text == ""


@pytest.mark.parametrize("payload", [None, [], [1], "text", 1, True])
def test_ollama_invalid_top_level_is_isolated(tmp_path: Path, payload) -> None:
    responses = iter([payload, {"done": True, "response": "next"}])
    adapter = OllamaGenerateAdapter(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=json.dumps(next(responses)))
    ))
    req = make_request(tmp_path)
    result = adapter.run(req)
    assert result.ok is False
    assert result.error and len(result.error) <= 250
    assert json.loads(req.response_path.read_text()) == payload
    assert adapter.run(req).ok is True


@pytest.mark.parametrize("field", [
    "total_duration", "load_duration", "prompt_eval_count",
    "prompt_eval_duration", "eval_count", "eval_duration",
])
@pytest.mark.parametrize("value", [None, True, -1, 1.5, "2", [], {"count": 2}, 2**63, 10**400])
def test_ollama_invalid_metrics_are_isolated(tmp_path: Path, field, value) -> None:
    payload = {"done": True, "response": "partial", field: value}
    responses = iter([payload, {"done": True, "response": "next"}])
    adapter = OllamaGenerateAdapter(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=next(responses))
    ))
    req = make_request(tmp_path)
    result = adapter.run(req)
    assert result.ok is False
    assert result.error and len(result.error) <= 250
    assert result.tokens.prompt is None
    assert result.tokens.output is None
    assert result.backend is None
    assert json.loads(req.response_path.read_text()) == payload
    assert adapter.run(req).ok is True


def test_ollama_incomplete_answer_is_not_scored_and_next_case_runs(tmp_path: Path) -> None:
    from benchpack.packs import Case, Pack, Scoring
    from benchpack.results import RunReporter

    case = Case(id="answer", kind="chat", prompt="question", scoring=None, raw={})
    pack = Pack(id="test", version="1", description="test", defaults={},
                cases=[case], scoring=Scoring(mode="contains", expected="Paris"),
                path=tmp_path / "pack")
    reporter = RunReporter(tmp_path / "run", pack)
    responses = iter([{"done": False, "response": "Paris"},
                      {"done": True, "response": "Paris"}])
    adapter = OllamaGenerateAdapter(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=next(responses))
    ))
    req = make_request(tmp_path)
    first = adapter.run(req)
    assert first.output_text == "Paris"
    assert reporter.record(case, first, {})["scoring"] == {"mode": "contains", "passed": False}
    second = adapter.run(req)
    assert reporter.record(case, second, {})["scoring"]["passed"] is True


@pytest.mark.parametrize("body", [
    b"\xff\xfe\xfd",
    b'{"done":true,"response":"x","eval_count":' + b'9' * 5000 + b'}',
], ids=['invalid-encoding', 'oversized-integer'])
def test_ollama_decoder_failures_are_isolated(tmp_path: Path, body: bytes) -> None:
    responses = iter([httpx.Response(200, content=body),
                      httpx.Response(200, json={"done": True, "response": "next"})])
    adapter = OllamaGenerateAdapter(transport=httpx.MockTransport(lambda _: next(responses)))
    req = make_request(tmp_path)
    result = adapter.run(req)
    assert result.ok is False
    assert result.error and len(result.error) <= 250
    assert "text" in json.loads(req.response_path.read_text())
    assert adapter.run(req).ok is True


def test_ollama_largest_supported_metrics(tmp_path: Path) -> None:
    payload = {"done": True, "response": "", "eval_count": 2**63 - 1,
               "eval_duration": 2**63 - 1, "prompt_eval_count": 0,
               "prompt_eval_duration": 0}
    adapter = OllamaGenerateAdapter(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=payload)
    ))
    result = adapter.run(make_request(tmp_path))
    assert result.ok is True
    assert result.timing.decode_tps == 1_000_000_000
    assert result.timing.prefill_tps is None


def test_ollama_decoder_recursion_failure_is_isolated(tmp_path: Path, monkeypatch) -> None:
    response = httpx.Response(200, text="deep-json")
    def exhausted_decoder():
        raise RecursionError("decoder depth exhausted")
    monkeypatch.setattr(response, "json", exhausted_decoder)
    responses = iter([response, httpx.Response(200, json={"done": True, "response": "next"})])
    adapter = OllamaGenerateAdapter(transport=httpx.MockTransport(lambda _: next(responses)))
    req = make_request(tmp_path)
    assert adapter.run(req).ok is False
    assert json.loads(req.response_path.read_text()) == {"text": "deep-json"}
    assert adapter.run(req).ok is True
