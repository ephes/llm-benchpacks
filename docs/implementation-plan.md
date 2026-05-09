# Implementation Plan

## Active Backlog Queue

Status date: 2026-05-09.

This queue is the short working view over the longer historical plan below.
Keep completed implementation history in the phase sections, but use this
section to decide the next slice.

1. Keep `endpoint-python-correctness` helper/default-matrix promotion deferred
   after the 2026-05-09 local M5 `0.2.0` validation. The run reached
   `qwen3-coder:latest` through Ollama with `ok=true`, but the model again
   returned unmarked full-file Python inside a `diff` fence. It did not emit a
   unified diff or the new explicit `*** Begin File: inventory.py` replacement
   block, so the workspace stayed unchanged and the verifier failed. Treat this
   as a model output-contract failure, not a successful endpoint correctness
   lane.
2. Keep `coding-tasks-external-agent` explicitly exploratory and opt-in after
   the 2026-05-09 direct-edit comparison. The Apple M5/M4 slice reached
   Ollama/Codex on both hosts with valid telemetry and no endpoint or harness
   configuration blocker, but produced only 2/6 deterministic verifier passes:
   `fix-greeting` passed on both hosts, while the deeper Python and dashboard
   fixtures failed as no-source-mutation, no-mutation, or partial-source-edit
   task-quality failures. The Hetzner leg is driven from this machine through
   the authenticated OpenAI-compatible API, not by installing Codex, Claude,
   Ollama, or this repo on `llm.django-cast.com`. The local
   `openai-direct-edit-agent.py` wrapper reached
   `Qwen/Qwen2.5-1.5B-Instruct` through that API, but the rerun produced 0/3
   verifier passes: two non-JSON edit-payload failures before mutation and one
   verifier failure after an allowed-file mutation. Treat this as remote
   wrapper output-contract evidence first, especially because one non-JSON row
   ended with `finish_reason=length`; it is not a broad model-quality verdict.
3. Decide any next direct-edit external-agent slice deliberately before changing
   defaults: tighten the remote wrapper output contract, try JSON-mode or a
   larger completion budget on endpoints that support them, try a different
   already-configured agent/model, or refine reporting around no-source-mutation
   versus partial-source-mutation failures. Do not promote the external-agent
   pack set into helper defaults from the current mixed evidence.
4. Decide the next endpoint-only correctness slice deliberately before changing
   defaults: try another already-available endpoint, tighten the prompt
   contract, or consider whether accepting unmarked full-file replacements is
   safe enough. Do not change `scripts/benchpack-tmux-matrix` helper pack sets
   or default matrix recommendations until there is an apply-clean,
   verifier-passing live result.
5. Defer another broad runtime-only matrix for the current Gemma 4 strict-GGUF
   lane unless there is a new model target, runtime, host, or operational
   question. Existing M4/M5/Hetzner strict-GGUF evidence is sufficient for the
   current four-pack lane.
6. Keep result-registry work focused on concrete reporting/sharing needs. Local
   import, report, static site export, bundle create/validate, and bundle import
   have landed; hosted upload/review, richer public browsing, duplicate
   handling, query APIs, and leaderboard policy are later slices.
7. Keep research items parked until live evidence motivates them:
   concurrent/Poisson serving load, energy and cost-per-request, structured
   quantization axes, native CUDA server adapters, resource-aware program
   scoring, larger project-level tasks, and product matching/classification
   program benchmarks.

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

**Status:** closed 2026-04-30. The planned Phase 2 implementation slices have
landed: streaming TTFT, pack-driven warmup/repetitions, the bundled
`runtime-sweep` pack, Ollama native timing extraction, MLX and llama-server
OpenAI-compatible validation, read-only compare, normalized cache metadata,
cache-aware compare reporting, prompt/cache parity context, explicit prefill
parity status, gated comparable-only prefill TPS display, and explicit
`openai-chat` streaming usage omit mode. See `docs/spec-log.md` for the dated
history. Remaining items below are preserved as validation caveats or optional
future follow-up, not blockers for Phase 2 closure.

Scope:

- `runtime-sweep` pack with short, medium, and long prompt cases. **Landed
  2026-04-27.**
- Streaming TTFT measurement for OpenAI-compatible endpoints. **Landed
  2026-04-26.**
- Ollama native timing extraction. **Implemented and tested 2026-04-26** via
  the native `/api/generate` adapter's `prompt_eval_*` and `eval_*` duration
  fields, with those backend fields preserved in result metadata.
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
- For future optional OpenAI-compatible server validation, do not run benchmark
  commands until local server/model prerequisites and server help output have
  been verified.
- If another OpenAI-compatible server rejects `stream_options.include_usage`,
  run `openai-chat` streaming packs with `--openai-stream-usage omit`.
  **Landed 2026-04-29.** This explicit compatibility mode suppresses the
  `stream_options` key while preserving streamed output and TTFT; usage-derived
  token counts and token-rate fields remain null unless the endpoint reports
  token usage another way.
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
- Make `benchpack compare` cache-aware without adding `prefill_tps`.
  **Landed 2026-04-29** as cached-prompt medians, cache metadata coverage, and
  deterministic warnings for incomplete metadata or differing complete cached
  prompt-token medians.
- Make `benchpack compare` prompt/cache-parity-aware without adding
  `prefill_tps`. **Landed 2026-04-29** as prompt-token medians beside cached
  prompt-token medians, plus deterministic warnings when prompt-token medians
  differ and cache parity is therefore not comparable across different prompts.
- Add a compact deterministic `prefill parity` status to `benchpack compare`
  without adding `prefill_tps`. **Landed 2026-04-29** with case-level statuses
  repeated on each run row: `missing-case`, `prompt-missing`, `prompt-diff`,
  `cache-missing`, `cache-diff`, or `comparable`.
- Add a gated `prefill_tps med` compare column. **Landed 2026-04-29** as a
  median of normalized `timing.prefill_tps` values that renders numerically only
  when the case-level `prefill parity` status is `comparable`; every
  non-comparable status renders `—`.

Validation:

- The same pack is intended to run against `mlx_lm.server`, `llama-server`, and
  Ollama. Curated Phase 2 run-log evidence currently covers `mlx_lm.server` and
  `llama-server`; a curated Ollama `runtime-sweep` live run remains useful
  optional validation if needed later.
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

## Operational Track: Apple Silicon M4/M5 Comparison

Make local Apple Silicon comparisons repeatable before adding heavier remote or
production harness automation.

**Status:** started 2026-05-03. The first runbook/SSH orchestration slice
landed in `docs/apple-silicon-m4-m5-runbook.md` as a documentation-only
workflow for local M5 runs, SSH-driven M4 Studio runs, result pullback, compare
commands, fairness checks, interpretation boundaries, and troubleshooting. The
runner can already execute useful first-pass benchmarks for this goal with
`smoke-chat`, `runtime-sweep`, `desktop-django-wrap`, and
`patch-from-failure`. The optional bundled `python-regression-fix` and
`django-dashboard-regression-fix` repo-task packs are now available for deeper
fenced-patch signal, and the tmux helper now exposes them through an explicit
optional `--pack-set coding-tasks` matrix, but they are not part of the default
four-pack matrix.
Apple host model metadata and report-ready matrix guidance have also landed. A
read-only Markdown report generator also landed to
assemble run-log and comparison-note skeletons from existing result
directories while reusing compare median, warning, cache-row, and
`prefill parity` semantics. A narrow user-supplied runtime metadata slice also
landed: `benchpack run --run-metadata <json-file>` persists a small
`run-metadata.json` artifact and `benchpack report` includes it when present.
The narrow report-set manifest follow-up also landed: `benchpack report --set
<manifest.toml>` expands a source-only TOML list of existing result directories
into the same read-only report pipeline. Remaining work is deeper live
benchmark interpretation, production external harness execution, and further
larger repo-task packs, not benchmark semantics.

Scope:

- Add a local/SSH benchmark runbook for comparing this local M5 Max machine
  against the M4 Max Studio over SSH. **Landed 2026-05-03** in
  `docs/apple-silicon-m4-m5-runbook.md`, covering prerequisite checks, repo
  sync, `uv sync`, runtime/server startup assumptions, benchmark commands,
  host labels, result directory naming, artifact pullback, and
  `benchpack compare` invocation.
- Keep the first workflow manual or script-assisted, not a broad remote
  orchestration framework. Do not add live benchmark result artifacts or
  ignored `results/*/raw/` payloads to git.
- Define a recommended first comparison matrix. **Landed 2026-05-03** in the
  runbook:
  - `smoke-chat` for endpoint sanity
  - `runtime-sweep` for TTFT, throughput, prompt-token, cached-token, and
    prefill-parity comparison
  - `desktop-django-wrap` for prompt-only coding-agent-shaped behavior
  - `patch-from-failure` as the current tiny repo-mutating verifier-backed
    smoke task
- Add fairness notes for same model, quantization, runtime path, endpoint
  options, context/cache settings, power mode, thermal state, and background
  load. **Landed 2026-05-03** in the runbook. Treat M4-vs-M5 conclusions as
  invalid when those are not aligned or clearly documented.
- Audit Apple Silicon hardware/runtime metadata. **Landed 2026-05-03** as a
  narrow `hardware.json` host-metadata improvement: Darwin collection now
  records optional `hardware_model`, `hardware_model_name`, and
  `hardware_model_identifier` fields when macOS reports them, and uses
  `SPHardwareDataType` as a fallback for chip, core count, and memory when
  `sysctl` output is generic or unavailable. The audit confirmed that runtime
  versions, server command, model checksum, quantization, context size,
  power/thermal state, and cache settings should remain explicit run-note
  responsibilities for now rather than broad runtime discovery.
