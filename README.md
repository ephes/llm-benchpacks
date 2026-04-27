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
```

Each invocation writes `results/<date>-<host-label>/` containing
`run.jsonl`, `summary.md`, `hardware.json`, and `raw/`. See
[`docs/specification.md`](docs/specification.md) for the full CLI shape and
collision rules, and `uv run pytest` for the test suite.

Bundled packs:

- `smoke-chat`: non-streaming single-case endpoint smoke test.
- `runtime-sweep`: streaming short/medium/long runtime measurement pack with one
  warmup and three measured repetitions per case.

## Initial Shape

The first implementation stays small:

1. A CLI that can run one benchmark pack against one endpoint.
2. An OpenAI-compatible adapter for `mlx_lm.server`, `llama-server`, vLLM, LM Studio, and similar servers.
3. An Ollama-native adapter for `/api/generate` so we retain Ollama's native timing fields.
4. Smoke and runtime-sweep benchmarks, plus one real workload pack from
   `desktop-django-starter` later in Phase 3.
5. JSONL result artifacts plus a small Markdown summary.

The repository is private while the spec and first runner are still unstable.
