"""Tests for the openai-chat adapter."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from benchpack.adapters import AdapterRequest
from benchpack.adapters.openai_chat import OpenAIChatAdapter


def make_request(tmp_path: Path, **overrides) -> AdapterRequest:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    base = {
        "prompt": "What is the capital of France?",
        "model": "test-model",
        "endpoint": "http://example.test/v1",
        "defaults": {"temperature": 0, "max_tokens": 64, "stream": False},
        "request_path": raw_dir / "case-001.request.json",
        "response_path": raw_dir / "case-001.response.json",
    }
    base.update(overrides)
    return AdapterRequest(**base)


def test_openai_chat_happy_path(tmp_path: Path) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "id": "resp-1",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "Paris."}}
                ],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 2,
                    "total_tokens": 9,
                },
            },
        )

    transport = httpx.MockTransport(handler)
    adapter = OpenAIChatAdapter(transport=transport)
    req = make_request(tmp_path)

    result = adapter.run(req)

    assert result.ok is True
    assert result.adapter == "openai-chat"
    assert result.endpoint == "http://example.test/v1/chat/completions"
    assert result.model == "test-model"
    assert result.timing.wall_s > 0
    assert result.timing.ttft_s is None
    assert result.timing.prefill_tps is None
    assert result.timing.decode_tps is None
    assert result.tokens.prompt == 7
    assert result.tokens.output == 2
    assert result.raw.request_path == str(req.request_path)
    assert result.raw.response_path == str(req.response_path)

    assert captured["url"] == "http://example.test/v1/chat/completions"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["messages"] == [
        {"role": "user", "content": "What is the capital of France?"}
    ]
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["max_tokens"] == 64
    assert captured["body"].get("stream") in (False, None)

    assert json.loads(req.request_path.read_text())["model"] == "test-model"
    assert json.loads(req.response_path.read_text())["choices"][0]["message"][
        "content"
    ] == "Paris."


def test_openai_chat_endpoint_already_full(tmp_path: Path) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(handler))
    req = make_request(
        tmp_path, endpoint="http://example.test/v1/chat/completions"
    )

    adapter.run(req)
    assert captured["url"] == "http://example.test/v1/chat/completions"


def test_openai_chat_marks_failure_on_http_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(handler))
    req = make_request(tmp_path)

    result = adapter.run(req)

    assert result.ok is False
    assert result.error is not None
    assert "500" in result.error
    assert req.response_path.exists()