- Document result interpretation boundaries: `runtime-sweep` is ready for
  performance comparison now; `desktop-django-wrap` is prompt-only;
  `patch-from-failure` is useful as a tiny repo-task smoke benchmark;
  `python-regression-fix` is an optional deeper single-file fenced-patch
  repo-task pack; and `django-dashboard-regression-fix` is an optional
  stronger multi-file fenced-patch repo-task pack. Larger coding-agent
  conclusions should wait for production external harness support and more
  curated repo-task evidence. **Updated 2026-05-07** in the source docs.
- Add benchmark matrix and reporting polish before live M4/M5 runs.
  **Landed 2026-05-03** in the runbook as a comparison report checklist and
  compact report skeleton that separates `hardware.json` host identity from
  manually captured runtime/model/cache/power notes, calls out result
  directories, records compare warnings and prefill parity statuses, and keeps
  per-pack interpretation boundaries explicit.
- Add a read-only report generator to reduce manual run-log/report assembly
  after paired M4/M5 runs. **Landed 2026-05-03** as `benchpack report`, which
  loads existing result directories, includes optional `hardware.json` host
  identity, summarizes adapter/model/endpoint and scoring pass/fail counts, and
  reuses compare helpers for medians, warnings, cache rows, and
  `prefill parity`.
- Add structured user-supplied runtime/run metadata capture for benchmark
  result directories. **Landed 2026-05-03** as
  `benchpack run --run-metadata <json-file>`, which validates a permissive JSON
  object, writes `run-metadata.json` beside `hardware.json`, includes compact
  metadata in `summary.md`, and teaches `benchpack report` to render runtime,
  model, operating-condition, and notes fields when present. This remains
  explicit user input rather than runtime autodiscovery, and it does not change
  adapter schemas, result row fields, compare behavior, or pack semantics.
- Add a tmux-assisted matrix helper for the metadata-backed run workflow.
  **Landed 2026-05-05** as `scripts/benchpack-tmux-matrix`, a narrow dry-run
  and launch wrapper that assembles existing `benchpack run` commands for the
  default M4/M5 matrix, requires `--run-metadata`, maps pack names to stable
  host-label suffixes, and keeps `--force` opt-in. It is not a remote
  orchestration framework and does not change benchmark semantics.
- Add an explicit optional coding-task pack set to the tmux matrix helper.
  **Landed 2026-05-07** as `scripts/benchpack-tmux-matrix --pack-set
  coding-tasks`, expanding to `patch-from-failure`, `python-regression-fix`,
  and `django-dashboard-regression-fix` while keeping the default four-pack
  matrix unchanged and rejecting mixed positional packs plus `--pack-set`.
  This is helper ergonomics for exploratory fenced-patch repo-task evidence,
  not broad production external-agent proof.
- Add explicit external-agent coding-task variants and a helper pack set.
  **Landed 2026-05-07** as
  `scripts/benchpack-tmux-matrix --pack-set coding-tasks-external-agent`,
  expanding to `patch-from-failure-external-agent`,
  `python-regression-fix-external-agent`, and
  `django-dashboard-regression-fix-external-agent`. Each variant declares
  `harness = { id = "external-agent", timeout_s = 900 }` on the measured
  repo-task case. The variants initially reused the fenced-patch prompts, then
  were updated later on 2026-05-07 to direct-edit prompts. The original packs,
  default four-pack matrix, and fenced-patch `coding-tasks` set remain
  unchanged. The helper launch path requires `BENCHPACK_EXTERNAL_AGENT_ARGV`
  for this pack set and injects it into tmux windows without printing its value
  in dry-run output. Local M5 direct-edit validation later on 2026-05-07 showed
  that this surface now produces meaningful deterministic signal with Codex
  OSS/Ollama: two fixtures passed and the larger dashboard fixture failed from
  no workspace mutation.
- Add a local Codex OSS external-agent wrapper. **Landed 2026-05-07** as
  `examples/external-agent/codex-oss-agent.py`, adapting the public
  external-agent context to `codex exec --oss --local-provider <provider>` for
  already-available local providers such as Ollama. It is a local live-evidence
  adapter, not a cloud-backed or credential-injecting harness.
- Add a compact durable summary for the completed Qwen3.6 M4/M5 benchmark
  sweep. **Landed 2026-05-05** as
  `docs/qwen36-m4-m5-benchmark-summary.md`, which summarizes the host/runtime/
  model matrix, runtime-sweep median total TPS, scoring outcome, interpretation
  caveats, and ignored result-directory patterns without committing generated
  result artifacts.
- Add a narrow report-set manifest for repeated report assembly. **Landed
  2026-05-05** as `benchpack report --set <manifest.toml>`, which loads a
  source-only TOML manifest with `version = 1` and `result_dirs = [...]`,
  resolves relative entries against the manifest location, and feeds the
  existing read-only report renderer without running benchmarks or mutating
  result directories.

Suggested implementation handoffs:

- Runbook / SSH orchestration slice: make the local-M5 plus SSH-to-M4 workflow
  repeatable without changing benchmark semantics. **Landed 2026-05-03** as
  documentation only.
- Hardware / runtime metadata audit slice: verify and, if necessary, improve
  Apple Silicon metadata capture for comparable result interpretation.
  **Landed 2026-05-03** with optional Apple host model metadata in
  `hardware.json`; runtime parity remains documented through run notes.
- Benchmark matrix / reporting polish slice: document the recommended matrix,
  compare commands, caveats, and result-reading guidance. **Landed 2026-05-03**
  as documentation only.
- Reporting generator slice: produce pasteable Markdown from existing result
  directories without writing artifacts or changing benchmark semantics.
  **Landed 2026-05-03** as `benchpack report`.
- Runtime metadata capture/reporting slice: persist explicit user-supplied
  runtime, model, and operating-condition metadata as a small result artifact
  and include it in reports without probing servers or changing compare.
  **Landed 2026-05-03** as `run-metadata.json`.
- Tmux metadata matrix helper slice: make the next metadata-backed local or
  SSH-launched benchmark matrix easier to dry-run and start in tmux while
  leaving result generation and reporting in the existing CLI. **Landed
  2026-05-05** as `scripts/benchpack-tmux-matrix`.
- Tmux coding-task pack-set slice: expose the current bundled repo-task packs
  as an explicit optional matrix without changing defaults or runner
  semantics. **Landed 2026-05-07** as `scripts/benchpack-tmux-matrix
  --pack-set coding-tasks`.
- Report-set manifest slice: let repeated comparison reports name their
  existing result directories once without changing report output or writing
  generated report artifacts. **Landed 2026-05-05** as `benchpack report
  --set`.

Validation:

- Documentation-only changes should pass link/path review and
  `git status --short`.
- If helper scripts are added, run their dry-run or unit-test path and
  `uv run pytest`.
- Do not run live M4/M5 benchmarks as part of implementation validation unless
  explicitly requested; curated benchmark outcomes belong in `docs/run-log.md`.

## Operational Track: Model Targets And Tri-host Gemma 4

Keep model selection explicit and current before launching new cross-host
benchmark campaigns.

**Status:** started 2026-05-06. The model target catalog, authenticated
`openai-chat` endpoint support, Gemma 4 tri-host runbook, strict same-GGUF
artifact preflights, and selected Gemma 4 E2B Q4_K_M strict-GGUF four-pack
evidence across M5, M4, and Hetzner have landed. Generated result artifacts
remain ignored and uncommitted unless a future curated run-log entry explicitly
force-adds a compact subset.

Scope:

- Maintain a source-controlled model target catalog. **Landed 2026-05-06** in
  `docs/model-targets.md`, with Gemma 4 as the preferred current small tri-host
  planning target and Qwen3.6 retained as the continuity target for the
  documented M4/M5 sweep.
- Add authenticated OpenAI-compatible endpoint support for `openai-chat`.
  **Landed 2026-05-06.** `benchpack run` now accepts
  `--openai-api-key-env <ENV_NAME>` for `openai-chat`; the adapter reads the
  token from that named environment variable at request time and sends
  `Authorization: Bearer <token>` on streaming and non-streaming requests.
  Secret values stay out of result rows, metadata, raw artifacts, task logs,
  docs, and external-agent context. The runner does not automatically read
  `OPENAI_API_KEY`.
- Add a Gemma 4 tri-host runbook slice for M4, M5, and the Hetzner CUDA host.
  **Landed 2026-05-06** in `docs/gemma4-tri-host-runbook.md`. It reuses the
  metadata-backed matrix workflow, records whether each comparison is strict
  artifact parity or runtime-and-format, includes placeholder metadata examples
  and dry-run command matrices, and avoids committing generated `results/*`.
- Decide and document the first Gemma 4 comparison mode before running it.
  **Landed 2026-05-06.** The selected first campaign mode was strict same-GGUF
  parity through `llama-server` on all three hosts, subject to artifact/runtime/
  memory fit; that lane now has four-pack evidence. The secondary
  service-shaped option remains MLX/GGUF on Apple Silicon versus vLLM Hugging
  Face weights on Hetzner, labeled as runtime-and-format rather than artifact
  parity.
- Add authenticated endpoint pass-through to the tmux matrix helper.
  **Landed 2026-05-06** as `scripts/benchpack-tmux-matrix
  --openai-api-key-env <ENV_NAME>`, which passes the environment variable name
  through to generated `benchpack run` commands without reading token values or
  changing benchmark semantics.
