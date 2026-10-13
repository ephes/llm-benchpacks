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


_COMPLETE = {"response": "Paris.", "done": True, "eval_count": 5, "eval_duration": 1_000_000_000}


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("[]", "response must be an object"),
        ("null", "response must be an object"),
        ("7", "response must be an object"),
        ('"text"', "response must be an object"),
        ("<html>bad gateway</html>", "not valid JSON"),
        ("9" * 5000, "not valid JSON"),
        ("[" * 100_000, "not valid JSON"),
        (json.dumps({**_COMPLETE, "error": "model not loaded"}), "backend error response"),
        (json.dumps({**_COMPLETE, "error": None}), "backend error response"),
        (json.dumps({**_COMPLETE, "done": False}), "not complete"),
        (json.dumps({"response": "partial"}), "not complete"),
        (json.dumps({**_COMPLETE, "done": "true"}), "not complete"),
        (json.dumps({"done": True}), "response text must be a string"),
        (json.dumps({**_COMPLETE, "response": ["Paris."]}), "response text must be a string"),
        (json.dumps({**_COMPLETE, "response": None}), "response text must be a string"),
        (json.dumps({**_COMPLETE, "eval_count": "5"}), "eval_count must be an integer"),
        (json.dumps({**_COMPLETE, "eval_count": True}), "eval_count must be an integer"),
        (json.dumps({**_COMPLETE, "eval_count": -1}), "eval_count must be an integer"),
        (json.dumps({**_COMPLETE, "eval_count": 5.0}), "eval_count must be an integer"),
        (json.dumps({**_COMPLETE, "eval_duration": {"ns": 1}}), "eval_duration must be an integer"),
        (json.dumps({**_COMPLETE, "total_duration": 2**53}), "total_duration must be an integer"),
        (json.dumps({**_COMPLETE, "prompt_eval_count": 10**400}), "prompt_eval_count must be an integer"),
    ],
)
def test_ollama_generate_fails_incomplete_or_malformed_success_response(
    tmp_path: Path, body: str, message: str
) -> None:
    adapter = OllamaGenerateAdapter(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    )
    req = make_request(tmp_path)

    result = adapter.run(req)

    assert result.ok is False
    assert result.error is not None and result.error.startswith("response parse error: ")
    assert message in result.error
    assert len(result.error) < 200
    assert result.output_text == ""
    assert result.tokens.prompt is None and result.tokens.output is None
    assert result.timing.prefill_tps is None and result.timing.decode_tps is None
    assert result.backend is None
    raw = json.loads(req.response_path.read_text())
    try:
        assert raw == json.loads(body)
    except (ValueError, RecursionError):
        assert raw == {"text": body}


def test_ollama_generate_http_error_with_json_body_publishes_no_output(tmp_path: Path) -> None:
    adapter = OllamaGenerateAdapter(
        transport=httpx.MockTransport(lambda _: httpx.Response(500, json=_COMPLETE))
    )
    req = make_request(tmp_path)

    result = adapter.run(req)

    assert result.ok is False
    assert (result.error or "").startswith("HTTP 500")
    assert result.output_text == ""
    assert result.tokens.output is None
    assert result.backend is None
    assert json.loads(req.response_path.read_text()) == _COMPLETE


@pytest.mark.parametrize("text", ["", "Paris."])
def test_ollama_generate_accepts_completed_response_with_null_and_boundary_metrics(
    tmp_path: Path, text: str
) -> None:
    payload = {
        "response": text,
        "done": True,
        "prompt_eval_count": None,
        "eval_count": 0,
        "total_duration": 2**53 - 1,
    }
    adapter = OllamaGenerateAdapter(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )

    result = adapter.run(make_request(tmp_path))

    assert result.ok is True
    assert result.error is None
    assert result.output_text == text
    assert result.tokens.prompt is None
    assert result.tokens.output == 0
    assert result.backend == {"total_duration": 2**53 - 1, "eval_count": 0}
