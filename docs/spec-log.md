# Spec Log

Use this file for dated changes to the benchmark design. It is intentionally
lighter than ADRs: decisions go in `docs/decisions.md`; this file captures the
working history and open questions.

## Format

```text
## YYYY-MM-DD

### Changed
- ...

### Open Questions
- ...
```

## 2026-04-28 (Phase 2 MLX server-path planning)

### Changed

- Phase 2 now validates `mlx_lm.server` through the existing `openai-chat`
  adapter before adding any dedicated MLX adapter.
- The `mlx_lm.server` validation path is explicit: run `smoke-chat` first for
  basic OpenAI-compatible chat behavior, then run `runtime-sweep` for streaming
  TTFT, warmup, and measured repetitions.
- Added D-010 to record the durable decision that the OpenAI-compatible server
  path should be tried before a direct MLX adapter.
- Supersedes the 2026-04-26 open question about whether direct `mlx-lm` should
  start as a CLI adapter or through `mlx_lm.server`: try the server path first.
- Refines the 2026-04-26 streaming TTFT compatibility question: validate
  `stream_options.include_usage` against `mlx_lm.server` and `llama-server`,
  then add a narrow `openai-chat` compatibility mode only if needed.

### Open Questions

- Whether `mlx_lm.server` and `llama-server` accept
  `stream_options.include_usage` remains to be validated locally. If either
  rejects it, the next slice should be a narrow `openai-chat` streaming
  compatibility mode before `benchpack compare`.

## 2026-04-27 (Phase 2 runtime-sweep pack)

### Changed

- Added the bundled `runtime-sweep` pack with `short`, `medium`, and `long`
  fixed inline chat prompts for repeated local runtime measurement.
- The pack uses `defaults.stream = true`, `defaults.warmup = 1`,
  `defaults.repetitions = 3`, `max_tokens = 128`, and `scoring.mode = "none"`.
- Documented adapter interpretation for this pack: `openai-chat` exercises
  streaming TTFT with `stream_options.include_usage`, while
  `ollama-generate` preserves Ollama native timing fields.

### Open Questions

- Compare/aggregation remains the next Phase 2 slice now that repeated
  runtime-oriented rows can be produced by a bundled pack.

## 2026-04-26 (Phase 2 warmup and repetitions)

### Changed

- `benchpack run` now gives `defaults.repetitions` runner semantics: each case
  records that many measured executions, with a top-level 1-based `repetition`
  field only when the count is greater than one.
- `defaults.warmup` now runs unrecorded warmup executions before measured
  repetitions. Warmups call the same adapter and write raw artifacts, but do not
  appear in `run.jsonl`, scoring, or `summary.md`.
- Raw artifact names preserve `raw/<case>.request.json` and
  `raw/<case>.response.json` for single-repetition packs. Multi-repetition runs
  use `raw/<case>.rep-NNN.*.json`; warmups use
  `raw/<case>.warmup-NNN.*.json`.
- The summary table keeps its existing columns and displays repeated measured
  rows as `<case>#<repetition>`.

### Open Questions

- The `runtime-sweep` pack and compare/aggregation command remain later Phase 2
  slices.

## 2026-04-26 (Phase 2 streaming TTFT)

### Changed

- `openai-chat` now honors `defaults.stream = true` by using streamed chat
  completions with `stream_options.include_usage`, measuring TTFT from request
  send to the first non-empty `delta.content` chunk, and assembling raw streamed
  output plus per-chunk wall offsets under `raw/<case>.response.json`.
- When streaming usage is reported, `openai-chat` fills `tokens.prompt`,
  `tokens.output`, `timing.prefill_tps`, and `timing.decode_tps`. The prefill
  and decode rates are TTFT-based approximations because OpenAI-compatible
  streaming APIs do not expose native runtime phase durations.
- Non-streaming `openai-chat` requests remain the default when
  `defaults.stream` is false or absent.
- Stream parse failures keep any assembled partial content in the raw response
  file for debugging, but return empty `output_text` to the reporter so failed
  partial generations are not scored as successful output.

### Open Questions

- The `runtime-sweep` pack and compare command remain later Phase 2 slices.
- Some older OpenAI-compatible local servers reject
  `stream_options.include_usage`; an explicit compatibility mode may be needed
  when validating against those servers.

## 2026-04-26 (post-review)

### Changed

- Promoted the `benchpack run ... [--force]` CLI shape and the output-directory
  collision rule (refuse-by-default, `--force` replaces, `--out` writes
  elsewhere) into `docs/specification.md`. The spec is the contract;
  `spec-log.md` only records history.