- Validate Gemma 4 runtime support and artifacts before live runs.
  **Artifact catalog slice landed 2026-05-06.** The source-controlled catalog
  now verifies the public `google/gemma-4-E2B-it` and
  `google/gemma-4-E4B-it` Hugging Face IDs, immutable HF revisions, GGUF
  conversion repos/files, official Ollama tags, MLX conversion repos,
  vLLM/Transformers support docs, and license/auth gate state from primary
  sources. The tri-host runbook now names the first strict same-GGUF dry-run
  candidate and keeps unresolved fields explicit. **Local M5 first-candidate
  preflight landed 2026-05-06.** The selected
  `bartowski/google_gemma-4-E2B-it-GGUF` E2B Q4_K_M artifact was downloaded
  from the pinned revision, its local SHA-256 was captured, and local
  `/opt/homebrew/bin/llama-server` version `9030 (a09a00e50)` loaded it on
  loopback with alias `gemma4-e2b-q4km`, conservative context/cache/batch
  settings, and ignored metadata in `metadata/m5-gemma4-llama-server.json`.
  **Local M5 chat-completions smoke landed 2026-05-06.** A direct
  non-streaming `/v1/chat/completions` request returned exact
  `GEMMA4_SMOKE_OK` content, and a tiny streaming request accepted
  `stream_options.include_usage=true` with a final usage chunk, so the local
  `openai-chat` path can keep the default `--openai-stream-usage include`.
  Gemma 4 thinking behavior may still consume an entire very small streaming
  token budget before normal content appears. **Local M5 `smoke-chat`
  benchpack run attempted 2026-05-06.** The `openai-chat` adapter reached the
  endpoint and wrote one measured row with `ok=true`, but scoring failed
  because the model spent the full `max_tokens=64` completion budget on
  `reasoning_content`, returned empty normal assistant content, and did not
  contain `Paris`. **Local M5 thinking-control direct smoke landed
  2026-05-06.** Restarting the same local `llama-server` command with
  `--reasoning off` made the exact `smoke-chat` France prompt return normal
  assistant content containing `Paris`, no `reasoning_content`, and
  `finish_reason=stop` within the 64-token non-streaming direct HTTP request.
  **Local M5 reasoning-off smoke-chat retry landed 2026-05-06.** The
  subsequent `benchpack run smoke-chat` against that `--reasoning off` server
  passed with `ok=true`, `scoring.passed=true`, normal content containing
  `Paris`, no `reasoning_content`, and `finish_reason=stop`. This resolves the
  local M5 smoke-chat scoring blocker for the selected strict same-GGUF
  candidate only. **Local M5 reasoning-off runtime-sweep landed
  2026-05-07.** One `benchpack run runtime-sweep` against the same local
  `llama-server --reasoning off` endpoint completed with 9/9 measured rows
  `ok=true`, scoring mode `none`, warmup artifacts excluded from `run.jsonl`,
  TTFT and usage-derived token/timing fields present, normal assistant content,
  no observed `reasoning_content`, and no visible template/tool/EOG leakage in
  sampled raw responses. This supported moving on to the local M5 four-pack
  matrix for the exact selected strict-GGUF configuration. **Local M5
  reasoning-off four-pack matrix attempted 2026-05-07.** The default tmux
  matrix ran once for `smoke-chat`,
  `runtime-sweep`, `desktop-django-wrap`, and `patch-from-failure` against the
  same local endpoint. `smoke-chat` passed `contains`, `runtime-sweep` wrote
  9/9 `ok=true` unscored rows, and both `desktop-django-wrap` rows passed
  regex scoring. `patch-from-failure` reached the endpoint and wrote one
  `ok=true` row, but failed `verify-script` because the generated fenced diff
  targeted a class-based `greeter.py` shape that did not match the fixture; the
  patch was rejected and the verifier saw unchanged output. Treat that as a
  local model/task-quality blocker for the tiny repo-task pack, not a serving
  or adapter blocker. `--reasoning-budget 0` remains untested because
  `--reasoning off` resolved the direct, smoke-chat, runtime-sweep, and
  prompt-only wrap local M5 gates. **M4 strict-GGUF preflight landed
  2026-05-07.** The M4 Studio repo was synced to the same `a82fb3f` commit
  after preserving its previous dirty tree in a named stash. The same pinned
  `bartowski/google_gemma-4-E2B-it-GGUF` Q4_K_M artifact was downloaded and
  matched SHA-256
  `b5310340b3a23d31655d7119d100d5df1b2d8ee17b3ca8b0a23ad7e9eb5fa705`.
  `/opt/homebrew/bin/llama-server` version `9030 (a09a00e50)` loaded it on
  `127.0.0.1:8081` with alias `gemma4-e2b-q4km`, the same context/cache/batch
  settings, and `--reasoning off`. Exactly one M4 `smoke-chat` passed with
  normal Paris content and no `reasoning_content`; exactly one follow-up
  `runtime-sweep` wrote 9/9 `ok=true` unscored measured rows with usage-derived
  timing/token fields present and no observed template/tool/EOG leakage. The
  M4 server was stopped afterward. **Same-commit Apple four-pack matrices
  landed 2026-05-07.** After refreshing ignored metadata to `2acd1b3`, fresh
  M5 and M4 matrices ran with the same strict-GGUF `llama-server --reasoning
  off` setup. On both hosts, `smoke-chat` passed, `runtime-sweep` wrote 9/9
  `ok=true` rows, `desktop-django-wrap` passed both regex cases, and
  `patch-from-failure` reached the endpoint but failed `verify-script`
  scoring. Runtime-sweep compare reported `prefill parity=comparable` for all
  three cases. Median total TPS M5 vs M4 was 158.45 vs 137.19 short, 159.73 vs
  137.83 medium, and 161.02 vs 138.63 long. **Hetzner strict same-GGUF
  preflight landed 2026-05-07 in the sibling repo.** LNB-011 proved checksum
  parity, isolated CUDA `llama-server` 9030 (`a09a00e50`) support,
  conservative 8K local-only load behavior, 36/36 layer offload, and memory
  fit for the same E2B Q4_K_M artifact. It did not run a benchmark pack,
  generation request, public request, runtime-sweep, load test, or quality
  evaluation. **Hetzner strict same-GGUF smoke/runtime slice landed
  2026-05-07.** The next narrow Hetzner slice ran exactly one `smoke-chat`
  against the same local-only CUDA `llama-server` endpoint and, because it
  passed, exactly one `runtime-sweep`. Smoke passed deterministic `contains`
  scoring, runtime-sweep wrote 9/9 measured rows `ok=true`, timing/token fields
  were populated, sampled raw artifacts showed no observed reasoning/template/
  tool/EOG leakage or truncation markers, and production vLLM was restored
  healthy afterward. `benchpack compare` over the existing Apple current-commit
  runtime directories plus the new Hetzner runtime directory reported
  `prefill parity=comparable` for short, medium, and long; median total TPS
  M5 vs M4 vs Hetzner was 158.45 vs 137.19 vs 118.49 short, 159.73 vs 137.83
  vs 117.50 medium, and 161.02 vs 138.63 vs 117.33 long. **Hetzner strict
  same-GGUF wrap/patch completion slice landed 2026-05-07.** A follow-up
  exclusive-GPU window fast-forwarded the clean remote repo to `b1e62c0`,
  dry-ran the helper for exactly `desktop-django-wrap` and
  `patch-from-failure`, and ran exactly one of each against the same
  local-only CUDA endpoint. Wrap wrote two `ok=true` rows and both regex cases
  passed. Patch wrote one `ok=true` adapter row and failed deterministic
  `verify-script` because the generated unified diff could not be applied
  cleanly. Production was restored healthy afterward. This completes the
  strict-GGUF tri-host four-pack evidence for the selected artifact; keep
  throughput claims limited to matching `runtime-sweep` reports and treat
  wrap/patch as scoring outcomes.
- Restore live Hetzner inventory access through the sibling deployment repo.
  **Updated 2026-05-07.** Companion `llm-node-bare` backlog entries now record
  GPU-driver recovery, Qwen2.5 baseline restoration, a pinned Gemma 4 E2B
  vLLM full-card idle-load preflight on the RTX 4000 SFF Ada host, and
  production role support for the Gemma-4-capable vLLM stack. That clears the
  deployment-side vLLM service-shaped readiness blockers that were previously
  recorded in this repo, but it is separate from the strict same-GGUF
  `llama-server` lane preflighted in sibling LNB-011. The sibling LNB-005
  authenticated benchmark access contract and LNB-010 live authenticated smoke
  have also landed with `BENCHPACK_HETZNER_OPENAI_TOKEN`; the smoke proves the
  public TLS -> Django Bearer auth/proxy -> vLLM access path only, not approval
  for a benchmark matrix.
- Next-work ordering: do not spend the next slice on another broad live
  tri-host matrix for the current four-pack lane. The direct-edit external-agent
  slice now has local M5 evidence with 2/3 verifier passes, so broader
  M4/M5/NVIDIA direct-edit comparison is reasonable as exploratory evidence.
  Lightweight report/status polish landed on 2026-05-08, so empty workspace
  diffs and no-mutation failures are now visible without manual artifact
  inspection. A simpler endpoint-only deterministic verifier-backed repo-task
  pack has now landed as `endpoint-python-correctness`, and the first local M5
  Ollama validation reached the adapter but failed the patch-output contract:
  `qwen3-coder:latest` returned replacement Python content inside a `diff`
  fence rather than an applicable unified diff. The first follow-up has now
  deliberately added an explicit path-marked replacement block fallback and
  bumped the pack to `0.2.0`. Treat `desktop-django-wrap` as prompt/format
  coverage rather than the primary cross-host correctness signal, and keep
  endpoint-correctness helper/default-matrix promotion deferred until a later
  successful live endpoint validation.

Validation:

- Documentation-only catalog/backlog changes should pass link/path review and
  `git status --short`.
- Adapter auth and runbook implementation slices should add focused tests and
  avoid live benchmark artifacts unless explicitly requested.

## Phase 3: Desktop Django Workload

Add the first real coding-agent-shaped workload.

