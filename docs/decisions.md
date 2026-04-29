# Decisions

## D-001: Separate Repository

Keep the benchmark runner in its own repository instead of adding it to
`desktop-django-starter`.

Reason: runtime adapters, hardware profiles, model artifacts, and benchmark
results will churn independently from the Django/Electron starter.

## D-002: Benchmark Packs Are Source

Benchmark packs are versioned source artifacts, not ad hoc command snippets.

Reason: the same workload should be replayable across runtimes, hardware, and
dates. Versioning packs makes result comparisons meaningful.

## D-003: OpenAI-Compatible Adapter First, Native Adapters Where Useful

Support OpenAI-compatible `/v1/chat/completions` early because many runtimes
expose it. Also support native Ollama because it reports useful timing fields.

Reason: forcing all runtimes through one lowest-common-denominator API would hide
important backend metrics.

## D-004: Deterministic Scoring Preferred

Prefer deterministic scoring such as tests passing, schema validity, or exact
artifact checks. Allow LLM-as-judge only when a pack explicitly declares it.

Reason: local model comparisons are noisy enough without making scoring opaque.

## D-005: Hardware Profiles Are First-Class

Every run records hardware and runtime metadata.

Reason: local inference numbers are meaningless without the exact host, memory,
driver, runtime, quantization, and context assumptions.

## D-006: Generated Results Stay Mostly Local

Raw results are generated artifacts. Commit curated summaries and logs, not every
large response file.

Reason: benchmark runs can produce noisy or large artifacts. The repo should stay
usable as source.

## D-007: Python With uv

The first implementation is a Python package managed with `uv`.

Reason: most local LLM tooling (`mlx-lm`, llama.cpp Python bindings, Ollama
clients, vLLM) has first-class Python support, and `uv` gives reproducible
dependency resolution and fast environment setup without committing to a
heavier packaging system this early.

## D-008: TOML For Pack Manifests

Benchpack manifests are TOML files (`benchpack.toml`).

Reason: TOML is human-editable, supports the table and array-of-tables shape that
packs need (cases, scoring), and matches the Python tooling already used by `uv`
and `pyproject.toml`.

## D-009: Pack-Owned Warmup And Repetition Counts

Measured repetition count and warmup count live in pack manifest defaults as
`defaults.repetitions` and `defaults.warmup`, not CLI flags.

Reason: repeated runtime measurements are part of the benchmark workload
contract. Keeping counts in the pack makes runs comparable across hosts and
avoids ad hoc invocation differences. Warmups are excluded from `run.jsonl`,
scoring, and summaries because they are preparation work, not benchmark samples.

## D-010: Validate MLX Through Its OpenAI-Compatible Server First

Use `mlx_lm.server` with the existing `openai-chat` adapter before adding a
dedicated `mlx-lm` CLI or Python adapter.

Reason: `mlx_lm.server` exposes an OpenAI-compatible chat surface, which is the
same runtime boundary already used for `llama-server`, vLLM, LM Studio, and
similar servers. Proving or disproving compatibility there keeps the adapter
surface smaller. Add a dedicated MLX adapter only if server-path validation
shows that the OpenAI-compatible path cannot provide the measurements the
project needs.

## D-011: Compare Existing Result Artifacts First

Make the first comparison command read existing result directories containing
`run.jsonl` instead of executing benchmarks or reading generated `raw/`
artifacts.

Reason: `run.jsonl` is the stable result contract from prior slices. A
read-only compare command gives useful Phase 2 summaries without expanding the
adapter surface, mutating result directories, or depending on ignored raw
payloads. `prefill_tps` stays out of the primary comparison table until
normalized results carry enough prompt-cache metadata to establish cache parity.

## D-012: Cached Prompt Tokens Live Under `tokens.cached_prompt`

Normalize backend-reported cached prompt-token counts as
`tokens.cached_prompt` in new `run.jsonl` records.

Reason: cached prompt tokens are a token-count property directly tied to
`tokens.prompt` and prefill interpretation. Keeping a single nullable field
under `tokens` makes missing backend support explicit without introducing a
larger cache object before there are multiple normalized cache fields.

## D-013: Compare Prompt/Cache Parity From Normalized Token Medians

`benchpack compare` reports median `tokens.prompt` beside median
`tokens.cached_prompt` and warns when prompt-token medians differ for a case
only when every compared row in that case has a numeric `tokens.prompt` value.
Cached-token parity is interpreted only relative to comparable prompt token
counts, and `prefill_tps` remains omitted from the primary table until
prompt/cache parity is explicit enough for speed comparison.

Reason: cached prompt-token counts are not meaningful in isolation when compared
runs used different prompt token counts. Keeping the rule in compare, based only
on normalized `run.jsonl` token fields, preserves old artifact compatibility
while avoiding prompt/cache inference from ignored raw payloads or timing
fields.