- Reporter now writes `endpoint` (the resolved URL the adapter actually called)
  alongside `adapter`/`model` in every `run.jsonl` record. Adapter return
  payload gained an `endpoint` field. Closes the gap between
  `docs/specification.md` (which already required endpoint capture) and the
  initial implementation. `docs/architecture.md` updated.
- CLI refuses to overwrite an existing run directory that already contains a
  `run.jsonl`; pass `--force` to replace it or `--out` to write elsewhere.
  Prevents the "second run on the same date+host appends to old `run.jsonl`
  while overwriting `raw/` and rewriting `summary.md` from only the current
  records" failure mode flagged in review.
- `benchpack.toml` pack and case ids must now match
  `^[A-Za-z0-9][A-Za-z0-9_-]*$`. Manifests with unsafe ids (slashes, `..`,
  empty) are rejected at load time so the reporter can use ids verbatim as
  path components. `docs/benchpack-format.md` documents the grammar.

## 2026-04-26 (afternoon)

### Changed

- Landed the Phase 1 minimal runner from `docs/implementation-plan.md`.
  - Python package `benchpack` managed with `uv`; console script
    `benchpack = "benchpack.cli:main"`.
  - `benchpack run <pack> --adapter <adapter> --model <model> [--endpoint] [--out] [--host-label]`.
  - Adapters: `openai-chat` (POST `/v1/chat/completions`, non-streaming) and
    `ollama-generate` (POST `/api/generate`, derives `prefill_tps` /
    `decode_tps` from native duration fields and preserves them under `backend`).
  - Pack loader, scoring (`none` and `contains` only — other modes parse but
    raise `NotImplementedError` per Phase 1 scope), best-effort
    macOS/Linux hardware collector, and reporter that writes
    `run.jsonl`, `summary.md`, `hardware.json`, plus `raw/`.
  - Reporter assembles the three-contributor envelope from
    `docs/architecture.md` and runs scoring before appending each `run.jsonl`
    line. Adapters do not import the pack loader, the reporter, or the
    collector.
- Recorded `uv run pytest` as the repo-level validation command in `AGENTS.md`.
- Added the `smoke-chat` benchpack at `benchpacks/smoke-chat/`.

### Open Questions

- Streaming TTFT measurement and the `runtime-sweep` pack remain Phase 2 work.
- `mlx-lm` adapter shape (CLI vs server) is still open.
- Remote Linux orchestration over SSH is still open.
- Vendoring strategy for `desktop-django-starter` content is still open.

## 2026-04-26

### Changed

- Created the initial spec for `llm-benchpacks`.
- Scoped the project around benchmark packs rather than a single hard-coded local
  LLM benchmark.
- Added Apple Silicon and small Hetzner GPU hosts as first-class targets.
- Defined initial adapters: OpenAI-compatible chat and Ollama native generate.
- Defined initial packs: smoke, runtime sweep, desktop Django wrapping,
  patch-from-failure, and tool/JSON reliability.
- Closed implementation-language and manifest-format choices: Python with `uv`
  (D-007) and TOML pack manifests (D-008).
- Defined scoring modes and per-case override semantics in
  `docs/benchpack-format.md`, and clarified the relationship between declarative
  `[scoring]` blocks and `verify/` scripts.
- Added `hardware.json` to the canonical result artifact tree.
- Split the result record into three contributions: adapter return payload
  (runtime fields), collector sample (`resources.memory_mb`,
  `resources.gpu_memory_mb`), and reporter additions (`pack.id`,
  `pack.version`, `case`, derived `total_tps`, and `scoring`). Adapters do
  not produce or read collector or reporter fields.
- Reordered the execution flow so deterministic verifiers run before
  `run.jsonl` is written; the scoring result is captured in the same record
  rather than emitted afterwards.
- Clarified that curated `run.jsonl` files may be committed alongside
  `summary.md` and `hardware.json`, matching the narrowed `.gitignore`.
- Standardized host label format on `<chip>-<form>-<memory>` (for example
  `m5-mbp-64gb`, `hetzner-gex44`).
- Narrowed `.gitignore` so only `results/*/raw/` is excluded by default; curated
  `summary.md`, `hardware.json`, and small `run.jsonl` files under `results/`
  are committable.
- Extended `AGENTS.md` "Spec And Log Discipline" to name `architecture.md`,
  `benchpack-format.md`, and `hardware-targets.md` as docs that must be updated
  when their respective contracts change.

### Open Questions

- Should direct `mlx-lm` start as a CLI adapter or through `mlx_lm.server` only?
- Should remote Linux hosts be driven over SSH by the CLI, or should users run the
  CLI on the host and copy results back?
- How much of `desktop-django-starter` should be vendored into the wrap benchmark
  versus referenced as an external checkout?