**Status:** started 2026-04-29 with the bundled `desktop-django-wrap` pack.
The first slice is prompt-only: two prompt-file-backed static chat cases ask for
concise wrapping plans. Prompt-file loading landed 2026-04-29 so longer static
prompts can live under pack-local `prompts/` directories. Static fixture
metadata loading and one portable synthetic `desktop-django-wrap` fixture
landed 2026-04-29. Case-level fixture refs landed 2026-04-30 as metadata-only
links from cases to top-level fixture ids. Fixture-backed prompt assembly for
referenced file fixtures landed 2026-04-30, appending file fixture contents to
loaded case prompts with stable delimiters while leaving directory fixtures
metadata-only. A compact pack-local synthetic Django repo snapshot directory
fixture landed 2026-04-30 as metadata only. Deterministic `regex` scoring and a
short fixed output skeleton for `desktop-django-wrap` landed 2026-04-30. A
docs-first repo-task contract design landed 2026-04-30, defining disposable
workspace, directory fixture, artifact, verifier, and mutation-isolation
semantics before implementation. Measured repo-task workspace preparation
landed 2026-05-01: each measured execution copies exactly one referenced
`kind = "repo"` directory fixture into `workspace/<case-id>/rep-NNN/` under the
run output directory, while repo-task warmups are rejected. Measured repo-task
workspace metadata landed 2026-05-01. Deterministic patch capture landed
2026-05-02: each measured repo-task execution writes
`patch/<case-id>/rep-NNN.diff` and records `patch.path`. Later Phase 3 slices
landed verifier execution, fenced model-output patch application, public
`fenced-patch` selection, public `external-agent` execution, direct-edit
external-agent variants, optional model-call summaries, and multiple bundled
repo-task packs. Remaining Phase 3 follow-up is now narrower: prompt
templating if needed, workspace cleanup/retention options, richer task
environment configuration, optional full agent-session replay, and larger
benchmark fixtures only when current evidence shows they are worth adding.
Measured repo-task
verifier execution and final verifier status landed 2026-05-02 for
`verify-script` rows only. A fixed-default runner-owned verifier subprocess
timeout landed 2026-05-02 so measured verifier hangs become completed failed
rows instead of runner hangs, and manifest-configurable verifier timeout via
`scoring.timeout_s` landed 2026-05-02 while preserving the `300.0` second
default. Manifest-configurable verifier environment support via
`scoring.environment` landed 2026-05-02 for measured `repo-task`
`verify-script` executions, overlaying string entries onto the inherited
verifier subprocess environment without adding CLI flags or result fields.
Deterministic no-op task log artifacts landed 2026-05-02: each measured
repo-task execution writes empty
`task/<case-id>/rep-NNN.stdout.log` and
`task/<case-id>/rep-NNN.stderr.log` files and records `task.stdout_path` and
`task.stderr_path`. Fenced model-output patch application landed 2026-05-02:
for measured repo-task executions, the runner extracts the first fenced `diff`
or `patch` block from model output, applies it as a unified diff inside the
prepared workspace, logs the task-phase outcome, then captures the
source-vs-workspace patch and runs any verifier. A 2026-05-09 follow-up added
an explicit path-marked full-file replacement fallback to the same fenced
executor. Full agent harness
integration and manifest task command execution remain planned. The first
bundled measured repo-mutating repo-task pack, `patch-from-failure`, landed
2026-05-02 as a narrow fixture/prompt/verifier slice over that fenced diff
contract. An internal repo-task task-executor boundary landed 2026-05-03 around
the existing fenced model-output patch phase, preserving behavior while keeping
full agent-session harness integration planned for a later slice. A docs-first
internal agent-session harness contract landed 2026-05-03, specifying the
future harness input shape, write boundaries, task log relationship, patch and
verifier ordering, and adapter/result boundary constraints without implementing
the harness or adding public manifest, CLI, adapter, artifact, or result schema
surface. The first narrow internal agent-session harness path landed
2026-05-03 behind `run_repo_task_executor`: runner-side callers can supply a
harness that receives the prepared workspace and deterministic task log paths,
mutates only the prepared workspace through validated helpers, writes the
existing task logs, and leaves patch capture, verifier execution, current CLI
defaults, adapter schemas, and result row shapes unchanged. A narrow internal
read-helper slice landed 2026-05-03 on the same request shape, giving harnesses
a validated workspace-relative UTF-8 text read helper alongside the existing
write helper without adding public harness selection or changing adapter/result
schemas. Internal workspace discovery helpers landed 2026-05-03: runner-side
harnesses can list deterministic sorted workspace-relative POSIX file paths and
check whether candidate regular files exist, still without public harness
selection, CLI flags, manifest fields, or adapter/result schema changes.
Symlinks to regular files are treated as file entries only when their targets
resolve inside the prepared workspace. An internal workspace file-delete helper
landed 2026-05-03: runner-side harnesses can remove existing regular files and
in-workspace symlink-to-file entries through the same workspace boundary, with
missing paths and directories returning false and unsafe paths remaining runner
failures before task logs are recorded. An internal workspace directory
discovery helper landed 2026-05-03: runner-side harnesses can list
deterministic sorted workspace-relative POSIX directory paths, including nested
directories created earlier in the same harness invocation, excluding the
workspace root, files, and symlinks including symlinks to directories. A
docs-first public harness selection contract landed 2026-05-03 without
implementation: future repo-task cases may explicitly declare
`harness = { id = "..." }`, absence keeps the current fenced `diff`/`patch`
executor default, and public selection must not change adapter schemas, result
row shapes, raw artifact paths, task log paths, patch/verifier ordering, or
repo-task warmup rejection by default. Narrow public manifest parsing and
executor routing for `harness = { id = "fenced-patch" }` landed 2026-05-03:
the loader accepts only that public id on `repo-task` cases, the CLI routes it
to the existing fenced model-output `diff`/`patch` executor, absence preserves
the same default, and external coding-agent harnesses remain future work. A
docs-first production external harness contract plus narrow task timeout
support landed 2026-05-03: future external harnesses must be explicit
case-local public `harness.id` values, adapter schemas and result rows stay
unchanged by default, and optional `harness.timeout_s` now bounds the
subprocess-backed fenced task executor without adding CLI flags or production
external coding-agent integration. A follow-on docs-first production external
harness contract refinement landed 2026-05-05 after the second fenced-patch
repo-task pack: it keeps the loader unchanged, treats `external-agent` as a
provisional documentation name only, enumerates future runner-owned harness
inputs, preserves existing adapter/raw/result/report boundaries, and defines the
external harness mutation, artifact, timeout, and failure boundaries for the
next implementation slice. The first narrow subprocess-backed external harness
skeleton landed 2026-05-05 behind the same repo-task executor boundary:
runner-side callers can provide explicit argv, the runner appends context
arguments, runs the subprocess without a shell in the prepared workspace,
captures existing task stdout/stderr logs, treats completed nonzero exits and
cleanly stopped timeouts as task outcomes, and leaves patch capture, verifier
execution, manifest parsing, CLI behavior, adapter schemas, raw paths, result
rows, compare/report behavior, and the default matrix unchanged. The public
`external-agent` parser-policy lock landed 2026-05-05: a named
`PROVISIONAL_EXTERNAL_AGENT_HARNESS_ID` constant is intentionally excluded from
`KNOWN_PUBLIC_HARNESS_IDS`, parser/CLI/executor tests reference that constant
directly, and the provisional id remains rejected at all three layers without
adding production external coding-agent execution. The first narrow public
`external-agent` repo-task harness slice then landed 2026-05-05: the loader now
accepts `harness = { id = "external-agent", timeout_s = ... }` on `repo-task`
cases, the CLI requires runner-owned `BENCHPACK_EXTERNAL_AGENT_ARGV` only when
such a case is selected, routes those cases to `ExternalProcessHarness`, and
keeps adapter schemas, raw paths, result rows, task log paths, patch/verifier
ordering, and fenced-patch defaults unchanged. The next narrow external-agent
context handoff slice landed 2026-05-06: public external-agent executions now
write `task/<case-id>/rep-NNN.context.json` with versioned runner-owned JSON
context and append `--context <path>` to the subprocess argv while preserving
the same adapter/result/report boundaries. The follow-up optional model-call
log path slice landed 2026-05-06: external-agent contexts now expose
`run.model_call_log_path` at
`task/<case-id>/rep-NNN.model-calls.jsonl` without requiring, parsing,
reporting, or adding that artifact to `run.jsonl`. The next recommended-shape
slice also landed 2026-05-06: docs and fake external-agent coverage now use
the minimal recommended JSONL line
`{"schema_version":1,"sequence":1,"model":"test-model","ok":true}` while
leaving the runner's treatment of the file optional and opaque until the later
safe summary slice. A deterministic reference external-agent harness example
also landed 2026-05-06 under
`examples/external-agent/`: it validates the public argv/context handoff,
mutates only the prepared workspace, writes one recommended model-call JSONL
line, and is covered through the public CLI external-agent path without adding
runner parsing, validation, result fields, reports, raw artifacts, manifest
commands, task environments, or production agent integration. The deterministic
model-call-shaped external-agent example then landed 2026-05-06 as
`examples/external-agent/model-call-agent.py`: it performs one tiny local HTTP
JSON request to an example-owned fake endpoint, writes the deterministic
response content only into the prepared workspace, writes one safe model-call
JSONL telemetry line to `run.model_call_log_path`, and is exercised through the
existing public CLI external-agent path while leaving runner schemas and
artifact parsing unchanged. The external-agent process-tree cleanup slice then
landed 2026-05-06: timed-out external subprocess harnesses now run in a POSIX
process group/session, receive bounded terminate-then-kill cleanup, preserve
captured task stdout/stderr plus deterministic timeout text, and remain task
outcomes when cleanup and log writing succeed. The safe model-call summary
slice then landed 2026-05-07: optional external-agent
`task/<case-id>/rep-NNN.model-calls.jsonl` artifacts remain outside
`run.jsonl`, but `summary.md` and `benchpack report` now parse only the
allowlisted recommended telemetry fields and render aggregate counts,
success/failure/error counts, labels, duration, and token totals while counting
unsafe lines without echoing their payloads.

Scope:

- Add a prompt-only `desktop-django-wrap` starter pack derived from the
  `desktop-django-starter` wrapping workflow. **Landed 2026-04-29.**
