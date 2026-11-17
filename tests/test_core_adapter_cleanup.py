"""Client retirement must not abort a campaign or replace a primary failure."""

import json
from pathlib import Path

import httpx
import pytest

from benchpack.adapters import AdapterRequest
from benchpack.adapters.ollama_generate import OllamaGenerateAdapter
from benchpack.adapters.openai_chat import OpenAIChatAdapter
from benchpack.packs import load_pack
from benchpack.results import RunReporter


class BrokenStream(httpx.SyncByteStream):
    def __iter__(self):
        yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        raise httpx.ReadError("private-stream-canary")


@pytest.mark.parametrize("mode,outcome", [
    (mode, outcome)
    for mode in ("ollama", "openai", "stream")
    for outcome in ("success", "parse", "http", "transport")
] + [("stream", "incomplete")])
@pytest.mark.parametrize("close_error", [OSError, RuntimeError])
def test_client_cleanup_preserves_outcome_and_next_case(
    tmp_path: Path, mode: str, outcome: str, close_error,
) -> None:
    def success():
        if mode == "ollama":
            return httpx.Response(200, json={
                "done": True, "response": "synthetic", "prompt_eval_count": 4,
                "eval_count": 2, "prompt_eval_duration": 1000000, "eval_duration": 1000000,
            })
        if mode == "openai":
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "synthetic"}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            })
        chunk = {"choices": [{"delta": {"content": "synthetic"}}],
                 "usage": {"prompt_tokens": 4, "completion_tokens": 2}}
        return httpx.Response(200, text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 2 or outcome == "success":
            return success()
        if outcome == "http":
            return httpx.Response(503, json={"error": "private-body-canary"})
        if outcome == "parse":
            body = "data: private-parse-canary\n\n" if mode == "stream" else "private-parse-canary"
            return httpx.Response(200, text=body)
        if outcome == "incomplete":
            return httpx.Response(200, text='data: {"choices": []}\n\n')
        if mode == "stream":
            return httpx.Response(200, stream=BrokenStream())
        raise httpx.ConnectError("private-transport-canary", request=request)

    class Transport(httpx.MockTransport):
        closes = 0

        def close(self):
            self.closes += 1
            if self.closes == 1:
                raise close_error("private-close-canary")

    transport = Transport(handler)
    adapter_class = OllamaGenerateAdapter if mode == "ollama" else OpenAIChatAdapter
    adapter = adapter_class(transport=transport)
    pack = load_pack(Path(__file__).resolve().parents[1] / "benchpacks/smoke-chat")
    reporter = RunReporter(tmp_path / "run", pack)
    results = []
    for repetition in (1, 2):
        request_path, response_path = reporter.measured_paths(pack.cases[0], repetition, 2)
        result = adapter.run(AdapterRequest(
            "synthetic", "test-model", "http://example.test", {"stream": mode == "stream"},
            request_path, response_path,
        ))
        results.append(result)
        reporter.record(pack.cases[0], result, {}, repetition=repetition)
        assert transport.closes == repetition  # Exactly one retirement per client.

    first, second = results
    assert not first.ok
    assert first.output_text == ""
    expected = {
        "success": "client cleanup error", "http": "HTTP 503",
        "transport": "transport error", "incomplete": "stream ended before [DONE]",
    }
    if outcome == "parse":
        assert first.error.startswith("stream parse error:" if mode == "stream" else "response parse error:")
    else:
        assert first.error == expected[outcome]
    if outcome in {"success", "parse", "http", "incomplete"}:
        assert all(value is None for value in first.tokens.to_dict().values())
        assert first.timing.ttft_s is None
        assert first.timing.prefill_tps is None
        assert first.timing.decode_tps is None
        assert first.backend is None
    assert first.timing.wall_s >= 0
    assert second.ok and second.output_text == "synthetic"
    assert calls == 2
    assert len(reporter.records) == 2
    portable = (reporter.output_dir / "run.jsonl").read_text()
    assert "private-" not in portable
    if outcome == "success":
        assert "synthetic" in Path(first.raw.response_path).read_text()
        assert reporter.records[0]["timing"]["total_tps"] is None
