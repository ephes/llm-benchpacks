"""Ollama ``/api/generate`` adapter.

Per ``docs/decisions.md`` D-003 we keep the native generate endpoint instead of
forcing Ollama through the OpenAI-compatible shape so that ``prompt_eval_*`` and
``eval_*`` duration fields are preserved.  Those fields populate
``timing.prefill_tps`` / ``timing.decode_tps``; the raw values stay accessible
under ``backend``.
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


_NS_PER_S = 1_000_000_000.0
_DEFAULT_ENDPOINT = "http://localhost:11434"
_BACKEND_FIELDS = (
    "total_duration",
    "load_duration",
    "prompt_eval_count",
    "prompt_eval_duration",
    "eval_count",
    "eval_duration",
)


def _resolve_url(endpoint: str | None) -> str:
    base = (endpoint or _DEFAULT_ENDPOINT).rstrip("/")
    if base.endswith("/api/generate"):
        return base
    return base + "/api/generate"


def _tps(count: int | None, duration_ns: int | None) -> float | None:
    if not count or not duration_ns:
        return None
    return round(count / (duration_ns / _NS_PER_S), 4)


def _build_options(defaults: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if "temperature" in defaults:
        options["temperature"] = defaults["temperature"]
    if "max_tokens" in defaults:
        options["num_predict"] = defaults["max_tokens"]
    if "top_p" in defaults:
        options["top_p"] = defaults["top_p"]
    return options


@register
class OllamaGenerateAdapter:
    name = "ollama-generate"

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
            "prompt": request.prompt,
            "stream": False,
        }
        options = _build_options(request.defaults)
        if options:
            body["options"] = options

        request.request_path.write_text(json.dumps(body, indent=2))

        ok = True
        error: str | None = None
        payload: dict[str, Any] = {}

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
                payload = response.json()
            except json.JSONDecodeError:
                payload = {"text": response.text}
            request.response_path.write_text(json.dumps(payload, indent=2))
            if response.status_code >= 400:
                ok = False
                error = f"HTTP {response.status_code}: {response.text[:200]}"
        finally:
            wall_s = time.monotonic() - start
            client.close()

        prompt_count = payload.get("prompt_eval_count")
        eval_count = payload.get("eval_count")
        prefill_tps = _tps(prompt_count, payload.get("prompt_eval_duration"))
        decode_tps = _tps(eval_count, payload.get("eval_duration"))

        backend = {k: payload[k] for k in _BACKEND_FIELDS if k in payload} or None

        output_text = payload.get("response", "") if isinstance(payload, dict) else ""

        return AdapterResult(
            adapter=self.name,
            endpoint=url,
            model=request.model,
            ok=ok,
            timing=Timing(
                wall_s=wall_s,
                prefill_tps=prefill_tps,
                decode_tps=decode_tps,
            ),
            tokens=Tokens(prompt=prompt_count, output=eval_count),
            raw=RawPaths(
                request_path=str(request.request_path),
                response_path=str(request.response_path),
            ),
            output_text=output_text,
            backend=backend,
            error=error,
        )