- Add static prompt-file support and move `desktop-django-wrap` prompts under
  `benchpacks/desktop-django-wrap/prompts/`. **Landed 2026-04-29.**
- Add top-level static `[[fixtures]]` manifest metadata with pack-relative file
  and directory path validation. **Landed 2026-04-29.**
- Add one synthetic portable `desktop-django-wrap` fixture under
  `benchpacks/desktop-django-wrap/fixtures/`. **Landed 2026-04-29.**
- Add case-level `fixture_refs` metadata that validates refs against top-level
  fixture ids in the same pack. **Landed 2026-04-30.**
- Add fixture-backed prompt assembly for referenced file fixtures, preserving
  directory fixtures as metadata-only refs. **Landed 2026-04-30.**
- Include a compact target-repo snapshot directory fixture. **Landed
  2026-04-30** as a pack-local static `repo` fixture referenced by existing
  cases but not copied, executed, injected into prompts, or used to mutate a
  repository.
- Define the repo-task disposable workspace contract before implementation.
  **Landed 2026-04-30** as documentation only: source repo fixtures are
  immutable; repo-task cases copy exactly one primary `kind = "repo"`
  directory fixture into a run-owned disposable workspace; mutation is isolated
  to that workspace; expected artifacts include workspace metadata, patch diff,
  task logs, verifier output, and final status; current directory fixtures
  remain metadata-only outside repo-task execution.
- Import or generate the `desktop-django-starter` resolved wrap prompt in a
  later slice after repo-task execution support starts.
- Add deterministic constraints for short output comparison. **Landed
  2026-04-30** with executable `regex` scoring and the
  `desktop-django-wrap` `DDS_WRAP_PLAN`/fixed-label output skeleton.
- Implement disposable directory copy for one pack-owned repo fixture per
  measured repo-task execution. **Landed 2026-05-01** as runner-owned
  workspace preparation at `workspace/<case-id>/rep-NNN/`, with exactly one
  referenced `kind = "repo"` directory fixture, source fixture immutability,
  separate measured repetition copies, destination-exists failures, and
  no adapter changes.
- Add a repo-task runner skeleton that prepares workspaces and records planned
  artifact paths without changing existing chat adapter behavior. **Partially
  landed** for workspace preparation and measured workspace metadata in
  `run.jsonl` on 2026-05-01, and measured patch artifact paths on 2026-05-02;
  verifier artifact paths and final verifier status landed later on
  2026-05-02; task execution log paths landed on 2026-05-02.
- Implement `verify-script` execution against the disposable workspace and
  record verifier artifacts. **Landed 2026-05-02** for measured `repo-task`
  executions only: scripts run as `sys.executable <pack-relative script>` after
  patch capture, stdout/stderr and structured JSON are written under
  `verify/<case-id>/rep-NNN.*`, and result rows include `verify`, `repo_task`,
  and top-level `verify-script` scoring.
- Add bounded verifier subprocess execution. **Landed 2026-05-02** for
  measured `repo-task` `verify-script` executions only: the runner uses a
  fixed default verifier timeout, records timeouts as completed failed measured
  rows, keeps verifier JSON/stdout/stderr artifact paths stable, writes
  `repo_task.verify_exit_code = null`, and marks timeout JSON with
  `timed_out` and `timeout_s`. Manifest-configurable verifier timeout via
  `scoring.timeout_s` also landed 2026-05-02, preserving the `300.0` second
  default when absent. CLI timeout flags and broader timeout policy remain
  planned; narrow task timeout later landed under `harness.timeout_s`.
- Add manifest-configurable verifier environment support. **Landed 2026-05-02**
  for measured `repo-task` `verify-script` executions only: optional
  `scoring.environment` is a validated string-to-string table in the effective
  scoring table, overlaid onto the inherited verifier subprocess environment
  when declared, and omitted from `run.jsonl` result rows. CLI environment
  flags, task environment configuration, shell expansion, templating, and
  secrets handling remain out of scope.
- Capture deterministic patch/diff artifacts from workspace changes. **Landed
  2026-05-02** as source-vs-workspace directory snapshot diffs written to
  `patch/<case-id>/rep-NNN.diff`, with `patch.path` recorded in measured
  repo-task rows.
- Extend result records conservatively for repo-task patch/verifier/log artifact
  paths and final status once the runner/verifier contract is implemented.
  **Partially landed 2026-05-02** for `patch.path`; verifier artifact paths and
  final verifier status also landed 2026-05-02 for `verify-script`; task log
  artifact paths landed 2026-05-02.
- Apply model output to the prepared workspace through a narrow explicit patch
  contract. **Landed 2026-05-02** for measured `repo-task` executions only: the
  runner uses the first fenced `diff` or `patch` block in adapter output as a
  unified diff, applies it inside the prepared workspace after the adapter call
  and before patch capture, writes task stdout/stderr logs, keeps rows
  completed for missing or unapplicable patches, and leaves the adapter boundary
  and result object shapes unchanged.
- Add explicit full-file replacement support to the fenced repo-task executor.
  **Landed 2026-05-09** as a narrow fallback inside the same first fenced
  `diff` or `patch` block: content beginning with
  `*** Begin File: <repo-relative-path>` and ending with `*** End File` writes
  only that validated workspace-relative UTF-8 file. Invalid replacement blocks
  are task outcomes with unchanged workspaces and deterministic task stderr.
- Introduce an internal repo-task task-executor boundary around the existing
  fenced model-output patch phase. **Landed 2026-05-03** without adding
  manifest fields, CLI flags, executor selection, task commands, task
  environment configuration, task timeout configuration, agent harness
  semantics, or result schema changes. Narrow task timeout later landed under
  the public harness table.
- Define the docs-first internal agent-session harness contract behind the
  repo-task executor boundary. **Landed 2026-05-03** as documentation only:
  future harness input may include the prepared workspace, case and pack
  metadata, model/adapter/endpoint/default context, output directory,
  repetition, and deterministic task log paths; writes are limited to the
  prepared workspace and run output directory; pack-owned fixtures, prompts,
  verifier scripts, source docs, adapter request/result schemas, existing
  artifact paths, and row shapes remain unchanged.
- Add the first narrow internal agent-session harness executor path behind the
  repo-task executor boundary. **Landed 2026-05-03** without adding manifest or
  CLI selection: runner-side callers can supply a harness to
  `run_repo_task_executor`; current CLI repo-task runs still use the fenced
  model-output `diff`/`patch` executor by default; task log paths and record
  shape remain unchanged; patch capture and verifier execution observe the
  harness-mutated prepared workspace.
- Add a validated internal workspace text read helper to
  `AgentSessionHarnessRequest`. **Landed 2026-05-03** without adding manifest
  or CLI selection: runner-side harnesses can read existing UTF-8 workspace
  files through the same path safety boundary used for workspace writes, while
  unsafe or unreadable paths remain runner failures before task logs are
  recorded.
- Add internal workspace discovery helpers to `AgentSessionHarnessRequest`.
  **Landed 2026-05-03** without adding manifest or CLI selection:
  `list_workspace_paths()` returns sorted POSIX regular-file paths under the
  prepared workspace, including files created earlier in the same harness
  invocation and in-workspace symlinks to regular files, and
  `workspace_file_exists(relative_path)` checks candidate files through the same
  path safety boundary as workspace reads and writes.
- Add an internal workspace file-delete helper to
  `AgentSessionHarnessRequest`. **Landed 2026-05-03** without adding manifest
  or CLI selection: `delete_workspace_file(relative_path)` removes existing
  regular files and in-workspace symlink-to-file entries through the same path
  safety boundary as workspace reads and writes, returns false for missing
  paths and directories, leaves symlink targets intact, and keeps unsafe paths
  or delete `OSError`s as runner failures before task logs are recorded.
- Add an internal workspace directory discovery helper to
  `AgentSessionHarnessRequest`. **Landed 2026-05-03** without adding manifest
  or CLI selection: `list_workspace_dirs()` returns sorted POSIX
  workspace-relative directory paths under the prepared workspace, including
  nested directories and directories created earlier in the same harness
  invocation, excluding the workspace root, files, and symlinks including
  symlinks to directories.
- Define a docs-first public harness selection contract. **Landed
  2026-05-03** as documentation only: a future explicit case-local
  `harness = { id = "..." }` table may select runner-known repo-task
  harnesses, absence keeps the fenced `diff`/`patch` executor as the
  compatibility default, selection is not inferred, and adapter schemas, result
  row shapes, task log paths, raw artifact paths, patch capture ordering,
  verifier ordering, and repo-task warmup rejection remain unchanged in this
  slice.
- Implement narrow public `fenced-patch` harness selection. **Landed
  2026-05-03** for `repo-task` cases only: manifests may declare
  `harness = { id = "fenced-patch" }`, the loader rejects malformed harness
  tables, unknown ids, extra keys, and harness declarations on non-`repo-task`
  cases, and the CLI routes explicit `fenced-patch` to the existing fenced
  model-output `diff`/`patch` executor. Absence keeps the same default fenced
  executor. No CLI flags, adapter schema changes, raw path changes, task log
  path changes, row-shape changes, task commands, task environment, task
  timeout, workspace retention, repo-task warmups, pack-level harness defaults,
  or external coding-agent integration were added.
- Define the docs-first production external harness contract and add narrow
  task timeout support. **Landed 2026-05-03** as one scoped slice: future
  production external harnesses are public repo-task harnesses selected by
  explicit case-local `harness.id`, never inferred from model, adapter,
  endpoint, fixture shape, verifier, host, or pack id. Normal adapter
  request/result schemas remain unchanged by default; harness-owned model calls
  are runner/harness concerns; task logs, raw paths, row shapes, patch capture
  after task execution, verifier execution after patch capture, source fixture
  immutability, and repo-task warmup rejection remain unchanged. The manifest
  now accepts `harness = { id = "fenced-patch", timeout_s = <positive number> }`
  for `repo-task` cases only. The timeout bounds the fenced executor's
  subprocess preflight and apply calls. Preflight timeout is a task outcome with
  unchanged workspace; apply timeout after preflight is a runner failure because
  partial mutation cannot be ruled out. Internal in-process harness callables
  reject task timeout.
