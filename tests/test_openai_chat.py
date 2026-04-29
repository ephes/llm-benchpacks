"""Tests for the openai-chat adapter."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Iterator
from pathlib import Path

import httpx

from benchpack.adapters import AdapterRequest
from benchpack.adapters.openai_chat import (
    OPENAI_STREAM_USAGE_KEY,
    OPENAI_STREAM_USAGE_OMIT,
    OpenAIChatAdapter,
)


class DelayedSSEStream(httpx.SyncByteStream):
    def __init__(self, events: list[dict | str], delay_s: float = 0.01) -> None:
        self.events = events
        self.delay_s = delay_s

    def __iter__(self) -> Iterator[bytes]:
        for event in self.events:
            time.sleep(self.delay_s)
            if event == "[DONE]":
                yield b"data: [DONE]\n\n"
            elif isinstance(event, str):
                yield f"data: {event}\n\n".encode()
            else:
                yield f"data: {json.dumps(event)}\n\n".encode()


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
    assert result.tokens.cached_prompt is None
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


def test_openai_chat_captures_cached_prompt_tokens_non_streaming(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "ok"}}
                ],
                "usage": {
                    "prompt_tokens": 104,
                    "completion_tokens": 2,
                    "prompt_tokens_details": {"cached_tokens": 103},
                },
            },
        )

    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(handler))
    result = adapter.run(make_request(tmp_path))

    assert result.tokens.prompt == 104
    assert result.tokens.output == 2
    assert result.tokens.cached_prompt == 103


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


def test_openai_chat_streaming_happy_path(tmp_path: Path) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=DelayedSSEStream(
                [
                    {"choices": [{"delta": {"role": "assistant"}}]},
                    {"choices": [{"delta": {"content": "Par"}}]},
                    {"choices": [{"delta": {"content": "is."}}]},
                    {
                        "choices": [],
                        "usage": {
                            "prompt_tokens": 7,
                            "completion_tokens": 2,
                            "total_tokens": 9,
                            "prompt_tokens_details": {"cached_tokens": 6},
                        },
                    },
                    "[DONE]",
                ]
            ),
        )

    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(handler))
    req = make_request(
        tmp_path,
        defaults={"temperature": 0, "max_tokens": 64, "stream": True},
    )

    result = adapter.run(req)

    assert result.ok is True
    assert captured["body"]["stream"] is True
    assert captured["body"]["stream_options"] == {"include_usage": True}
    assert result.output_text == "Paris."
    assert result.tokens.prompt == 7
    assert result.tokens.output == 2
    assert result.tokens.cached_prompt == 6
    assert result.timing.wall_s > 0
    assert result.timing.ttft_s is not None
    assert 0 < result.timing.ttft_s < result.timing.wall_s
    assert result.timing.prefill_tps is not None
    assert math.isfinite(result.timing.prefill_tps)
    assert result.timing.decode_tps is not None
    assert math.isfinite(result.timing.decode_tps)

    response_payload = json.loads(req.response_path.read_text())
    assert response_payload["choices"][0]["message"]["content"] == "Paris."
    assert response_payload["usage"]["prompt_tokens"] == 7
    assert response_payload["chunks"][0]["delta"] == ""
    assert response_payload["chunks"][1]["delta"] == "Par"
    assert response_payload["chunks"][2]["delta"] == "is."
    assert response_payload["chunks"][1]["offset_s"] >= result.timing.ttft_s
    request_payload = json.loads(req.request_path.read_text())
    assert request_payload["stream_options"] == {"include_usage": True}


def test_openai_chat_streaming_without_usage_keeps_token_metrics_empty(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=DelayedSSEStream(
                [
                    {"choices": [{"delta": {"role": "assistant"}}]},
                    {"choices": [{"delta": {"content": "hello"}}]},
                    "[DONE]",
                ]
            ),
        )

    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(handler))
    req = make_request(tmp_path, defaults={"stream": True})

    result = adapter.run(req)

    assert result.ok is True
    assert result.output_text == "hello"
    assert result.tokens.prompt is None
    assert result.tokens.output is None
    assert result.tokens.cached_prompt is None
    assert result.timing.wall_s > 0
    assert result.timing.ttft_s is not None
    assert result.timing.prefill_tps is None
    assert result.timing.decode_tps is None


def test_openai_chat_streaming_omit_usage_sends_no_stream_options(
    tmp_path: Path,
) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=DelayedSSEStream(
                [
                    {"choices": [{"delta": {"role": "assistant"}}]},
                    {"choices": [{"delta": {"content": "hello"}}]},
                    "[DONE]",
                ]
            ),
        )

    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(handler))
    req = make_request(
        tmp_path,
        defaults={
            "stream": True,
            OPENAI_STREAM_USAGE_KEY: OPENAI_STREAM_USAGE_OMIT,
        },
    )

    result = adapter.run(req)

    assert result.ok is True
    assert captured["body"]["stream"] is True
    assert "stream_options" not in captured["body"]
    assert result.output_text == "hello"
    assert result.tokens.prompt is None
    assert result.tokens.output is None
    assert result.tokens.cached_prompt is None
    assert result.timing.wall_s > 0
    assert result.timing.ttft_s is not None
    assert result.timing.prefill_tps is None
    assert result.timing.decode_tps is None
    request_payload = json.loads(req.request_path.read_text())
    assert request_payload["stream"] is True
    assert "stream_options" not in request_payload


def test_openai_chat_streaming_omit_usage_still_consumes_usage_chunk(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert "stream_options" not in body
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=DelayedSSEStream(
                [
                    {"choices": [{"delta": {"content": "ok"}}]},
                    {
                        "choices": [],
                        "usage": {
                            "prompt_tokens": 5,
                            "completion_tokens": 1,
                            "prompt_tokens_details": {"cached_tokens": 4},
                        },
                    },
                    "[DONE]",
                ]
            ),
        )

    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(handler))
    req = make_request(
        tmp_path,
        defaults={
            "stream": True,
            OPENAI_STREAM_USAGE_KEY: OPENAI_STREAM_USAGE_OMIT,
        },
    )

    result = adapter.run(req)

    assert result.ok is True
    assert result.output_text == "ok"
    assert result.tokens.prompt == 5
    assert result.tokens.output == 1
    assert result.tokens.cached_prompt == 4
    assert result.timing.prefill_tps is not None
    assert math.isfinite(result.timing.prefill_tps)
    assert result.timing.decode_tps is not None
    assert math.isfinite(result.timing.decode_tps)


def test_openai_chat_streaming_marks_failure_on_http_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(handler))
    req = make_request(tmp_path, defaults={"stream": True})

    result = adapter.run(req)

    assert result.ok is False
    assert result.error is not None
    assert "500" in result.error
    assert result.timing.wall_s > 0
    assert result.timing.ttft_s is None
    assert result.timing.prefill_tps is None
    assert result.timing.decode_tps is None
    assert req.response_path.exists()
    response_payload = json.loads(req.response_path.read_text())
    assert response_payload["error"] == result.error
    assert response_payload["error_payload"] == {"text": "boom"}


def test_openai_chat_streaming_parse_error_keeps_partial_raw_only(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=DelayedSSEStream(
                [
                    {"choices": [{"delta": {"content": "partial"}}]},
                    "{not json",
                ]
            ),
        )

    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(handler))
    req = make_request(tmp_path, defaults={"stream": True})

    result = adapter.run(req)

    assert result.ok is False
    assert result.output_text == ""
    assert result.error is not None
    assert "stream parse error" in result.error
    response_payload = json.loads(req.response_path.read_text())
    assert response_payload["choices"][0]["message"]["content"] == "partial"
    assert response_payload["error"] == result.error
