"""OpenAI-compatible ``/v1/chat/completions`` adapter.

Phase 1 is non-streaming.  ``ttft_s`` / ``prefill_tps`` / ``decode_tps`` are
left as ``None`` until streaming support lands in Phase 2.
"""

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


def _resolve_url(endpoint: str | None) -> str:
    if not endpoint:
        raise ValueError("openai-chat adapter requires --endpoint")
    base = endpoint.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


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
            tokens=Tokens(prompt=prompt_tokens, output=completion_tokens),
            raw=RawPaths(
                request_path=str(request.request_path),
                response_path=str(request.response_path),
            ),
            output_text=output_text,
            backend=None,
            error=error,
        )
