"""Tests for the openai-chat adapter."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from benchpack.adapters import AdapterRequest
from benchpack.adapters.openai_chat import (
    OPENAI_API_KEY_ENV_KEY,
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
        captured["authorization"] = request.headers.get("authorization")
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
    assert captured["authorization"] is None

    assert json.loads(req.request_path.read_text())["model"] == "test-model"
    assert json.loads(req.response_path.read_text())["choices"][0]["message"][
        "content"
    ] == "Paris."


def test_openai_chat_sends_authorization_header_non_streaming(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    token = "unit-test-token"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    monkeypatch.setenv("BENCHPACK_OPENAI_TOKEN", token)
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(handler))
    req = make_request(
        tmp_path,
        defaults={
            "temperature": 0,
            "max_tokens": 64,
            "stream": False,
            OPENAI_API_KEY_ENV_KEY: "BENCHPACK_OPENAI_TOKEN",
        },
    )

    result = adapter.run(req)

    assert result.ok is True
    assert captured["authorization"] == f"Bearer {token}"
    raw_request = req.request_path.read_text()
    assert "Authorization" not in raw_request
    assert "Bearer" not in raw_request
    assert token not in raw_request
    raw_response = req.response_path.read_text()
    assert "Authorization" not in raw_response
    assert "Bearer" not in raw_response
    assert token not in raw_response


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
        captured["authorization"] = request.headers.get("authorization")
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
    assert captured["authorization"] is None
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


def test_openai_chat_sends_authorization_header_streaming(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    token = "unit-test-stream-token"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=DelayedSSEStream(
                [
                    {"choices": [{"delta": {"content": "ok"}}]},
                    "[DONE]",
                ]
            ),
        )

    monkeypatch.setenv("BENCHPACK_STREAM_OPENAI_TOKEN", token)
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(handler))
    req = make_request(
        tmp_path,
        defaults={
            "stream": True,
            OPENAI_API_KEY_ENV_KEY: "BENCHPACK_STREAM_OPENAI_TOKEN",
        },
    )

    result = adapter.run(req)

    assert result.ok is True
    assert captured["authorization"] == f"Bearer {token}"
    raw_request = req.request_path.read_text()
    assert "Authorization" not in raw_request
    assert "Bearer" not in raw_request
    assert token not in raw_request
    raw_response = req.response_path.read_text()
    assert "Authorization" not in raw_response
    assert "Bearer" not in raw_response
    assert token not in raw_response


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


@pytest.mark.parametrize("env_value", [None, ""])
def test_openai_chat_configured_auth_missing_or_empty_env_fails_without_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_value: str | None,
) -> None:
    calls = 0
    env_name = "BENCHPACK_MISSING_OPENAI_TOKEN"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": []})

    if env_value is None:
        monkeypatch.delenv(env_name, raising=False)
    else:
        monkeypatch.setenv(env_name, env_value)
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(handler))
    req = make_request(
        tmp_path,
        defaults={"stream": False, OPENAI_API_KEY_ENV_KEY: env_name},
    )

    with pytest.raises(ValueError) as excinfo:
        adapter.run(req)

    message = str(excinfo.value)
    assert env_name in message
    assert "not set or is empty" in message
    assert "Bearer" not in message
    assert calls == 0
    assert not req.request_path.exists()
    assert not req.response_path.exists()


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
    assert response_payload["error_payload"] == {"text": "{not json"}


@pytest.mark.parametrize('events', [[], [{'choices': [{'delta': {'content': 'partial'}}]}], [{'error': {'message': 'backend failed'}}, '[DONE]']])
def test_stream_requires_completion(tmp_path: Path, events: list) -> None:
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=DelayedSSEStream(events, 0))))
    req = make_request(tmp_path, defaults={'stream': True})
    result = adapter.run(req)
    assert not result.ok
    assert result.output_text == ''
    assert result.error
    raw = json.loads(req.response_path.read_text())
    if events and 'error' in events[0]:
        assert raw['error_payload'] == events[0]
    if events and 'choices' in events[0]:
        assert raw['choices'][0]['message']['content'] == 'partial'


@pytest.mark.parametrize('payload', [[], None, {'choices': None}, {'choices': [{'delta': None}]}, {'usage': {'completion_tokens': 5}, 'choices': 1}, {'choices': 1}, {'choices': [None]}, {'choices': [{'delta': []}]}, {'choices': [{'delta': {'content': ['bad']}}]}, {'usage': []}, {'usage': {'completion_tokens': 'bad'}}])
def test_stream_shape_failure_isolated(tmp_path: Path, payload: object) -> None:
    class ClosingStream(DelayedSSEStream):
        closed = False
        def close(self) -> None:
            self.closed = True
    stream = ClosingStream([{'choices': [{'delta': {'content': 'partial'}}]}, json.dumps(payload), '[DONE]'], 0)
    responses = iter([stream, DelayedSSEStream([{'choices': [{'delta': {'content': 'next'}}]}, {'choices': [], 'usage': {'completion_tokens': 1}}, '[DONE]'], 0)])
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=next(responses))))
    req = make_request(tmp_path, defaults={'stream': True})
    failed = adapter.run(req)
    assert not failed.ok
    assert failed.output_text == ''
    assert len(failed.error) < 250
    assert stream.closed
    raw = json.loads(req.response_path.read_text())
    assert failed.tokens.output is None
    assert raw['error_payload'] == payload
    assert raw['choices'][0]['message']['content'] == 'partial'
    succeeded = adapter.run(req)
    assert succeeded.ok and succeeded.output_text == 'next'
    assert succeeded.tokens.output == 1


@pytest.mark.parametrize("payload", [
    [], None, 1, "scalar", {},
    {"choices": None}, {"choices": []}, {"choices": {}},
    {"choices": [None]}, {"choices": [{"message": None}]},
    {"choices": [{"message": []}]}, {"choices": [{"message": {}}]},
    {"choices": [{"message": {"content": 1}}]},
    {"choices": [{"message": {"content": ["bad"]}}]},
    {"choices": [{"message": {"content": "ok"}}, None]},
    {"error": {"message": "backend failed"}},
    {"error": None, "choices": [{"message": {"content": "ok"}}]},
    *[
        {"choices": [{"message": {"content": "ok"}}], "usage": usage}
        for usage in ([], 1, {"prompt_tokens": "1"}, {"completion_tokens": True},
                      {"total_tokens": -1}, {"completion_tokens": 1.5},
                      {"completion_tokens": 10**400}, {"prompt_tokens": 2**53},
                      {"total_tokens": 2**53})
    ],
])
def test_nonstream_shape_failure_isolated(tmp_path: Path, payload: object) -> None:
    responses = iter([
        httpx.Response(200, content=json.dumps(payload)),
        httpx.Response(200, json={"choices": [{"message": {"content": "next"}}]}),
    ])
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(lambda _: next(responses)))
    req = make_request(tmp_path)
    failed = adapter.run(req)
    assert not failed.ok
    assert failed.output_text == ""
    assert failed.error and len(failed.error) < 250
    assert failed.tokens.prompt is None and failed.tokens.output is None
    assert json.loads(req.response_path.read_text()) == payload
    succeeded = adapter.run(req)
    assert succeeded.ok and succeeded.output_text == "next"


def test_nonstream_non_json_failure_isolated(tmp_path: Path) -> None:
    responses = iter([
        httpx.Response(200, text="not JSON"),
        httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}),
    ])
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(lambda _: next(responses)))
    req = make_request(tmp_path)
    failed = adapter.run(req)
    assert not failed.ok and failed.output_text == ""
    assert "not valid JSON" in failed.error
    assert failed.tokens.output is None
    assert json.loads(req.response_path.read_text()) == {"text": "not JSON"}
    succeeded = adapter.run(req)
    assert succeeded.ok and succeeded.output_text == ""


@pytest.mark.parametrize("content", ["", None])
@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 0, "completion_tokens": 0}])
def test_nonstream_empty_completion_valid(tmp_path: Path, content: str | None, usage: object) -> None:
    payload = {"choices": [{"message": {"content": content}}], "usage": usage}
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    result = adapter.run(make_request(tmp_path))
    assert result.ok and result.output_text == ""
    assert result.tokens.output == (0 if usage else None)


def test_nonstream_integer_decode_limit_isolated(tmp_path: Path) -> None:
    text = '{"usage":{"prompt_tokens":' + '1' * 4301 + '}}'
    responses = iter([
        httpx.Response(200, text=text),
        httpx.Response(200, json={"choices": [{"message": {"content": "next"}}]}),
    ])
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(lambda _: next(responses)))
    req = make_request(tmp_path)
    failed = adapter.run(req)
    assert not failed.ok and failed.output_text == ""
    assert json.loads(req.response_path.read_text()) == {"text": text}
    assert adapter.run(req).output_text == "next"


def test_nonstream_http_error_does_not_extract_completion(tmp_path: Path) -> None:
    payload = {"choices": [None], "usage": []}
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(
        lambda _: httpx.Response(500, json=payload)
    ))
    req = make_request(tmp_path)
    result = adapter.run(req)
    assert not result.ok and result.output_text == ""
    assert "HTTP 500" in result.error
    assert result.tokens.output is None
    assert json.loads(req.response_path.read_text()) == payload


def test_nonstream_nested_json_failure_isolated(tmp_path: Path, monkeypatch) -> None:
    text = '[' * 2000 + '0' + ']' * 2000
    original_json = httpx.Response.json
    attempted = []

    def limited_json(response, **kwargs):
        if response.text == text:
            attempted.append(True)
            raise RecursionError('JSON nesting limit')
        return original_json(response, **kwargs)

    monkeypatch.setattr(httpx.Response, 'json', limited_json)
    responses = iter([
        httpx.Response(200, text=text),
        httpx.Response(200, json={"choices": [{"message": {"content": "next"}}]}),
    ])
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(lambda _: next(responses)))
    req = make_request(tmp_path)
    failed = adapter.run(req)
    assert not failed.ok and failed.output_text == ""
    assert attempted == [True]
    assert "not valid JSON" in failed.error
    assert failed.tokens.output is None
    assert json.loads(req.response_path.read_text()) == {"text": text}
    assert adapter.run(req).output_text == "next"


def test_nonstream_usage_upper_boundary_valid(tmp_path: Path) -> None:
    count = 2**53 - 1
    payload = {"choices": [{"message": {"content": "ok"}}],
               "usage": {"prompt_tokens": count, "completion_tokens": count,
                         "total_tokens": count}}
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    result = adapter.run(make_request(tmp_path))
    assert result.ok and result.tokens.output == count
