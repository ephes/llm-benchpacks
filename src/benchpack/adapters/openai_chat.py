"""OpenAI-compatible ``/v1/chat/completions`` adapter."""

from __future__ import annotations

import json
import os
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
OPENAI_API_KEY_ENV_KEY = "_openai_api_key_env"
# Largest integer exactly interoperable with JSON consumers using doubles.
MAX_NONSTREAM_TOKEN_COUNT = 2**53 - 1


class OpenAIChatAuthError(ValueError):
    """Raised when explicit openai-chat auth configuration is unusable."""


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


def _nonstream_completion(payload: Any) -> tuple[dict[str, Any], str]:
    if not isinstance(payload, dict):
        raise ValueError("response must be an object")
    if "error" in payload:
        raise ValueError("backend error response")
    usage = payload.get("usage")
    if usage is None:
        usage = {}
    if not isinstance(usage, dict):
        raise ValueError("usage must be an object or null")
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= MAX_NONSTREAM_TOKEN_COUNT
        ):
            raise ValueError("usage token counts must be integers between 0 and 2**53 - 1")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("choices must be a nonempty array")
    for choice in choices:
        if not isinstance(choice, dict):
            raise ValueError("choice must be an object")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ValueError("message must be an object")
        if "content" not in message:
            raise ValueError("message content is required")
        content = message["content"]
        if content is not None and not isinstance(content, str):
            raise ValueError("content must be a string or null")
    return usage, choices[0]["message"]["content"] or ""


def _auth_headers(defaults: dict[str, Any]) -> dict[str, str] | None:
    env_name = defaults.get(OPENAI_API_KEY_ENV_KEY)
    if env_name is None:
        return None
    if not isinstance(env_name, str) or not env_name:
        raise OpenAIChatAuthError(
            "openai-chat auth env var name must be a non-empty string"
        )
    token = os.environ.get(env_name)
    if token is None or token == "":
        raise OpenAIChatAuthError(
            f"openai-chat auth env var {env_name!r} is not set or is empty"
        )
    return {"Authorization": f"Bearer {token}"}


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
        headers = _auth_headers(request.defaults)
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
            return self._run_streaming(request, url, body, headers)

        request.request_path.write_text(json.dumps(body, indent=2))

        ok = True
        error: str | None = None
        usage: dict[str, Any] = {}
        response_payload: Any = None
        output_text = ""

        client = httpx.Client(transport=self._transport, timeout=self._timeout)
        start = time.monotonic()
        try:
            response = client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            ok = False
            error = f"transport error: {exc!r}"
            request.response_path.write_text(json.dumps({"error": str(exc)}))
        else:
            decode_failed = False
            try:
                response_payload = response.json()
                raw_response = json.dumps(response_payload, indent=2)
            except (ValueError, RecursionError):
                decode_failed = True
                response_payload = {"text": response.text}
                raw_response = json.dumps(response_payload, indent=2)
            request.response_path.write_text(raw_response)
            if response.status_code >= 400:
                ok = False
                error = f"HTTP {response.status_code}: {response.text[:200]}"
            elif decode_failed:
                ok = False
                error = "response parse error: response is not valid JSON"
            else:
                try:
                    usage, output_text = _nonstream_completion(response_payload)
                except ValueError as exc:
                    ok = False
                    error = f"response parse error: {str(exc)[:200]}"
        finally:
            wall_s = time.monotonic() - start
            client.close()

        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        cached_prompt_tokens = _cached_prompt_tokens(usage)

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
        headers: dict[str, str] | None,
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
        completed = False
        invalid_event = False

        client = httpx.Client(transport=self._transport, timeout=self._timeout)
        start = time.monotonic()
        try:
            with client.stream("POST", url, json=body, headers=headers) as response:
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
                            completed = True
                            break

                        invalid_event = True
                        error_payload = {"text": data[:2000]}
                        payload = json.loads(data)
                        error_payload = payload
                        if not isinstance(payload, dict):
                            raise ValueError("event must be an object")
                        if "error" in payload:
                            raise ValueError("backend error event")
                        event_usage = payload.get("usage")
                        if event_usage is not None:
                            if not isinstance(event_usage, dict):
                                raise ValueError("usage must be an object")
                            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                                value = event_usage.get(key)
                                if value is not None and (
                                    isinstance(value, bool) or not isinstance(value, int) or value < 0
                                ):
                                    raise ValueError("usage token counts must be nonnegative integers")

                        choices = payload.get("choices", [])
                        if not isinstance(choices, list):
                            raise ValueError("choices must be an array")
                        delta = ""
                        for choice in choices:
                            if not isinstance(choice, dict):
                                raise ValueError("choice must be an object")
                            delta_payload = choice.get("delta", {})
                            if not isinstance(delta_payload, dict):
                                raise ValueError("delta must be an object")
                            content = delta_payload.get("content")
                            if content is not None and not isinstance(content, str):
                                raise ValueError("content must be a string or null")
                        if event_usage is not None:
                            usage = event_usage
                        if choices:
                            delta = choices[0].get("delta", {}).get("content") or ""
                        invalid_event = False
                        error_payload = None
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
        except (json.JSONDecodeError, ValueError) as exc:
            ok = False
            error = f"stream parse error: {str(exc)[:200]}"
        finally:
            wall_s = time.monotonic() - start
            client.close()

        if ok and not completed:
            ok = False
            error = "stream ended before [DONE]"

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
        if invalid_event or error_payload is not None:
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
