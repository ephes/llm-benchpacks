"""Runtime adapter contract.

Per ``docs/architecture.md`` the adapter return payload is intentionally narrow:
it covers only the fields the backend itself can supply.  The reporter is
responsible for adding ``pack``/``case``/``total_tps``/``scoring`` and the
collector is responsible for ``resources``.  Adapters must not import the
pack loader, the reporter, or the collector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class AdapterRequest:
    """Inputs handed to an adapter for a single case."""

    prompt: str
    model: str
    endpoint: str | None
    defaults: dict[str, Any]
    request_path: Path
    response_path: Path


@dataclass
class Timing:
    wall_s: float
    ttft_s: float | None = None
    prefill_tps: float | None = None
    decode_tps: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "wall_s": self.wall_s,
            "ttft_s": self.ttft_s,
            "prefill_tps": self.prefill_tps,
            "decode_tps": self.decode_tps,
        }


@dataclass
class Tokens:
    prompt: int | None = None
    output: int | None = None
    cached_prompt: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "output": self.output,
            "cached_prompt": self.cached_prompt,
        }


@dataclass
class RawPaths:
    request_path: str
    response_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_path": self.request_path,
            "response_path": self.response_path,
        }


@dataclass
class AdapterResult:
    """The narrow payload an adapter returns; reporter wraps it.

    ``endpoint`` is the resolved URL the adapter actually called — distinct
    from the user's possibly-shorter ``--endpoint`` argument — so result records
    are unambiguous when comparing the same adapter/model against different
    local servers.

    ``output_text`` carries the backend's textual output and is consumed by the
    reporter for scoring; it is not written into ``run.jsonl``.
    """

    adapter: str
    endpoint: str | None
    model: str
    ok: bool
    timing: Timing
    tokens: Tokens
    raw: RawPaths
    output_text: str = ""
    backend: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "adapter": self.adapter,
            "endpoint": self.endpoint,
            "model": self.model,
            "ok": self.ok,
            "timing": self.timing.to_dict(),
            "tokens": self.tokens.to_dict(),
            "raw": self.raw.to_dict(),
        }
        if self.backend is not None:
            out["backend"] = self.backend
        if self.error is not None:
            out["error"] = self.error
        return out


class Adapter(Protocol):
    name: str

    def run(self, request: AdapterRequest) -> AdapterResult: ...


# Registry populated by submodules at import time.
ADAPTERS: dict[str, type[Adapter]] = {}


def register(adapter_cls: type[Adapter]) -> type[Adapter]:
    ADAPTERS[adapter_cls.name] = adapter_cls
    return adapter_cls


def get_adapter(name: str) -> Adapter:
    # Trigger module import so adapters self-register.
    from . import openai_chat as _openai_chat  # noqa: F401
    from . import ollama_generate as _ollama_generate  # noqa: F401

    if name not in ADAPTERS:
        raise KeyError(
            f"unknown adapter {name!r}; registered: {sorted(ADAPTERS)}"
        )
    return ADAPTERS[name]()