- Refine the next production external harness contract after bundled
  fenced-patch coverage exists. **Landed 2026-05-05** as documentation only:
  no parser or executor behavior changed; `external-agent` is documented only as
  a provisional future id and remains rejected by the loader; future production
  harness inputs are runner-owned context such as prepared workspace, case and
  pack metadata, prompt text, output directory, repetition, task log paths,
  selected harness options, optional run metadata, and model/adapter/endpoint/
  defaults context when the harness owns model calls. External harnesses may
  mutate only the prepared workspace and write only existing task logs until a
  later artifact schema names more outputs. Existing adapter schemas, raw paths,
  result row shapes, compare/report behavior, patch capture after the task
  phase, verifier execution after patch capture, repo-task warmup rejection, and
  the default M4/M5 matrix remain unchanged.
- Add the first narrow subprocess-backed external harness runner skeleton.
  **Landed 2026-05-05** behind `run_repo_task_executor` without public manifest
  or CLI selection: runner-side callers can supply an explicit argv sequence,
  the runner appends prepared workspace, case, output directory, and repetition
  arguments, runs without `shell=True`, captures stdout/stderr to the existing
  task log paths, and keeps nonzero exits and cleanly stopped timeouts inside
  the existing task/verifier flow. Invalid harness combinations, unsafe argv,
  missing executables, invalid workspaces, and unwritable logs remain runner
  failures. At landing time, `external-agent` remained loader-rejected; the
  later public runnable slice below superseded that parser policy.
- Lock the public `external-agent` parser policy as loader-rejected.
  **Landed 2026-05-05** without changing executor or CLI behavior: a named
  `PROVISIONAL_EXTERNAL_AGENT_HARNESS_ID` constant lives alongside
  `PUBLIC_HARNESS_FENCED_PATCH` and is intentionally excluded from
  `KNOWN_PUBLIC_HARNESS_IDS`. Parser, CLI, and executor tests reference the
  constant directly: the parser error mentions both the provisional id and the
  implemented `fenced-patch` id; the CLI test proves manifest load fails before
  any adapter call or run-output directory is created; the executor test proves
  a stray `harness_id="external-agent"` raises `TaskError` without writing task
  logs and without mutating the prepared workspace. Existing fenced-patch
  defaults, internal in-process and runner-side subprocess harness paths,
  adapter schemas, raw paths, row shapes, patch/verifier ordering,
  compare/report behavior, and the default M4/M5 matrix remain unchanged. This
  policy was intentionally superseded by the following public runnable slice.
- Implement the first narrow public `external-agent` repo-task harness slice.
  **Landed 2026-05-05** with parser support for
  `harness = { id = "external-agent", timeout_s = <positive number> }` on
  `repo-task` cases, CLI loading of runner-owned
  `BENCHPACK_EXTERNAL_AGENT_ARGV` as a JSON array of non-empty strings, routing
  through the existing `ExternalProcessHarness` subprocess executor, and early
  missing/malformed argv failures before output directory creation or adapter
  calls. Direct executor `harness_id="external-agent"` remains rejected so the
  CLI owns public-to-internal routing. The normal adapter call still precedes
  the task harness phase, and no manifest command blobs, CLI task-command flags,
  task environments, raw artifact paths, result row fields, compare/report
  changes, workspace retention controls, repo-task warmups, or live benchmark
  artifacts were added.
- Add runner-owned public `external-agent` context input. **Landed 2026-05-06**
  as deterministic `task/<case-id>/rep-NNN.context.json` files plus appended
  `--context <path>` subprocess arguments. The context includes pack/case
  metadata, loaded prompt text, fixture/source workspace metadata, task log
  paths, optional run metadata path, and selected adapter/model/endpoint/
  defaults. It remains harness input only: no new manifest commands, CLI
  task-command flags, task environments, adapter fields, raw artifacts,
  `run.jsonl` fields, compare/report changes, or live benchmark artifacts were
  added.
- Expose an optional external-agent model-call log path. **Landed 2026-05-06**
  as `run.model_call_log_path` in the external-agent context, using the
  deterministic task artifact location
  `task/<case-id>/rep-NNN.model-calls.jsonl`. The runner does not pre-create,
  require, or add that file to `run.jsonl`; harness-owned model calls remain
  outside normal adapter `raw/` artifacts. Safe summary parsing/reporting for
  this optional artifact landed in the later 2026-05-07 slice below.
- Document a recommended external-agent model-call JSONL object shape. **Landed
  2026-05-06** as guidance and fake external-agent coverage only. The
  recommended minimal per-call line is
  `{"schema_version":1,"sequence":1,"model":"test-model","ok":true}`, with
  optional safe timing, adapter/endpoint label, token count, and short error
  fields. This did not add runner parsing, validation, summaries, reports,
  result schema fields, or normal adapter `raw/` artifacts for harness-owned
  calls, and it explicitly avoids recommending full prompts, full responses,
  request bodies, headers, environment variables, API keys, bearer tokens, or
  credentials in the default shape.
- Add a deterministic reference external-agent harness example. **Landed
  2026-05-06** as `examples/external-agent/reference-agent.py` plus usage docs
  and focused CLI coverage. The example reads the public context, validates
  core fields against the appended argv, writes only a small marker inside the
  prepared workspace and one recommended JSONL line at
  `run.model_call_log_path`, makes no live model calls, and left the runner's
  optional/opaque treatment of that file unchanged in this slice. Safe summary
  parsing/reporting landed later without changing `run.jsonl`.
- Add a deterministic model-call-shaped external-agent example. **Landed
  2026-05-06** as `examples/external-agent/model-call-agent.py` plus usage docs
  and focused CLI coverage. The example reads the public context, performs one
  stdlib local HTTP JSON request to an example-owned fake endpoint, sends only
  case id, repetition, and model, writes the deterministic response content
  only inside the prepared workspace, and writes one safe JSONL telemetry line
  at `run.model_call_log_path`. The runner did not parse, validate, summarize,
  report, or add that file to `run.jsonl` in this slice, and no adapter raw
  artifacts are created for harness-owned calls. Safe summary parsing/reporting
  landed later without changing `run.jsonl`.
- Add external-agent process-tree cleanup on timeout. **Landed 2026-05-06**
  for POSIX/macOS/Linux subprocess harnesses: external agents run in a new
  process group/session, timeout cleanup sends a bounded terminate signal and
  escalates to kill when needed, captured stdout/stderr is preserved in the
  existing task logs with deterministic timeout text, and cleaned-up timeouts
  remain task outcomes without adding result fields or task artifact paths.
- Add safe external-agent model-call telemetry summaries. **Landed
  2026-05-07** as a report-only parser for optional
  `task/<case-id>/rep-NNN.model-calls.jsonl` artifacts. It validates only the
  recommended allowlisted fields, counts invalid or unsafe lines without
  echoing their payloads, includes aggregate summaries in `summary.md` and
  `benchpack report`, and keeps model-call paths, full prompts, full
  responses, request bodies, headers, credentials, and all model-call payloads
  out of `run.jsonl`.
- Add explicit external-agent variants for the bundled coding-task workloads.
  **Landed 2026-05-07** as `patch-from-failure-external-agent`,
  `python-regression-fix-external-agent`, and
  `django-dashboard-regression-fix-external-agent`. The variants use the same
  fixtures and deterministic verifiers as their fenced-patch source packs but
  select the public `external-agent` harness with a 900 second task timeout.
  Their prompts now tell the external agent to edit the prepared workspace
  directly instead of emitting fenced patch output. They are exposed through
  the separate tmux helper pack set
  `coding-tasks-external-agent`; default fenced-patch pack behavior remains
  unchanged.
- Add a local Codex OSS wrapper for public external-agent live evidence.
  **Landed 2026-05-07** as `examples/external-agent/codex-oss-agent.py`. The
  wrapper validates the runner context, asks `codex exec --oss` to edit the
  prepared workspace directly through a local provider such as Ollama, and
  writes one safe model-call telemetry line without adding result fields.
- Record the first public external-agent live evidence. **Landed 2026-05-07**
  as an M5-only Codex OSS/Ollama run of the
  `coding-tasks-external-agent` pack set. The adapter, public harness path,
  tmux environment injection, metadata, and model-call telemetry all worked,
  but every verifier failed because the copied fenced-diff prompts caused the
  agent to emit unified diffs to stdout instead of editing the prepared
  workspace. Captured workspace diffs were empty. Treat this as mechanical
  harness validation plus benchmark-quality failure, not successful
  coding-agent task evidence.
- Record direct-edit external-agent live evidence. **Landed 2026-05-07** as a
  second M5-only Codex OSS/Ollama run of the same explicit pack set after the
  prompts changed to direct workspace editing. `fix-greeting` and
  `fix-task-summary` passed their deterministic verifiers with non-empty
  workspace diffs, while `fix-dashboard-regressions` failed with an empty
  workspace diff after Codex emitted only a plan. Treat this as meaningful
  exploratory coding-agent task signal, not default-matrix promotion.
- Add the first bundled measured repo-mutating repo-task pack over the fenced
  unified-diff contract. **Landed 2026-05-02** as `patch-from-failure`: one
  tiny Python repo fixture, one `fix-greeting` measured `repo-task` case,
  `defaults.warmup = 0`, `defaults.repetitions = 1`, a prompt that requires a
  fenced `diff` block, and a stdlib `verify-script` that checks the patched
  workspace. A second bundled fenced-patch repo-task pack,
  `python-regression-fix`, landed 2026-05-05 with a small stdlib Python
  task-summary fixture, multiple edge cases, and deterministic
  `verify-script` scoring. A stronger multi-file bundled fenced-patch
  repo-task pack, `django-dashboard-regression-fix`, landed 2026-05-07 with a
  stdlib dashboard-shaped fixture, visibility and archived-filtering
  regressions, deterministic sorting, input immutability checks, and
  `verify-script` scoring.
