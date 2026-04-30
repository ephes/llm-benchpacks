# llm-benchpacks

Portable benchmark packs for local LLM runtimes and coding-agent workloads.

This repository is for answering practical questions such as:

- Is direct `mlx-lm` faster than Ollama's MLX path on the same Mac?
- How does `llama-server` compare to `mlx_lm.server` on the same prompt shape?
- Which model/runtime combination is usable for a real coding-agent workflow?
- Do small hosted GPUs, such as Hetzner's RTX 4000 SFF Ada machines, behave differently enough that we need separate recommendations?

The project should measure both raw inference behavior and workload behavior. Raw
tokens/sec is useful, but coding agents also depend on time to first token,
prefill speed, prompt-cache reuse, long-context stability, tool-call formatting,
and whether the final repository changes pass verification.

## Documentation

- [Specification](docs/specification.md): product scope, benchmark model, metrics, and MVP.
- [Architecture](docs/architecture.md): proposed runner, adapters, packs, and result schema.
- [Implementation Plan](docs/implementation-plan.md): phased path from minimal runner to remote GPU comparisons.
- [Benchpack Format](docs/benchpack-format.md): initial manifest sketch.
- [Hardware Targets](docs/hardware-targets.md): initial machines and runtime assumptions.
- [Decisions](docs/decisions.md): durable design decisions.
- [Spec Log](docs/spec-log.md): dated changes to the spec and open design questions.
- [Run Log](docs/run-log.md): benchmark run history and result pointers.

## Usage

The Phase 1 runner is in `src/benchpack/`, managed with [`uv`](https://docs.astral.sh/uv/):

```sh
uv sync
uv run benchpack run smoke-chat --adapter ollama-generate --model qwen3-coder:latest
uv run benchpack run smoke-chat --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1
uv run benchpack run runtime-sweep --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-runtime --force
uv run benchpack run runtime-sweep --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --openai-stream-usage omit --host-label local-runtime --force
uv run benchpack run desktop-django-wrap --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-wrap --force
uv run benchpack compare results/2026-04-28-mlx-lm-runtime results/2026-04-29-llama-server-runtime
```

Each invocation writes `results/<date>-<host-label>/` containing
`run.jsonl`, `summary.md`, `hardware.json`, and `raw/`. See
[`docs/specification.md`](docs/specification.md) for the full CLI shape and
collision rules, and `uv run pytest` for the test suite.

For `openai-chat` streaming runs, `--openai-stream-usage include` is the
default and sends `stream_options.include_usage` so supporting endpoints can
return token usage chunks. Use `--openai-stream-usage omit` for
OpenAI-compatible local servers that reject that option; streamed output and
TTFT remain available, while usage-derived token counts and token-rate fields
stay null unless the server still reports usage.

`benchpack compare` is read-only and compares existing result directories that
contain `run.jsonl`. It prints per-case medians for wall time, TTFT, decode TPS,
total TPS, output tokens, prompt tokens, backend-reported cached prompt tokens,
and prefill TPS gated on prefill parity. The `prefill_tps med` column renders a
numeric median only when that case's `prefill parity` status is `comparable`;
otherwise it renders `—`. Compare also prints cache metadata coverage as
numeric cached-token rows over total rows for each case/run group and a
case-level `prefill parity` status repeated on each run row. The status is one
of `missing-case`, `prompt-missing`, `prompt-diff`, `cache-missing`,
`cache-diff`, or `comparable`, in that priority order. Compare warns when
metadata is incomplete, complete prompt-token medians differ, or complete
cached-token medians differ. Prompt-token coverage is used to decide whether a
prompt mismatch warning is meaningful, but the table does not add a second
coverage column. Old rows may lack `tokens.prompt`, `tokens.cached_prompt`, or
`timing.prefill_tps`, and missing values do not establish parity or prefill
speed.

Bundled packs:

- `smoke-chat`: non-streaming single-case endpoint smoke test.
- `runtime-sweep`: streaming short/medium/long runtime measurement pack with one
  warmup and three measured repetitions per case.
- `desktop-django-wrap`: streaming prompt-only first Phase 3 coding-agent-shaped
  workload with pack-local prompt files that asks for Django-in-Electron
  wrapping plans, uses a `DDS_WRAP_PLAN` contains check, and declares two
  pack-local synthetic fixtures for wrap planning: one context file and one
  compact static Django repo snapshot directory. Both cases reference both
  fixtures by id. The file fixture is appended to the loaded prompt with stable
  delimiters, while the directory fixture remains metadata-only and is not
  copied, executed, injected, or used to mutate a repository. This is not yet a
  repo-mutating wrap benchmark.

## Initial Shape

The first implementation stays small:

1. A CLI that can run one benchmark pack against one endpoint.
2. An OpenAI-compatible adapter for `mlx_lm.server`, `llama-server`, vLLM, LM Studio, and similar servers.
3. An Ollama-native adapter for `/api/generate` so we retain Ollama's native timing fields.
4. Smoke and runtime-sweep benchmarks, plus the prompt-only
   `desktop-django-wrap` Phase 3 starter pack derived from the
   `desktop-django-starter` wrapping workflow, with static fixture metadata
   referenced by fixture id from cases. Referenced file fixtures are assembled
   into prompts, while referenced directory fixtures stay metadata-only.
   Fixtures are not templated, copied, executed, or used to mutate
   repositories.
5. JSONL result artifacts plus a small Markdown summary.

The repository is private while the spec and first runner are still unstable.
