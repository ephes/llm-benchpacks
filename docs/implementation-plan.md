# Implementation Plan

## Phase 1: Minimal Runner

**Status:** landed 2026-04-26. See `docs/spec-log.md` for the dated entries.

Deliver a CLI that can run one benchmark case against one endpoint and write
results.

Scope:

- Python package managed with `uv`.
- `benchpack run <pack> --adapter <adapter> --model <model>` (with
  `--endpoint`, `--out`, `--host-label`, `--force`).
- `openai-chat` adapter.
- `ollama-generate` adapter.
- `smoke-chat` benchmark pack.
- JSONL run output plus Markdown summary, with `endpoint` recorded per run.
- Best-effort hardware metadata on macOS and Linux.
- Refuse-to-overwrite collision rule on the per-run output directory.

Validation:

- `uv run pytest` (manifest loading, result normalization, scoring,
  re-run safety, adapter HTTP handling).
- Smoke run against a locally reachable endpoint.

## Phase 2: Runtime Sweep

Add fixed-context performance cases that make runtime comparisons meaningful.

**Status:** in progress. Streaming TTFT measurement for OpenAI-compatible
endpoints landed 2026-04-26, pack-driven warmup/repetitions landed 2026-04-26,
the bundled `runtime-sweep` pack landed 2026-04-27, `mlx_lm.server`
validation through `openai-chat` passed 2026-04-28, earlier local
`llama-server` validation attempts on 2026-04-29 were blocked by missing local
server/model prerequisites, and `llama-server` validation through
`openai-chat` passed later on 2026-04-29 after those prerequisites were
installed locally; the first read-only `benchpack compare` command landed
2026-04-29; normalized prompt-cache metadata for new rows landed 2026-04-29;
see `docs/spec-log.md`.

Scope:

- `runtime-sweep` pack with short, medium, and long prompt cases. **Landed
  2026-04-27.**
- Streaming TTFT measurement for OpenAI-compatible endpoints. **Landed
  2026-04-26.**
- Ollama native timing extraction.
- Warmup and repetitions. **Landed 2026-04-26.**
- Validate the `mlx_lm.server` OpenAI-compatible path through the existing
  `openai-chat` adapter. **Validated 2026-04-28.**
  - Run `smoke-chat` first to prove basic chat behavior.
  - Run `runtime-sweep` next to exercise streaming TTFT, warmup, and measured
    repetitions.
- Complete `llama-server` validation on a host with a verified
  `llama-server` binary and a suitable local GGUF instruct model. **Validated
  2026-04-29** with Homebrew `llama.cpp` 8960 and
  `Qwen2.5-0.5B-Instruct-Q4_K_M.gguf`.
- For future OpenAI-compatible server validation, do not run benchmark commands
  until local server/model prerequisites and server help output have been
  verified.
- If another OpenAI-compatible server rejects `stream_options.include_usage` or
  otherwise differs from the OpenAI-compatible streaming assumptions, add a
  narrow `openai-chat` compatibility slice before comparing that endpoint. That
  slice should likely suppress `stream_options.include_usage` for endpoints
  that reject it and record TTFT/output text while leaving usage-derived token
  rates null unless the endpoint reports token usage another way.
- Implement `benchpack compare` over existing `run.jsonl` result directories.
  **Landed 2026-04-29** as a compact read-only median table for wall time,
  TTFT, decode TPS, total TPS, and output tokens. Before using compare output
  for prefill-speed conclusions, establish prompt-cache parity between compared
  servers, for example by disabling llama.cpp prompt cache or recording
  cached-token counts on both sides.
- Normalize backend-reported cached prompt-token counts into
  `tokens.cached_prompt` for new rows. **Landed 2026-04-29** for
  OpenAI-compatible `usage.prompt_tokens_details.cached_tokens`; missing support
  is recorded as `null`, and existing result artifacts remain historical.

Validation:

- Same pack can run against `mlx_lm.server`, `llama-server`, and Ollama.
- `smoke-chat` against `mlx_lm.server` is considered successful when it writes
  one measured row with `ok = true` and `scoring.passed = true`.
- `runtime-sweep` against `mlx_lm.server` is considered successful when it
  writes nine measured rows, no warmup rows appear in `run.jsonl`, and each
  measured row has `ok = true`, non-null `timing.ttft_s`,
  `timing.prefill_tps`, `timing.decode_tps`, and `tokens.output`.
- `runtime-sweep` against `llama-server` should use the same success criteria
  as `runtime-sweep` against `mlx_lm.server`. **Validated 2026-04-29.**
- If `runtime-sweep` does not meet that bar, capture the adapter error or
  missing fields in the run notes before choosing the compatibility slice.

Suggested local `mlx_lm.server` check:

```sh
mlx_lm.server --model <mlx-model>
uv run benchpack run smoke-chat --adapter openai-chat --model <mlx-model> --endpoint http://localhost:8080/v1 --host-label mlx-lm-smoke --force
uv run benchpack run runtime-sweep --adapter openai-chat --model <mlx-model> --endpoint http://localhost:8080/v1 --host-label mlx-lm-runtime --force
```

Use the same invocation shape against the `llama-server` OpenAI-compatible
endpoint when validating that path.

Do not add a dedicated `mlx-lm` adapter until this server-path validation shows
that the OpenAI-compatible adapter is insufficient for the measurements we need.

## Phase 3: Desktop Django Workload

Add the first real coding-agent-shaped workload.

Scope:

- Import or generate the `desktop-django-starter` resolved wrap prompt.
- Include a compact target-repo snapshot fixture.
- Add deterministic constraints for short output comparison.
- Add optional full agent-session replay later.

Validation:

- The pack runs on Apple Silicon and Linux without path-specific edits.

## Phase 4: Task Completion Benchmarks

Move beyond speed into correctness.

Scope:

- `patch-from-failure` pack.
- Disposable worktree setup.
- Model output to patch extraction or agent-harness integration.
- Deterministic scoring by tests passing, diff size, and timeout.

Validation:

- A baseline model/runtime pair can solve at least one toy fixture end to end.

## Phase 5: Remote Host Orchestration

Make remote GPU runs practical.

Scope:

- Document a manual remote workflow first.
- Optional SSH runner after local execution is stable.
- Artifact pullback from hosts such as `hetzner-gex44`.
- Host labels and result comparison across machines.

Validation:

- A run from a remote Linux CUDA host can be compared with a local Mac run.