- Integrate a production agent-session harness after disposable workspace,
  verifier, patch artifacts, public compatibility selection, and the
  docs-first production external harness contract exist. **Partially landed**
  as an internal executor path for runner-side callers only, public
  `fenced-patch` selection for the existing compatibility executor, the
  2026-05-05 production external contract refinement, and a runner-side
  subprocess skeleton for deterministic external harness boundary tests, plus
  the first public `external-agent` CLI routing slice and optional model-call
  log artifact path, a recommended model-call JSONL line shape, and safe
  aggregate model-call summaries. The first local live external-agent evidence
  mechanically validated the public path but failed deterministically under
  copied fenced-diff prompts. External-agent-specific direct-edit prompts have
  now landed for the bundled variants, and the first M5 direct-edit validation
  passed two of three deterministic verifiers while classifying the dashboard
  case as a no-mutation task-quality failure. Required model-call logging
  beyond the optional summary artifact and richer harness configuration remain
  planned later.
- Add richer task status/reporting only if a real harness proves the existing
  task logs and runner-failure boundaries are insufficient. **Planned later.**
- Add repo-task warmup support, workspace cleanup/retention options, task
  environment support if needed, broader timeout/reporting policy if needed,
  and further larger repo-task packs if current bundled fixtures remain too
  small. **Planned later.**
- Add optional full agent-session replay later.

Validation:

- The pack runs on Apple Silicon and Linux without path-specific edits.

## Benchmark Design Research Track

Improve the coding-agent benchmark surface before launching broader live
campaigns. See `docs/benchmark-research.md` for research notes, source leads,
and caveats.

**Status:** opened 2026-05-07 as documentation/backlog only; the first
direct-edit external-agent prompt slice and local M5 real-agent validation
landed later the same day. No datasets were downloaded, and generated
`results/*`, metadata, raw payloads, workspaces, task logs, model-call logs,
patch artifacts, and verify artifacts remain local/ignored unless explicitly
curated.

Scope:

- Design external-agent-specific direct-edit task variants that remove
  fenced-diff output instructions while preserving the current default
  fenced-patch packs, result schemas, verifier behavior, adapter APIs, and
  tmux defaults. **Landed 2026-05-07** for the three existing external-agent
  coding-task packs by changing only their prompts, pack versions,
  descriptions, docs, and prompt-contract tests.
- Validate the direct-edit variants locally on M5 with a real external agent.
  **Landed 2026-05-07** with Codex OSS through local Ollama:
  `patch-from-failure-external-agent` and
  `python-regression-fix-external-agent` passed, while
  `django-dashboard-regression-fix-external-agent` failed from no workspace
  mutation. This is enough to justify exploratory broader direct-edit
  comparison, but not default matrix promotion.
- Add lightweight report/status polish for external-agent repo-task outcomes if
  larger campaigns become hard to classify manually. **Landed 2026-05-08** as a
  report-only `Repo-Task Outcomes` table in `summary.md` and
  `benchpack report`, derived from existing `repo_task`, scoring, and patch
  artifact data. The table shows patch byte counts and compact labels such as
  `passed`, `failed-no-mutation`, `failed-with-mutation`, and
  `failed-unknown-mutation` without changing `run.jsonl`.
- Add a simple endpoint-only coding correctness pack before promoting another
  cross-host correctness matrix. **Landed 2026-05-08** as
  `endpoint-python-correctness`, a normal-chat-adapter `repo-task` pack with a
  tiny committed Python inventory fixture, a fenced unified-diff prompt,
  default fenced-patch executor use, deterministic stdlib `verify-script`
  scoring, and a verifier-only edge dataset. **Replacement fallback landed
  2026-05-09** by accepting an explicit path-marked full-file replacement block
  inside the same fenced executor and bumping the pack to `0.2.0`. It requires
  no `external-agent`, avoids output-skeleton scoring, and is documented as the
  generic endpoint-only correctness signal. Adding it to tmux helper matrices
  or changing the recommended default matrix remains deferred after the first
  local M5 validation attempt failed from model output format rather than
  endpoint reachability, pending a new live validation of the revised contract.
- Research ProjDevBench-inspired project-level tasks where an agent builds or
  completes an executable project and deterministic execution scoring supplies
  detailed failure classes.
- Research product classification, product matching, and price-comparison
  style tasks where the coding agent writes a program or pipeline and the
  runner evaluates held-out F1, weighted F1, hierarchical F1, pairwise
  matching metrics, or cluster metrics.
- Research resource-aware scoring for agent-written programs: wall time, peak
  process memory, GPU memory when available, timeouts, memory-limit verdicts,
  runtime errors, compile errors, and whether those remain separate metrics or
  feed an explicit weighted score.
- Validate dataset candidates before implementation: license, access,
  attribution, size, task fit, train/test split design, offline
  reproducibility, and whether a small fixture can be committed or an external
  fetch step is required.

Validation:

- Documentation-only changes should pass `git diff --check`, link/path review,
  and `git status --short`.
- Do not run live benchmarks or download Kaggle, Hugging Face, WDC, or other
  datasets for this research track without explicit operator approval.

## Phase 4: Task Completion Benchmarks

Move beyond speed into correctness.

**Status:** started. The current bundled task-completion packs establish
fenced-patch repo-task plumbing and deterministic verifier behavior, including
the new `endpoint-python-correctness` endpoint-only pack for a small generic
correctness signal. Recent live evidence shows that fenced-diff prompts are too
prompt-contract-sensitive for broad coding-agent conclusions. The direct-edit
external-agent variants now have local M5 real-agent evidence with 2/3 verifier
passes, and lightweight task-outcome reporting polish has landed. The first
local M5 validation of `endpoint-python-correctness` reached Ollama but failed
because the model emitted replacement-file content instead of an applicable
unified diff. The revised `0.2.0` pack now explicitly supports a path-marked
replacement block fallback, but it still needs live endpoint validation before
it counts as endpoint-only correctness success. The next useful live slice is
broader direct-edit comparison as exploratory evidence; endpoint-only
helper/default matrix promotion remains deferred until a later successful
endpoint-correctness validation.

Scope:

- `patch-from-failure` pack. **Landed 2026-05-02** as the first bundled
  measured repo-mutating repo-task pack using fenced model-output diffs.
- `endpoint-python-correctness` pack. **Landed 2026-05-08** as a simple
  endpoint-only measured repo-mutating repo-task pack with a tiny stdlib
  inventory fixture, a normal chat-adapter fenced unified-diff prompt, a
  deterministic verifier with a hidden edge dataset, and no external-agent
  dependency.
- `python-regression-fix` pack. **Landed 2026-05-05** as a second bundled
  measured repo-mutating repo-task pack with a small stdlib Python regression,
  multiple deterministic edge cases, and the existing fenced unified-diff
  executor.
- `django-dashboard-regression-fix` pack. **Landed 2026-05-07** as a stronger
  bundled measured repo-mutating repo-task pack with a compact multi-file
  stdlib dashboard fixture, deterministic verifier checks, and the existing
  fenced unified-diff executor.
- Disposable worktree setup. **Landed** through measured repo-task workspace
  preparation and artifact recording.
- Model output to patch extraction. **Landed** through the default fenced
  unified-diff executor.
- Public external-agent harness plumbing. **Landed mechanically** through the
  public `external-agent` path and M5 Codex OSS/Ollama evidence. The initial
  copied prompts failed to produce workspace edits, while the later direct-edit
  prompts produced 2/3 verifier passes on the same local runtime family.
- Direct-edit external-agent benchmark variants. **Landed 2026-05-07** by
  updating the existing external-agent coding-task packs to instruct real
  agents to edit the prepared workspace directly while preserving the default
  fenced-patch packs and runner semantics.
- Local M5 direct-edit validation. **Landed 2026-05-07** with Codex
  OSS/Ollama: two direct-edit fixtures passed end to end and one larger
  dashboard fixture failed from no workspace mutation. Generated artifacts
  stayed local/ignored.
- Lightweight task-outcome reporting polish. **Landed 2026-05-08** as
  report-only repo-task outcome summaries in `summary.md` and
  `benchpack report`, making empty workspace diffs and mutation-visible
  failures visible before broader direct-edit campaigns.
- Universal endpoint-only correctness pack. **Landed 2026-05-08** as
  `endpoint-python-correctness`. Use it to separate "model can produce an
  applicable correct fix" from "an external agent stack is installed and
  operating." Keep `desktop-django-wrap` available as prompt-only
  coding-agent-shaped coverage rather than treating its regex skeleton as the
  main correctness benchmark. **Local M5 validation attempted 2026-05-08**
  with `qwen3-coder:latest` through Ollama: the endpoint and adapter worked,
  but the model returned replacement Python content inside a `diff` fence, the
  runner rejected it as a non-unified diff with no file paths, captured
  `patch_bytes=0`, and the verifier failed all visible and hidden checks
  against the unchanged fixture. **Replacement fallback landed 2026-05-09** as
  a deliberate path-marked full-file replacement block inside the fenced
  executor plus `endpoint-python-correctness` version `0.2.0`. Tmux-helper or
  default-matrix changes remain premature until that revised contract has live
  endpoint validation.
- Deterministic scoring by tests passing, timeouts, and resource use.
  **Partially landed** for verifier pass/fail and timeouts; resource-aware
  scoring for agent-written programs remains research/design work.

Validation:

- A baseline real external-agent/runtime pair can solve at least one
  direct-edit fixture end to end without relying on fenced-diff stdout.
  **Validated 2026-05-07** on local M5 with Codex OSS through Ollama.
