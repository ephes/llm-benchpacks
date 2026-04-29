"""OpenAI-compatible ``/v1/chat/completions`` adapter."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from . import (
    AdapterRequest,
    AdapterResult,
    RawPaths,
    Timing,
    Tokens,
    register,
)


OPENAI_STREAM_USAGE_KEY = "_openai_stream_usage"
OPENAI_STREAM_USAGE_INCLUDE = "include"
OPENAI_STREAM_USAGE_OMIT = "omit"


def _resolve_url(endpoint: str | None) -> str:
    if not endpoint:
        raise ValueError("openai-chat adapter requires --endpoint")
    base = endpoint.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def _tps(count: int | None, duration_s: float | None) -> float | None:
    if not count or not duration_s or duration_s <= 0:
        return None
    return round(count / duration_s, 4)


def _json_payload_from_response(response: httpx.Response) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError:
        return {"text": response.text}


def _cached_prompt_tokens(usage: dict[str, Any]) -> int | None:
    details = usage.get("prompt_tokens_details")
    if not isinstance(details, dict):
        return None
    value = details.get("cached_tokens")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


@register
class OpenAIChatAdapter:
    name = "openai-chat"

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 600.0,
    ) -> None:
        self._transport = transport
        self._timeout = timeout

    def run(self, request: AdapterRequest) -> AdapterResult:
        url = _resolve_url(request.endpoint)
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "stream": False,
        }
        for key in ("temperature", "max_tokens", "top_p"):
            if key in request.defaults:
                body[key] = request.defaults[key]

        if request.defaults.get("stream"):
            body["stream"] = True
            stream_usage = request.defaults.get(
                OPENAI_STREAM_USAGE_KEY,
                OPENAI_STREAM_USAGE_INCLUDE,
            )
            if stream_usage == OPENAI_STREAM_USAGE_INCLUDE:
                body["stream_options"] = {"include_usage": True}
            elif stream_usage != OPENAI_STREAM_USAGE_OMIT:
                raise ValueError(
                    "openai-chat stream usage mode must be "
                    f"{OPENAI_STREAM_USAGE_INCLUDE!r} or {OPENAI_STREAM_USAGE_OMIT!r}"
                )
            return self._run_streaming(request, url, body)

        request.request_path.write_text(json.dumps(body, indent=2))

        ok = True
        error: str | None = None
        usage: dict[str, Any] = {}
        response_payload: Any = None

        client = httpx.Client(transport=self._transport, timeout=self._timeout)
        start = time.monotonic()
        try:
            response = client.post(url, json=body)
        except httpx.HTTPError as exc:
            ok = False
            error = f"transport error: {exc!r}"
            request.response_path.write_text(json.dumps({"error": str(exc)}))
        else:
            try:
                response_payload = response.json()
            except json.JSONDecodeError:
                response_payload = {"text": response.text}
            request.response_path.write_text(
                json.dumps(response_payload, indent=2)
            )
            if response.status_code >= 400:
                ok = False
                error = f"HTTP {response.status_code}: {response.text[:200]}"
            else:
                usage = response_payload.get("usage", {}) or {}
        finally:
            wall_s = time.monotonic() - start
            client.close()

        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        cached_prompt_tokens = _cached_prompt_tokens(usage)

        output_text = ""
        if isinstance(response_payload, dict):
            choices = response_payload.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                output_text = message.get("content") or ""

        return AdapterResult(
            adapter=self.name,
            endpoint=url,
            model=request.model,
            ok=ok,
            timing=Timing(wall_s=wall_s),
            tokens=Tokens(
                prompt=prompt_tokens,
                output=completion_tokens,
                cached_prompt=cached_prompt_tokens,
            ),
            raw=RawPaths(
                request_path=str(request.request_path),
                response_path=str(request.response_path),
            ),
            output_text=output_text,
            backend=None,
            error=error,
        )

    def _run_streaming(
        self,
        request: AdapterRequest,
        url: str,
        body: dict[str, Any],
    ) -> AdapterResult:
        request.request_path.write_text(json.dumps(body, indent=2))

        ok = True
        error: str | None = None
        usage: dict[str, Any] = {}
        output_parts: list[str] = []
        chunks: list[dict[str, Any]] = []
        ttft_s: float | None = None
        wall_s = 0.0
        error_payload: Any = None

        client = httpx.Client(transport=self._transport, timeout=self._timeout)
        start = time.monotonic()
        try:
            with client.stream("POST", url, json=body) as response:
                if response.status_code >= 400:
                    response.read()
                    error_payload = _json_payload_from_response(response)
                    ok = False
                    error = f"HTTP {response.status_code}: {response.text[:200]}"
                else:
                    for line in response.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            continue

                        payload = json.loads(data)
                        if payload.get("usage"):
                            usage = payload["usage"]

                        choices = payload.get("choices") or []
                        delta = ""
                        if choices:
                            delta_payload = choices[0].get("delta") or {}
                            delta = delta_payload.get("content") or ""
                        offset_s = time.monotonic() - start
                        chunks.append({"offset_s": offset_s, "delta": delta})
                        if delta:
                            if ttft_s is None:
                                ttft_s = offset_s
                            output_parts.append(delta)
        except httpx.HTTPError as exc:
            ok = False
            error = f"transport error: {exc!r}"
            error_payload = {"error": str(exc)}
        except json.JSONDecodeError as exc:
            ok = False
            error = f"stream parse error: {exc}"
        finally:
            wall_s = time.monotonic() - start
            client.close()

        assembled_text = "".join(output_parts)
        response_payload: dict[str, Any] = {
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": assembled_text},
                }
            ],
            "chunks": chunks,
        }
        if usage:
            response_payload["usage"] = usage
        if error is not None:
            response_payload["error"] = error
        if error_payload is not None:
            response_payload["error_payload"] = error_payload
        request.response_path.write_text(json.dumps(response_payload, indent=2))

        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        cached_prompt_tokens = _cached_prompt_tokens(usage)
        prefill_tps = _tps(prompt_tokens, ttft_s)
        decode_tps = _tps(completion_tokens, wall_s - ttft_s if ttft_s else None)
        output_text = assembled_text if ok else ""

        return AdapterResult(
            adapter=self.name,
            endpoint=url,
            model=request.model,
            ok=ok,
            timing=Timing(
                wall_s=wall_s,
                ttft_s=ttft_s,
                prefill_tps=prefill_tps,
                decode_tps=decode_tps,
            ),
            tokens=Tokens(
                prompt=prompt_tokens,
                output=completion_tokens,
                cached_prompt=cached_prompt_tokens,
            ),
            raw=RawPaths(
                request_path=str(request.request_path),
                response_path=str(request.response_path),
            ),
            output_text=output_text,
            backend=None,
            error=error,
        )
