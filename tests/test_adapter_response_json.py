"""Core provider evidence must have one JSON interpretation."""

import json
from pathlib import Path

import httpx
import pytest

from benchpack.adapters import AdapterRequest
from benchpack.adapters.ollama_generate import OllamaGenerateAdapter
from benchpack.adapters.openai_chat import OpenAIChatAdapter


def request_for(tmp_path: Path, stream: bool = False) -> AdapterRequest:
    return AdapterRequest(
        prompt="synthetic prompt", model="test-model", endpoint="http://example.test",
        defaults={"stream": stream}, request_path=tmp_path / "request.json",
        response_path=tmp_path / "response.json",
    )


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("adapter_type, members, suffix", [
    (OpenAIChatAdapter,
     ['"choices":[{"message":{"content":"first"}}]',
      '"choices":[{"message":{"content":"second"}}]'], ""),
    (OpenAIChatAdapter, ['"usage":{"completion_tokens":1}',
                         '"usage":{"completion_tokens":2}'],
     ',"choices":[{"message":{"content":"ok"}}]'),
    (OpenAIChatAdapter, ['"content":"first"', '"con\\u0074ent":"second"'],
     "nested-content"),
    (OpenAIChatAdapter, ['"cached_tokens":1', '"cached_tokens":2'], "nested-usage"),
    (OllamaGenerateAdapter, ['"done":false', '"done":true'], ',"response":"ok"'),
    (OllamaGenerateAdapter, ['"response":"first"', '"response":"second"'], ',"done":true'),
    (OllamaGenerateAdapter, ['"eval_count":1', '"eval_count":2'],
     ',"done":true,"response":"ok"'),
    (OllamaGenerateAdapter, ['"label":"first"', '"label":"second"'], "nested-extra"),
])
def test_nonstream_duplicate_members_fail_without_credit(
    tmp_path, adapter_type, members, suffix, reverse,
):
    joined = ",".join(reversed(members) if reverse else members)
    if suffix == "nested-content":
        text = '{"choices":[{"message":{' + joined + '}}]}'
    elif suffix == "nested-usage":
        text = ('{"choices":[{"message":{"content":"ok"}}],'
                '"usage":{"prompt_tokens_details":{' + joined + '}}}')
    elif suffix == "nested-extra":
        text = '{"done":true,"response":"ok","extra":[{' + joined + '}]}'
    else:
        text = "{" + joined + suffix + "}"
    valid = ({"done": True, "response": "next"} if adapter_type is OllamaGenerateAdapter
             else {"choices": [{"message": {"content": "next"}}]})
    responses = iter([httpx.Response(200, text=text), httpx.Response(200, json=valid)])
    adapter = adapter_type(transport=httpx.MockTransport(lambda _: next(responses)))
    request = request_for(tmp_path)

    result = adapter.run(request)

    assert not result.ok
    assert result.output_text == ""
    assert result.tokens.to_dict() == {"prompt": None, "output": None, "cached_prompt": None}
    assert result.timing.prefill_tps is None and result.timing.decode_tps is None
    assert result.backend is None
    assert result.error == "response parse error: duplicate JSON member"
    assert json.loads(request.response_path.read_text()) == {"text": text}
    assert adapter.run(request).output_text == "next"


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("members, wrapper", [
    (['"choices":[]', '"choices":[{"delta":{"content":"bad"}}]'], "{}"),
    (['"usage":{"completion_tokens":1}', '"usage":{"completion_tokens":2}'], "{}"),
    (['"content":"first"', '"con\\u0074ent":"second"'], '{"choices":[{"delta":{}}]}'),
    (['"completion_tokens":1', '"completion_tokens":2'], '{"usage":{}}'),
    (['"x":1', '"x":2'], '{"extra":[{}]}'),
])
def test_stream_duplicate_members_fail_without_credit(tmp_path, members, wrapper, reverse):
    text = wrapper.replace("{}", "{" + ",".join(reversed(members) if reverse else members) + "}")
    prior = {"choices": [{"index": 0, "delta": {"content": "prior"}}],
             "usage": {"prompt_tokens": 3, "completion_tokens": 1}}
    body = f"data: {json.dumps(prior)}\n\ndata: {text}\n\ndata: [DONE]\n\n"
    adapter = OpenAIChatAdapter(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, text=body)))
    request = request_for(tmp_path, stream=True)

    result = adapter.run(request)

    assert not result.ok and result.output_text == ""
    assert result.error == "stream parse error: invalid event"
    assert result.tokens.to_dict() == {"prompt": None, "output": None, "cached_prompt": None}
    assert result.timing.ttft_s is None
    assert result.timing.prefill_tps is None and result.timing.decode_tps is None
    raw = json.loads(request.response_path.read_text())
    assert raw["error_payload"] == {"text": text}
    assert raw["choices"][0]["message"]["content"] == "prior"


@pytest.mark.parametrize("adapter_type, stream", [
    (OpenAIChatAdapter, False), (OpenAIChatAdapter, True), (OllamaGenerateAdapter, False),
])
@pytest.mark.parametrize("status", [200, 500])
def test_duplicate_failure_evidence_is_bounded(tmp_path, adapter_type, stream, status):
    text = '{"extension":"' + "x" * 3000 + '","extension":null}'
    body = f"data: {text}\n\ndata: [DONE]\n\n" if stream and status == 200 else text
    adapter = adapter_type(transport=httpx.MockTransport(
        lambda _: httpx.Response(status, text=body)))
    request = request_for(tmp_path, stream=stream)
    result = adapter.run(request)
    assert not result.ok and result.output_text == ""
    raw = json.loads(request.response_path.read_text())
    evidence = raw["error_payload"] if stream else raw
    assert evidence == {"text": text[:2000]}
    assert len(result.error) < 100