- A baseline endpoint-only runtime should produce one applicable correct fenced
  diff or explicit replacement block for `endpoint-python-correctness` before
  the pack is promoted into helper/default matrices. **Attempted 2026-05-08**
  on local M5 with `qwen3-coder:latest` through Ollama; this failed against the
  original `0.1.0` diff-only contract as a model-output format issue with a
  meaningful deterministic verifier failure, not as an infrastructure blocker.
  The `0.2.0` replacement fallback needs a new live validation.

## Phase 5: Remote Host Orchestration

Make remote GPU runs practical.

**Status:** started. Authenticated OpenAI-compatible endpoint support in this
repo has landed through `openai-chat --openai-api-key-env`; the sibling
deployment repo has current SSH/inventory, service-shaped vLLM Gemma 4
readiness evidence, authenticated benchmark access, a live authenticated public
`smoke-chat`, strict same-GGUF CUDA `llama-server` preflight evidence, and
strict same-GGUF Hetzner four-pack evidence split across the smoke/runtime and
wrap/patch slices on 2026-05-07. The remaining remote-run blocker is not
runner capability; it is explicit operator scheduling for broader future
matrices beyond this completed strict-GGUF tri-host four-pack.

Scope:

- Document a manual remote workflow first.
- Add or document safe authentication for OpenAI-compatible remote endpoints
  without leaking bearer tokens into result artifacts.
- Optional SSH runner after local execution is stable.
- Artifact pullback from hosts such as `hetzner-gex44`.
- Host labels and result comparison across machines.

Validation:

- A run from a remote Linux CUDA host can be compared with a local Mac run.

## Operational Track: Result Registry And Community Submission

Make benchmark results searchable and shareable without weakening provenance or
comparability.

**Status:** started 2026-05-08. The first local SQLite registry import slice has
landed as `benchpack registry import --db <sqlite> <result-dir>...`, the first
compact public bundle slice has landed as
`benchpack registry bundle create/validate`, and the first comparability
indexing slice has landed as SQLite schema version `2`. A first registry-backed
report slice has also landed as `benchpack registry report --db <sqlite>`,
rendering the existing Markdown report medians, warnings, cache rows, and
`prefill parity` statuses from indexed rows and stored compact metadata. A
first static local site export has also landed as
`benchpack registry site --db <sqlite> --out <site-dir>`, writing
`index.html` and `report.md` from indexed compact rows. A first offline
received-bundle ingestion slice has also landed as
`benchpack registry bundle import --db <sqlite> <bundle-dir>...`. This
keeps the artifact-first workflow: local `results/<date>-<host-label>/`
directories, `run.jsonl`, `hardware.json`, `run-metadata.json`, and pack
manifests remain the canonical evidence. The database is an index over
validated result artifacts or validated compact bundles, and public bundles
are compact exports for sharing, not the only copy of benchmark truth.

Scope:

- Define a result-registry data model before choosing a hosted implementation.
  **Partially landed 2026-05-08** as local SQLite schema version `2`, with
  `runs`, `result_rows`, `result_case_stats`, and `registry_meta` tables. The
  schema captures result-directory identity, row count, `run.jsonl` SHA-256,
  pack ids/versions, adapters, models, endpoints, optional hardware/
  run-metadata JSON, selected host/runtime/model fields, normalized row timing/
  token/scoring/repo-task fields, compact sort-keyed row JSON, explicit
  comparability anchors from `run-metadata.json`, and per-run/case prompt/
  cached-token coverage medians. Hosted submitter/provenance metadata,
  artifact references beyond the canonical local result path, runner version,
  and endpoint-class normalization remain later work.
- Preserve raw and large artifacts outside the relational core. Store compact
  normalized rows in the database, keep optional `raw/`, `workspace/`,
  `patch/`, `task/`, `verify/`, and model-call artifacts in object storage or
  local artifact bundles, and reference them by content hash or immutable
  artifact id.
- Add a local import/index command before adding public submission. **Landed
  2026-05-08** as `benchpack registry import --db <sqlite> <result-dir>...`,
  which validates existing result directories and normalized rows, records the
  current registry schema version, indexes optional hardware and run metadata
  when present, rejects malformed rows or malformed optional metadata, replaces
  indexed rows on re-import of the same result directory, and avoids mutating
  benchmark outputs.
- Add an export/bundle format for public sharing. **Landed 2026-05-08** as
  `benchpack registry bundle create --out <bundle-dir> <result-dir>...` plus
  `benchpack registry bundle validate <bundle-dir>`. Version `1` bundles copy
  compact report-facing files only: `run.jsonl`, optional `hardware.json`,
  optional `run-metadata.json`, referenced patch diffs, and safe model-call
  JSONL logs only when every non-empty line is allowlisted telemetry. Raw
  payloads, workspaces, normal task logs, verifier artifacts, and unsafe
  model-call logs are omitted by default, with hashes and byte counts recorded
  for omitted regular files when available. Bundles require a provenance label
  (`self-reported`, `operator-curated`, or `independently-reproduced`) and
  validate offline with file hash checks, row/metadata validation, unlisted-file
  rejection, and a conservative secret scan. This is not yet public upload,
  moderation, object storage, or website ingestion.
- Add a local offline received-bundle import path before hosted upload/review.
  **Landed 2026-05-09** as
  `benchpack registry bundle import --db <sqlite> <bundle-dir>...`, which
  validates every compact bundle before opening SQLite, then imports bundled
  `runs/run-NNN-<label>/` directories through the same registry indexing path.
  The command preserves original run labels from the bundle manifest, uses the
  bundled compact run directory path as the registry identity key, writes only
  the requested SQLite database, and does not mutate bundle contents, require
  source result directories, read omitted raw/workspace/task/verify artifacts,
  contact endpoints, or create hosted review state.
- Design comparability rules as first-class database fields, not ad hoc UI
  filters. **First slice landed 2026-05-08** as nullable `runs` columns for
  explicit comparison mode, comparison boundary, host label/repo commit,
  runtime endpoint/options, model artifact repo/file/revision/checksum/
  quantization, and operating-condition notes, plus `result_case_stats` rows
  for prompt-token and cached-prompt-token coverage/median data. The registry
  now has structured inputs for artifact parity, runtime-and-format labeling,
  prompt/cache parity checks, pack-version filtering, and hardware/operating
  caveats without inferring missing metadata.
- Add registry-backed report reproduction before website views.
  **Landed 2026-05-08** as `benchpack registry report --db <sqlite>`, with
  optional repeated `--run-id` or `--label` filters. The command reads schema
  version `2` registry rows, reconstructs report inputs from
  `result_rows.raw_json`, `runs.hardware_json`, and `runs.run_metadata_json`,
  and reuses the existing report renderer so medians, warnings, cache rows,
  and `prefill parity` semantics match directory-backed reports. It does not
  require source result directories, mutate the database, read raw/workspace/
  task/verify artifacts, or contact endpoints. Artifact-only sections stay
  bounded: model-call summaries are omitted and repo-task patch byte counts
  render as unknown from registry-only data.
- Treat community submission as untrusted input. Public uploads should go
  through schema validation, size limits, secret scanning, content-type checks,
  duplicate detection, provenance labels, and moderation or review states
  before appearing in default leaderboards.
- Avoid a single leaderboard as the primary product. The first website should
  be a comparison explorer that lets users filter by pack, model artifact,
  runtime, quantization, host class, operating system, memory, cache settings,
  and provenance; it should separate throughput, latency, correctness, and
  resource metrics instead of collapsing them into one opaque score.
- Build the website in stages:
  - static or read-only generated reports over a local registry snapshot.
    **Landed 2026-05-09** as `benchpack registry site --db <sqlite> --out
    <site-dir>`, which writes a local `index.html` with run/case-metric tables
    plus `report.md` from existing registry-backed report rendering. It reads
    only SQLite schema version `2` compact rows, supports the same optional
    `--run-id` and `--label` selectors as registry report, refuses existing
    output paths unless `--force` is supplied, and does not read source
    artifacts, mutate the database, or contact endpoints.
  - authenticated upload/review for result bundles;
  - public browse and comparison views;
  - optional API for querying normalized results;
  - only later, richer submitter profiles, hardware catalogs, or maintained
    public leaderboards.
- Keep privacy boundaries explicit. Result bundles and the registry must not
  store bearer tokens, API keys, full private prompts, private repository
  contents, local absolute paths that identify users unnecessarily, or raw task
  logs by default. Any public raw-artifact sharing should be explicit opt-in.

Validation:

- A local registry import can round-trip existing result directories into a
  database and reproduce `benchpack report` medians and warnings.
  **Landed 2026-05-08** for local import/indexing, comparability stats, and
  registry-backed report rendering:
  focused tests cover metadata indexing, row normalization, idempotent
  re-import, malformed row rejection, malformed optional metadata rejection,
  CLI dispatch, schema-v1 upgrade, comparability-anchor indexing, and per-case
  prompt/cache/prefill median stats, plus registry report rendering without
  source artifacts and run-id/label selection.
- Imported rows retain enough provenance to explain whether two runs are
  comparable, partially comparable, or only useful as separate observations.
- A sample public bundle can be validated without network access and without
  leaking secrets. **Landed 2026-05-08** for directory bundles through
  `benchpack registry bundle validate`, focused tests for copied compact files,
  omitted raw hashes, unlisted-file rejection, and obvious secret rejection.
- A received compact public bundle can be validated and indexed into the local
  registry without source result artifacts and without partial writes on
  malformed multi-bundle input. **Landed 2026-05-09** through
  `benchpack registry bundle import`, with focused tests for original-label
  preservation, metadata indexing from bundled compact files, CLI dispatch, and
  all-input validation before database creation.
- The first web view can answer a concrete question such as "compare this
  model artifact across M4, M5, and RTX 4000 SFF Ada using the same pack and
  runtime family" without manual spreadsheet work.
