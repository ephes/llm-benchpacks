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

## 2026-05-07 (Gemma 4 M4 strict-GGUF preflight)

### Changed

- Preserved the dirty M4 Studio `/Users/jochen/projects/llm-benchpacks`
  working tree in git stash `pre-gemma4-m4-sync-20260507`, then fast-forwarded
  the M4 repo to `a82fb3f` (`Record Gemma 4 M5 four-pack matrix`) so the M4
  preflight used the same source commit as the local M5 checkpoint.
- Downloaded the same pinned
  `bartowski/google_gemma-4-E2B-it-GGUF` revision
  `b5e99bd964eaacc27ba484bb2eb3e9f6160b9143`, file
  `google_gemma-4-E2B-it-Q4_K_M.gguf`, on the M4 Studio and verified SHA-256
  `b5310340b3a23d31655d7119d100d5df1b2d8ee17b3ca8b0a23ad7e9eb5fa705`.
- Started M4 `/opt/homebrew/bin/llama-server` version `9030 (a09a00e50)` on
  `127.0.0.1:8081` only, with alias `gemma4-e2b-q4km`, the same
  context/cache/batch settings as M5, and `--reasoning off`. The server loaded
  successfully, offloaded 36/36 layers to Metal, logged `thinking = 0`, and
  exposed the alias through `/v1/models`.
- Ran exactly one M4 `benchpack run smoke-chat --adapter openai-chat`. It
  passed with `ok=true`, `scoring.passed=true`, `finish_reason=stop`, normal
  content `The capital of France is Paris.`, no `reasoning_content`, no
  visible template/tool/EOG leakage, and prompt/output/cached tokens 21/8/0.
- Because smoke passed, ran exactly one M4 `benchpack run runtime-sweep
  --adapter openai-chat`. It wrote 9 measured rows, all `ok=true`, scoring mode
  `none`, with warmup artifacts excluded from `run.jsonl`. Streaming usage was
  accepted, TTFT and usage-derived timing/token fields were present, sampled
  responses had normal content with no observed `reasoning_content` or
  template/tool/EOG leakage, and server logs showed `truncated = 0` for the
  measured requests. Median total TPS by case was 135.58 short, 136.38 medium,
  and 138.35 long; median TTFT was 24.5 ms, 25.8 ms, and 13.9 ms respectively.
- Stopped the M4 server after the runtime-sweep and confirmed no listener on
  TCP port 8081 and no matching `llama-server.*gemma4-e2b-q4km` process.
  Pulled back only compact smoke/runtime artifacts (`run.jsonl`, `summary.md`,
  `hardware.json`, and `run-metadata.json`) plus ignored
  `metadata/m4-gemma4-llama-server.json`; remote `raw/` payloads stayed on the
  M4 Studio and generated results remain ignored.

### Open Questions

- M4 checksum/load/smoke/runtime-sweep now pass for the selected strict-GGUF
  `llama-server --reasoning off` configuration, so an M4 four-pack matrix is
  the next Apple-lane step if the campaign wants parity with the local M5
  matrix.
- The local M5 `patch-from-failure` verifier failure remains a
  model/task-quality blocker for the tiny repo-task pack, not a serving or
  adapter blocker.
- Hetzner remains separate and blocked by deployment-side GPU-driver/service
  recovery, exclusive-GPU full-card Gemma 4 serving preflight, same-GGUF
  llama.cpp parity, and authenticated benchmark access.

## 2026-05-07 (Hetzner Gemma 4 progress recheck)

### Changed

- Rechecked the sibling `llm-node-bare` repo and the live
  `root@llm.django-cast.com` host with read-only SSH commands. The host is
  reachable, `llm`, `llm-mgmt`, and `caddy` are active/enabled, the resident
  Qwen2.5 still serves locally, management `/healthz/` and `/readyz/` return
  HTTP 200, and public unauthenticated `/v1/models` returns HTTP 401.
- Confirmed the live GPU inventory: NVIDIA RTX 4000 SFF Ada Generation,
  20,475 MiB VRAM, driver 580.126.09, with the resident Qwen2.5 service using
  about 16.1 GiB VRAM and about 3.9 GiB free at recheck time.
- Confirmed sibling deployment progress: an isolated
  `/opt/llm/lnb007-gemma4-vllm-cu129` runtime imports Gemma 4 support with
  vLLM 0.20.1, Transformers 5.8.0, Torch 2.11.0+cu129, and CUDA 12.9; the
  pinned `google/gemma-4-E2B-it` snapshot is cached under the isolated cache
  layout. Updated backlog/readiness docs to make the next Hetzner item an
  exclusive-GPU full-card E2B load preflight, not a benchmark run.
- A later same-day post-`apt dist-upgrade` health gate in the sibling repo
  blocked that preflight before any Gemma 4 process was launched: `nvidia-smi`
  fails with `Failed to initialize NVML: Driver/library version mismatch`,
  `llm.service` is stuck in `activating (auto-restart)`, local Qwen2.5
  `/v1/models` is down, management `/readyz/` reports
  `backend_available: false`, and public unauthenticated `/v1/models` still
  returns HTTP 401.

### Open Questions

- Hetzner Gemma 4 serving readiness first needs operator-approved GPU-driver
  recovery and a healthy Qwen2.5 baseline again. Only then should LNB-008 stop
  the current `llm` service for an exclusive-GPU full-card preflight with
  temporary local-only vLLM on `127.0.0.1:18007`.
- Authenticated public benchmark credentials remain a deployment-side procedure
  item even though `llm-benchpacks` already supports
  `--openai-api-key-env`.
- Local M5 `runtime-sweep` remained an independent gate at the time of this
  Hetzner recheck; the follow-up same-day local M5 entry below records that
  result. M4 checksum/load/smoke and Hetzner full-card serving preflight remain
  independent gates before any meaningful M4/M5/Hetzner comparison matrix.

## 2026-05-07 (Gemma 4 local M5 runtime-sweep with reasoning off)

### Changed

- Ran exactly one local M5 `benchpack run runtime-sweep` against
  `gemma4-e2b-q4km` on `http://127.0.0.1:8081/v1`, using the selected
  strict same-GGUF `llama-server` command with `--reasoning off` and ignored
  `metadata/m5-gemma4-llama-server.json`.
- The run completed successfully with 9 measured rows, matching the expected
  3 cases x 3 repetitions. Warmup requests produced raw artifacts but no
  measured rows, all measured rows had `ok=true`, scoring was `none`, TTFT and
  usage-derived token/timing fields were present, and
  `stream_options.include_usage=true` was accepted.
- Sampled raw responses contained normal assistant content, no observed
  `reasoning_content`, and no visible template, tool, or EOG leakage. The
  stored streaming response aggregate does not expose `finish_reason`, but the
  server logs showed HTTP 200 requests ending with `truncated=0` rather than a
  length-stop pattern.
- Recorded the compact result in ignored local metadata and left
  `results/2026-05-07-m5-max-gemma4-llama-reasoning-off-runtime/` ignored and
  uncommitted. No four-pack matrix, M4 work, Hetzner work, SSH command,
  sibling-repo work, non-loopback endpoint call, or additional runtime was
  performed.

### Open Questions

- The tested local M5 strict-GGUF `llama-server --reasoning off`
  configuration supported proceeding to a local M5 four-pack matrix through the
  normal metadata/tmux dry-run workflow; the follow-up same-day entry below
  records that matrix result.
- M4 strict-GGUF checksum/load/smoke parity remains the next Apple-lane gate,
  while Hetzner remains blocked by deployment-side GPU-driver/service recovery,
  exclusive-GPU Gemma 4 serving preflight, and authenticated benchmark access.

## 2026-05-07 (Gemma 4 local M5 four-pack matrix)

### Changed

- Started the selected local M5 `gemma4-e2b-q4km` GGUF through
  `/opt/homebrew/bin/llama-server` on `127.0.0.1:8081` with the validated
  `--reasoning off` command, rendered the default four-pack tmux dry run, and
  launched exactly one local M5 matrix for `smoke-chat`, `runtime-sweep`,
  `desktop-django-wrap`, and `patch-from-failure`.
- All four `benchpack run` commands exited 0 and wrote ignored result
  directories under
  `results/2026-05-07-m5-max-gemma4-llama-reasoning-off-4pack-20260507-1012-*`.
  `smoke-chat` passed `contains`, `runtime-sweep` wrote 9/9 `ok=true`
  unscored rows, and both `desktop-django-wrap` rows passed regex scoring.
- `patch-from-failure` reached the endpoint and wrote one `ok=true` row, but
  `verify-script` scoring failed. The model returned a fenced diff, but it
  targeted a class-based `greeter.py` shape that did not match the fixture;
  `git apply --check` rejected the patch, the workspace stayed unchanged, and
  the verifier saw `Hello Ada.` instead of `Hello, Ada!`.
- Recorded the compact matrix result in ignored local metadata, stopped the
  server, and removed the tmux session. No M4 work, Hetzner work, SSH command,
  sibling-repo work, endpoint outside loopback, second runtime, or generated
  result curation was performed.

### Open Questions

- The selected local M5 strict-GGUF `llama-server --reasoning off`
  configuration is runtime-ready for the four-pack workflow, but the tiny
  repo-task pack is a local model/task-quality blocker for this artifact.
- Decide whether the `patch-from-failure` failure is acceptable signal for the
  campaign, should be retried under the same strict local M5 setup, or should
  be compared against M4 after strict-GGUF M4 preflight.
- M4 strict-GGUF checksum/load/smoke parity remains the next Apple-lane gate,
  while Hetzner remains blocked by deployment-side GPU-driver/service recovery,
  exclusive-GPU Gemma 4 serving preflight, and authenticated benchmark access.

## 2026-05-06 (Gemma 4 local M5 smoke-chat with reasoning off)

### Changed

- Retried exactly one local M5 `benchpack run smoke-chat` against
  `gemma4-e2b-q4km` on `http://127.0.0.1:8081/v1`, with the selected
  `llama-server` GGUF command plus `--reasoning off` and ignored
  `metadata/m5-gemma4-llama-server.json`.
- The measured row passed: `ok=true`, `scoring.passed=true`,
  `finish_reason=stop`, normal assistant content
  `The capital of France is Paris.`, no `reasoning_content`, and token counts
  of 21 prompt, 8 output, and 0 cached prompt tokens.
- Recorded the compact result in ignored local metadata and left the generated
  `results/2026-05-06-m5-max-gemma4-llama-reasoning-off-smoke-20260506-2124/`
  directory ignored and uncommitted. No `runtime-sweep`, benchmark matrix, M4
  work, Hetzner work, SSH command, sibling-repo work, or non-loopback endpoint
  call was performed.

### Open Questions

- The local M5 smoke-chat scoring blocker is resolved for the selected strict
  same-GGUF candidate when `llama-server` is started with `--reasoning off`.
- A local M5 `runtime-sweep` remains a separate explicit next slice; do not
  infer four-pack matrix readiness from this single-pack smoke.
- M4 and Hetzner strict same-GGUF checksum parity, `llama-server` support,
  comparable runtime options, memory fit, token provisioning, SSH/inventory,
  and serving readiness remain unresolved.

## 2026-05-06 (Gemma 4 local M5 thinking-control smoke)

### Changed

- Started the selected local M5 `gemma4-e2b-q4km` GGUF through
  `/opt/homebrew/bin/llama-server` on loopback with the previous conservative
  context/cache/batch settings plus exactly one thinking-control override:
  `--reasoning off`.
- `llama-server` loaded successfully and logged `thinking = 0` for the Gemma 4
  chat template. A single direct non-streaming `/v1/chat/completions` request
  using the bundled `smoke-chat` France prompt, `temperature=0`,
  `max_tokens=64`, and `stream=false` returned HTTP 200, valid JSON, normal
  assistant content `The capital of France is Paris.`, no
  `reasoning_content`, and `finish_reason=stop`.
- Recorded the compact direct-smoke observation in ignored
  `metadata/m5-gemma4-llama-server.json`, stopped the server, and deliberately
  did not run `benchpack run`, `runtime-sweep`, a benchmark matrix, M4 work,
  Hetzner work, SSH commands, or non-loopback endpoint calls.

### Open Questions

- A future local M5 `benchpack run smoke-chat` retry should use the same
  `llama-server` command with `--reasoning off` before launching
  `runtime-sweep` or the four-pack matrix.
- `--reasoning-budget 0` remains untested in this slice because
  `--reasoning off` resolved the direct 64-token smoke behavior.
- M4 and Hetzner strict same-GGUF checksum parity, `llama-server` support,
  comparable runtime options, memory fit, token provisioning, SSH/inventory,
  and serving readiness remain unresolved.

## 2026-05-06 (Gemma 4 local M5 benchpack smoke-chat)

### Changed

- Ran exactly one local M5 `benchpack run smoke-chat` against the selected
  `gemma4-e2b-q4km` alias on `http://127.0.0.1:8081/v1`, with
  `--run-metadata metadata/m5-gemma4-llama-server.json`.
- The `openai-chat` adapter reached the local `llama-server` endpoint and
  wrote one measured row with `ok=true`, but bundled `smoke-chat` scoring
  failed because the response spent the full `max_tokens=64` completion budget
  on `reasoning_content`, returned empty normal assistant content, and did not
  contain `Paris`.
- Recorded the compact smoke result in ignored local metadata and left the
  generated `results/2026-05-06-m5-max-gemma4-llama-20260506-2044-smoke/`
  directory ignored and uncommitted. The server was stopped after the run. No
  benchmark matrix, M4 work, Hetzner work, SSH command, sibling-repo work, or
  non-loopback endpoint call was performed.

### Open Questions

- Gemma 4 thinking behavior needs a deliberate serving, prompt, adapter, or
  token-budget strategy before running `runtime-sweep` or the four-pack matrix
  with this local `llama-server` configuration.
- Local `llama-server --help` exposes untested candidate controls such as
  `--reasoning off`, `--reasoning-budget 0`, `--chat-template-kwargs`, and
  `--reasoning-format`; a future narrow slice should validate one of those
  before retrying benchmark packs.
- M4 and Hetzner strict same-GGUF checksum parity, `llama-server` support,
  comparable runtime options, memory fit, token provisioning, SSH/inventory,
  and serving readiness remain unresolved.

## 2026-05-06 (Gemma 4 local M5 chat-completions smoke)

### Changed

- Started the already-selected local M5
  `bartowski/google_gemma-4-E2B-it-GGUF` E2B Q4_K_M artifact through
  `/opt/homebrew/bin/llama-server` on loopback with alias
  `gemma4-e2b-q4km` and the previously captured conservative context/cache/
  batch settings.
- Sent one direct non-streaming `/v1/chat/completions` request to
  `http://127.0.0.1:8081/v1` without running `benchpack run`; the endpoint
  returned HTTP 200, valid chat-completion JSON, and exact
  `GEMMA4_SMOKE_OK` content without visible template, tool, thinking, or EOG
  leakage.
- Sent one tiny streaming compatibility request with
  `stream_options.include_usage=true`; the endpoint accepted it and returned a
  final usage chunk, so future `openai-chat` runs can keep the default
  `--openai-stream-usage include` for this local server.
- Recorded the direct smoke observations in ignored
  `metadata/m5-gemma4-llama-server.json`. No `benchpack run`, benchmark
  matrix, M4 work, Hetzner work, SSH command, endpoint call outside local
  loopback, or generated `results/*` artifact was produced.

### Open Questions

- The tiny streaming request emitted only `reasoning_content` chunks before
  `finish_reason=length`, so Gemma 4 thinking behavior may consume an entire
  very small streaming token budget before any normal content is emitted, even
  though include-usage compatibility is confirmed.
- M4 and Hetzner strict same-GGUF checksum parity, `llama-server` support,
  comparable runtime options, memory fit, token provisioning, SSH/inventory,
  and serving readiness remain unresolved.
- A full `benchpack run smoke-chat` and any four-pack matrix still require
  explicit authorization.

## 2026-05-06 (Gemma 4 local M5 GGUF preflight)

### Changed

- Downloaded exactly the first strict same-GGUF candidate,
  `bartowski/google_gemma-4-E2B-it-GGUF` revision
  `b5e99bd964eaacc27ba484bb2eb3e9f6160b9143`, file
  `google_gemma-4-E2B-it-Q4_K_M.gguf`, to the local Hugging Face cache for M5
  preflight.
- Captured local SHA-256
  `b5310340b3a23d31655d7119d100d5df1b2d8ee17b3ca8b0a23ad7e9eb5fa705` and
  recorded it in ignored metadata.
- Verified that local `/opt/homebrew/bin/llama-server` version
  `9030 (a09a00e50)` can load the selected GGUF on loopback with alias
  `gemma4-e2b-q4km`, `--ctx-size 8192`, `--batch-size 1024`,
  `--ubatch-size 512`, f16 KV cache types, `--gpu-layers auto`, and
  `--parallel 1`.
- Recorded load behavior, tokenizer/chat-template observations, and local idle
  memory notes in `metadata/m5-gemma4-llama-server.json`, which remains ignored
  and local by default.
- Ran only the `scripts/benchpack-tmux-matrix --dry-run` render for the local
  M5 Gemma 4 alias. No benchmark matrix, `benchpack run`, M4 work, Hetzner
  work, SSH commands, endpoint calls, or generated `results/*` artifacts were
  produced.
- Updated `docs/gemma4-tri-host-runbook.md` with the durable M5 preflight
  status while keeping M4 and Hetzner checksum/load/memory-fit blockers open.
- Updated `docs/implementation-plan.md` so the Gemma 4 operational track now
  records the local M5 first-candidate preflight as landed while leaving
  chat-completion smoke, M4/Hetzner parity, token provisioning, SSH/inventory,
  and serving readiness open.

### Open Questions

- Chat-completion output formatting remains unresolved until a single smoke
  call is explicitly authorized; the preflight used only load logs and
  `/v1/models`.
- M4 and Hetzner strict same-GGUF checksum parity, `llama-server` support,
  comparable runtime options, and memory fit remain unverified.
- Hetzner token provisioning, SSH/inventory, serving readiness, and checksums
  for alternative Gemma 4 artifacts remain separate follow-ups.

## 2026-05-06 (Gemma 4 artifact verification and catalog table)

### Changed

- Updated `docs/model-targets.md` with a verified Gemma 4 artifact table based
  on current primary sources: Google announcement/model pages, Hugging Face
  model and repo metadata, Transformers Gemma4 docs, vLLM supported-models and
  Gemma 4 recipe docs, ggml-org/bartowski/Unsloth GGUF repos, official Ollama
  tags, and mlx-community MLX conversion repos.
- Resolved the previous placeholder IDs as real public Hugging Face repos:
  `google/gemma-4-E2B-it` and `google/gemma-4-E4B-it`, with Apache 2.0 license
  metadata, non-gated HF API state, and immutable repo revision guidance.
- Recorded exact small-target GGUF and MLX artifact candidates, including the
  first strict same-GGUF dry-run candidate
  `bartowski/google_gemma-4-E2B-it-GGUF` file
  `google_gemma-4-E2B-it-Q4_K_M.gguf`, plus upstream ggml-org and Unsloth
  alternatives, official Ollama Q4_K_M tags, and MLX Community 4-bit
  conversions.
- Aligned `docs/gemma4-tri-host-runbook.md` with the verified catalog while
  keeping endpoint values, hostnames, checksums, runtime versions, context/cache
  options, memory fit, and live run status as placeholders.
- Marked the catalog/runbook artifact verification slice as landed in
  `docs/implementation-plan.md`. No live benchmarks, endpoint calls, SSH
  commands, model downloads, or generated `results/*` artifacts were produced.

### Open Questions

- Post-download checksums, exact local `llama-server`/Ollama/MLX/vLLM load
  behavior, tokenizer/chat-template behavior through each server, and memory fit
  still need preflight validation before launch.
- Hetzner token provisioning, live SSH/inventory verification, and serving
  readiness remain operational blockers tracked outside this repo slice.

## 2026-05-06 (Gemma 4 tri-host runbook and comparison mode)

### Changed

- Added `docs/gemma4-tri-host-runbook.md` for M4, M5, and Hetzner Gemma 4
  campaign planning without running live benchmarks.
- Selected strict same-GGUF parity through `llama-server` on all three hosts as
  the primary first campaign mode, subject to artifact, runtime, and memory-fit
  validation.
- Documented the secondary service-shaped Apple-vs-Hetzner path as
  runtime-and-format evidence, not strict artifact parity.
- Added placeholder-only metadata examples for M5, M4, Hetzner
  `llama-server`, and optional Hetzner vLLM, including runtime command,
  artifact, quantization, checksum, endpoint, auth env var name, context/cache,
  power, thermal, background load, and comparison mode fields.
- Extended `scripts/benchpack-tmux-matrix` with
  `--openai-api-key-env <ENV_NAME>` as a dry-run/testable pass-through to
  generated `benchpack run` commands. The helper does not read token values.
- Updated the README, Apple Silicon runbook, model target catalog,
  implementation plan, and architecture helper boundary notes. No live
  benchmarks were run and no generated `results/*` artifacts were produced.

### Open Questions

- Exact Gemma 4 artifact IDs, revisions, quantization filenames, checksums,
  license gates, MLX/GGUF/vLLM support, and memory fit still need validation.
- Hetzner token provisioning, SSH/inventory verification, and Gemma 4 serving
  readiness remain operational blockers before any live tri-host campaign.

## 2026-05-06 (authenticated openai-chat endpoints)

### Changed

- Added explicit `benchpack run --openai-api-key-env <ENV_NAME>` support for
  `openai-chat` so authenticated OpenAI-compatible endpoints can receive
  `Authorization: Bearer <token>` headers.
- The token is read only from the named environment variable when that option
  is supplied. Unauthenticated local endpoint behavior remains the default, and
  the runner does not implicitly read `OPENAI_API_KEY`.
- Preserved the existing result row shape, raw request/response body artifacts,
  `--openai-stream-usage include|omit` behavior, compare/report behavior, and
  manifest syntax. Raw request files remain JSON request bodies only and do not
  include HTTP headers.
- External-agent context and adapter defaults may contain the configured
  environment variable name, but never the resolved bearer token value. Missing
  or empty configured env vars fail deterministically without logging a token.
- No live benchmarks were run and no generated `results/*` artifacts were
  produced.

### Open Questions

- Hetzner token provisioning, live SSH/inventory verification, and Gemma 4
  serving readiness remain operational prerequisites before the next live
  tri-host benchmark campaign.

## 2026-05-06 (external-agent process-tree timeout cleanup)

### Changed

- Replaced direct timeout handling for runner-owned external subprocess
  harnesses with POSIX process-group cleanup: external agents start in a new
  process group/session, timeout handling sends a bounded terminate signal, and
  escalates to kill when processes do not exit.
- Preserved existing external-agent task logs, deterministic timeout stderr
  text, patch capture, verifier ordering, direct executor rejection of
  `harness_id="external-agent"`, public CLI argv/context behavior, and
  `run.jsonl` row shape.
- Added executor coverage proving a child process that ignores `SIGTERM` does
  not survive an external harness timeout and that pre-timeout workspace
  mutation still reaches patch capture.

### Open Questions

- Richer task status/reporting, named harness artifacts, required model-call
  logging, task environments, and production coding-agent integration remain
  separate future slices.

## 2026-05-06 (model target catalog and Gemma 4 tri-host planning)

### Changed

- Added `docs/model-targets.md` as the source-controlled catalog for current
  preferred model targets, artifact-parity notes, and revisit cadence.
- Recorded Gemma 4 as the preferred current small-model planning target for a
  future M4/M5/Hetzner slice, while retaining Qwen3.6 as the continuity target
  for explicit Qwen M4/M5 comparisons and existing curated results.
- Added backlog items in the implementation plan for authenticated
  OpenAI-compatible endpoint support, Gemma 4 tri-host runbook work, parity
  mode selection, runtime/artifact validation, and live Hetzner inventory
  verification through the sibling deployment repo.
- Coordinated with the sibling `llm-node-bare` planning shift to a Markdown
  backlog in that repo's `docs/backlog.md`, including LiteLLM removal or
  justification as deployment-side work.
- No live benchmarks were run and no generated `results/*` artifacts were
  produced.

### Open Questions

- Exact Gemma 4 artifacts, revisions, quantizations, MLX/GGUF/Ollama/vLLM
  support, license gates, and memory fit still need validation before launch.
- The first Gemma 4 tri-host comparison still needs an explicit choice between
  strict same-GGUF parity and an operational runtime-and-format comparison.
- The public Hetzner endpoint currently requires authentication, and
  `openai-chat` still needs a safe Authorization header path before it can be
  used directly.

## 2026-05-06 (external-agent deterministic model-call example)

### Changed

- Added `examples/external-agent/model-call-agent.py` as a deterministic,
  offline, production-shaped external-agent example that reads the public
  context, performs one stdlib HTTP JSON request to an example-owned local fake
  endpoint, mutates only the prepared workspace from the deterministic
  response, and writes one safe model-call JSONL line to
  `run.model_call_log_path`.
- Added focused CLI coverage that runs the source-controlled example through
  `BENCHPACK_EXTERNAL_AGENT_ARGV`, verifies the normal adapter call still
  happens before the external task phase, proves the local fake endpoint sees
  exactly one tiny safe request, and preserves patch capture, verifier
  execution, source fixture immutability, and existing result row shape.
- Updated example and project docs to make both external-agent examples
  discoverable while keeping the model-call log optional, harness-owned, and
  opaque to the runner. No runner parsing, validation, summaries, reports,
  `run.jsonl` fields, adapter raw artifacts for harness-owned calls, manifest
  command syntax, task environments, or live benchmark artifacts were added.
- Review follow-up tightened `model-call-agent.py` so `--model-call-url` must
  point at a plain HTTP loopback host and must not contain credentials or query
  strings.

### Open Questions

- Real production harnesses may still prove a need for enforced model-call
  telemetry schema, richer task status, named harness artifacts, or
  process-tree cleanup policy in later slices.

## 2026-05-06 (external-agent reference harness example)

### Changed

- Added `examples/external-agent/reference-agent.py` as a deterministic local
  reference harness for the public `external-agent` subprocess and context
  handoff.
- The example validates core context fields against the appended argv, mutates
  only the prepared workspace by writing a small marker file, and writes one
  recommended model-call JSONL line to `run.model_call_log_path` without making
  live model calls.
- Added example usage documentation and focused CLI coverage that runs the
  source-controlled example through `BENCHPACK_EXTERNAL_AGENT_ARGV`, preserving
  adapter-before-task ordering, patch capture, verifier execution, and the
  existing result row shape.
- Kept the model-call log optional, harness-owned, and opaque to the runner:
  no parsing, validation, summaries, reports, `run.jsonl` fields, adapter
  schema changes, normal `raw/` artifacts, manifest command syntax, task
  environments, or production agent integration were added.

### Open Questions

- Real production harnesses may still prove a need for enforced model-call
  telemetry schema, richer task status, named harness artifacts, or process-tree
  cleanup policy in later slices.

## 2026-05-06 (external-agent recommended model-call JSONL shape)

### Changed

- Documented a recommended, non-enforced JSONL object shape for public
  `external-agent` model-call logs written to the context-provided
  `task/<case-id>/rep-NNN.model-calls.jsonl` path.
- Recommended the minimal per-call line
  `{"schema_version":1,"sequence":1,"model":"test-model","ok":true}`, with
  optional safe timing, adapter/endpoint label, token count, and short error
  fields.
- Kept the artifact optional, harness-owned, and opaque to the runner. The
  runner still does not pre-create, require, validate, parse, summarize,
  report, or add the file to `run.jsonl`, and harness-owned calls remain
  outside normal adapter `raw/` request/response artifacts.
- Added explicit safety guidance against logging full prompts, full responses,
  request bodies, headers, environment variables, API keys, bearer tokens, or
  credentials in the default recommended shape.

### Open Questions

- A later production harness can prove whether the recommended shape should
  become an enforced schema, parsed summary, report input, or result field.
- Richer harness artifacts, process-tree cleanup, and task status/reporting
  remain separate future external-agent slices.

## 2026-05-06 (external-agent optional model-call log path)

### Changed

- Added a narrow optional model-call artifact handoff for public
  `external-agent` executions: the runner now includes
  `run.model_call_log_path` in the context JSON, pointing at
  `task/<case-id>/rep-NNN.model-calls.jsonl` under the run output directory.
- Kept the artifact optional and harness-owned. The runner exposes the path but
  does not pre-create, require, validate, parse, summarize, report, or add it
  to `run.jsonl`.
- Kept harness-owned model calls outside normal adapter `raw/` request/response
  artifacts and preserved existing task stdout/stderr paths, subprocess argv,
  adapter call ordering, patch capture ordering, verifier ordering, result row
  shape, compare/report behavior, and manifest/CLI surfaces.

### Open Questions

- A later production harness slice still needs a recommended or enforced
  model-call JSONL schema only if real agents prove that parsing or reporting
  that telemetry is necessary.
- Process-tree cleanup policy and evidence for richer task status/reporting
  remain open for full production external coding-agent integration.

## 2026-05-06 (external-agent context handoff)

### Changed

- Added the next narrow public `external-agent` slice: the runner now writes a
  deterministic JSON context file at `task/<case-id>/rep-NNN.context.json` for
  public external-agent executions and appends `--context <path>` to the
  subprocess argv.
- Versioned the context with `version = 1` and included explicit non-secret
  runner context: pack id/version/description, case id/kind/loaded prompt/
  fixture refs/harness id and timeout, prepared workspace path and source
  fixture metadata, run output directory, repetition, task stdout/stderr paths,
  optional persisted `run-metadata.json` path, selected adapter id/model/user
  endpoint argument/effective defaults, and pack fixture inventory.
- Kept the context as harness input only. No `run.jsonl` fields, adapter
  schemas, normal `raw/` artifacts, compare/report behavior, manifest command
  syntax, task environment configuration, or secrets handling changed.
- Preserved public `external-agent` argv loading policy, direct executor
  rejection of `harness_id="external-agent"`, fenced-patch default and explicit
  behavior, normal adapter call before the task phase, patch capture after the
  task phase, and verifier execution after patch capture.

### Open Questions

- Full production external coding-agent integration still needs harness-owned
  model-call logging, process-tree cleanup policy, and evidence for whether
  task logs plus verifier status are enough.

## 2026-05-05 (public external-agent runnable slice)

### Changed

- Promoted `external-agent` from loader-rejected provisional id to accepted
  public `repo-task` harness id. It is valid only in the case-local
  `harness = { id = "external-agent", timeout_s = ... }` table on `repo-task`
  cases; non-`repo-task` harness declarations and malformed harness tables
  remain rejected.
- Added runner-owned CLI configuration through `BENCHPACK_EXTERNAL_AGENT_ARGV`.
  The CLI reads it only when a loaded pack selects `external-agent`, parses it
  as a JSON array of non-empty strings without NUL bytes, rejects plain command
  strings and shell parsing, and fails before run output directory creation and
  before adapter calls when it is missing or malformed.
- Routed public `external-agent` cases to the existing
  `ExternalProcessHarness` executor path. The runner appends `--workspace`,
  `--case`, `--output-dir`, and `--repetition`, runs the subprocess without a
  shell in the prepared workspace, captures stdout/stderr into existing task
  log artifacts, then preserves patch capture and verifier execution ordering.
- Kept direct executor `harness_id="external-agent"` rejected so public
  manifest routing remains a CLI responsibility in this slice.
- Preserved existing fenced-patch defaults and explicit
  `harness = { id = "fenced-patch" }` behavior, the normal adapter call before
  the repo-task task phase, adapter request/result schemas, raw artifact paths,
  task log paths, measured row shapes, compare/report behavior, repo-task
  warmup rejection, and generated-result policy.

### Open Questions

- Full production external coding-agent integration still needs harness-owned
  model-call logging, richer runner-owned context, process-tree cleanup policy,
  and evidence for whether task logs plus verifier status are sufficient.
- A future cleanup can remove or rename the backward-compatible
  `PROVISIONAL_EXTERNAL_AGENT_HARNESS_ID` constant once downstream references
  have moved to `PUBLIC_HARNESS_EXTERNAL_AGENT`.

## 2026-05-05 (external-agent loader-rejection policy lock)

### Changed

- Locked the public parser policy for the provisional `external-agent` harness
  id without adding production external coding-agent execution. The id remains
  documentation-only and is rejected by the manifest loader, the CLI, and the
  repo-task executor boundary.
- Added a named `PROVISIONAL_EXTERNAL_AGENT_HARNESS_ID` constant in
  `benchpack.packs` alongside the existing `PUBLIC_HARNESS_FENCED_PATCH`
  constant and `KNOWN_PUBLIC_HARNESS_IDS` set. The constant is intentionally
  excluded from the public set; parser, CLI, and executor tests lock the
  exclusion so a future regression that added the provisional id to the
  public set would fail tests rather than silently accept the manifest.
- Sharpened parser, CLI, and executor tests so each layer references the
  provisional constant directly: the parser error mentions both the rejected
  provisional id and the implemented `fenced-patch` public id; the CLI test
  proves the manifest fails before any adapter call or run-output directory is
  created; the executor test proves a stray `harness_id="external-agent"`
  raises `TaskError` without writing task logs and without mutating the
  prepared workspace.
- Preserved every existing behavior: absent `harness` still defaults to the
  fenced-patch executor; `harness = { id = "fenced-patch" }` and
  `harness.timeout_s` semantics are unchanged; the internal in-process
  agent-session harness and runner-side `ExternalProcessHarness` paths remain
  runner-only with unchanged contracts; adapter request/result schemas, raw
  paths, `run.jsonl` row shapes, patch capture, verifier execution ordering,
  compare/report behavior, the default M4/M5 matrix, repo-task warmup
  rejection, and source-fixture immutability remain unchanged.

### Open Questions

- Whether the next slice should accept `external-agent` as a parser-reserved
  not-runnable id with a clear executor/CLI not-implemented error, or keep the
  loader as the single rejection point until the production external harness
  integration is ready.
- How a real production external harness will represent process-tree cleanup,
  model-call context, harness-owned artifacts, run-metadata handoff, and
  richer task status/reporting beyond the existing task logs.

## 2026-05-05 (production external harness contract refinement)

### Changed

- Refined the future production external repo-task harness contract after the
  second bundled fenced-patch pack established enough coverage for the current
  model-output unified-diff path.
- Kept code behavior unchanged: the only implemented public harness id remains
  `fenced-patch`, and `external-agent` is documented only as a provisional
  future id that the current loader must still reject.
- Documented the planned external harness manifest shape as an explicit
  case-local `harness = { id = "external-agent", timeout_s = ... }` table, with
  no task commands, task environment table, shell expansion, secrets handling,
  workspace retention flag, pack-level default, or CLI flag added now.
- Defined future runner-owned harness inputs: prepared workspace, case and pack
  metadata, loaded prompt text, fixture/source-repo metadata, output directory,
  repetition, task log paths, selected harness options, optional run metadata,
  and model/adapter/endpoint/defaults context when the harness owns model calls.
- Preserved adapter and result boundaries: harness-owned model calls are
  runner/harness concerns, not normal adapter request fields, and they do not
  write normal `raw/` artifacts or add `run.jsonl` fields without a later schema
  slice.
- Clarified mutation and artifact boundaries: future external harnesses may
  mutate only the prepared workspace and write only existing task logs until a
  later schema explicitly names more run-output artifacts.
- Clarified timeout and failure semantics for future external subprocess
  harnesses: `harness.timeout_s` remains a task-phase timeout distinct from
  verifier timeout; timeouts are task outcomes only when the runner can stop the
  process tree, close logs, and continue with bounded workspace state, otherwise
  they are runner failures.
- Reaffirmed ordering: workspace preparation, task harness execution, patch
  capture, verifier execution, then result recording. No compare/report behavior,
  default M4/M5 matrix, repo-task warmup support, workspace retention option, or
  live benchmark artifact was added.

### Open Questions

- The next implementation slice should decide between adding a parser-accepted
  reserved id that fails at execution with a clear not-implemented error, or
  keeping the loader as the single rejection point until the external runner
  exists.
- A real external harness may prove that richer task status/reporting or named
  harness artifacts are necessary, but this contract keeps existing task logs
  and verifier status as the default boundary.
- Production external harness integration still needs model-call logging,
  process-tree cleanup policy, run-metadata handoff, and a public parser/
  executor policy.

## 2026-05-05 (external subprocess harness skeleton)

### Changed

- Added the first narrow subprocess-backed external repo-task harness path
  behind `run_repo_task_executor` for runner-side callers and deterministic
  tests only.
- The new internal harness accepts explicit runner-owned argv, appends prepared
  workspace, case id, output directory, and repetition arguments, runs without a
  shell in the prepared workspace, and captures stdout/stderr into the existing
  `task/<case-id>/rep-NNN.*.log` artifacts.
- Completed nonzero subprocess exits are task outcomes rather than runner
  crashes. Timeouts are task outcomes when the direct subprocess is stopped and
  task logs can be written, using deterministic stderr text before patch
  capture and verifier execution continue.
- Invalid public/internal harness combinations, unsafe argv shape, missing
  executables, invalid workspaces, and unwritable required task logs remain
  runner failures before completed task records are assumed.
- Preserved existing fenced-patch defaults, explicit `harness = { id =
  "fenced-patch" }` behavior, internal in-process agent-session behavior,
  adapter schemas, raw paths, result row shapes, compare/report behavior, and
  default M4/M5 matrix. The manifest loader still rejects `external-agent`.

### Open Questions

- Whether the next production slice should keep `external-agent` loader-rejected
  until the real integration is ready, or add a parser-accepted reserved id that
  fails at execution with a clear not-implemented error.
- Whether production external harnesses need process-tree cleanup, richer task
  status/reporting, named harness artifacts, run-metadata handoff, or
  harness-owned model-call logging beyond the existing task logs.

## 2026-05-05 (python-regression-fix bundled repo-task)

### Changed

- Added `python-regression-fix` as a second bundled measured `repo-task` pack
  over the existing fenced unified-diff executor.
- The pack contains one stdlib-only Python repo fixture, one
  `fix-task-summary` measured case, `defaults.stream = false`,
  `defaults.warmup = 0`, `defaults.repetitions = 1`, and case-local
  `scoring.mode = "verify-script"`.
- The fixture exercises task summary counts, missing-owner handling,
  input-immutability, incomplete-overdue filtering, and due-date/title
  ordering without external dependencies or live benchmark requirements.
- The verifier imports the prepared workspace module directly, requires a
  non-empty captured patch artifact, writes structured JSON, and exits `0`
  only when all deterministic checks pass.
- Added bundled pack contract coverage and a mocked-adapter CLI flow that
  applies a known fenced diff, verifies the run-owned workspace changed, and
  confirms the pack-owned source fixture remains unchanged.
- Updated README, specification, architecture, benchpack format notes,
  implementation plan, and Apple Silicon runbook interpretation boundaries.
- Kept the default M4/M5 tmux/four-pack matrix unchanged; the new pack is an
  optional deeper fenced-patch repo-task signal, not production external
  agent-harness integration.

### Open Questions

- The new fixture is still intentionally small. A later pack may need a larger
  repository or production external harness once the runner has an explicit
  harness contract for that scope.
- Adding `python-regression-fix` to the default M4/M5 matrix should remain a
  separate operational decision after runtime cost and report shape are clear.

## 2026-05-05 (report-set manifest)

### Changed

- Added `benchpack report --set <manifest.toml>` as a narrow source-only
  report-set manifest mode for existing result directories.
- The TOML shape is `version = 1` plus non-empty `result_dirs = [...]`;
  `version` is optional but must be integer `1` when present.
- Relative `result_dirs` entries resolve relative to the manifest file's parent
  directory before the existing report loader reads `run.jsonl`.
- Kept report-set manifests read-only and reporting-only: no benchmark
  execution, runtime startup, tmux orchestration, SSH, result copying, report
  artifact writing, result-directory mutation, compare behavior changes, or
  result row schema changes.
- Updated README, specification, architecture, Apple Silicon runbook,
  implementation plan, and Qwen3.6 summary notes for the new CLI shape.

### Open Questions

- Curated source report-set manifests may be useful for durable benchmark
  narratives later, but this slice intentionally adds no checked-in manifests
  that point at local generated `results/*` directories.
- Report output may eventually display the report-set name or manifest path, but
  this first slice preserves the existing Markdown renderer output.

## 2026-05-05 (Qwen3.6 M4/M5 benchmark summary)

### Changed

- Added `docs/qwen36-m4-m5-benchmark-summary.md` as the compact durable summary
  for the completed Qwen3.6 M4/M5 MLX-vs-llama.cpp-vs-Ollama sweep.
- Linked the summary from the README documentation index so readers do not need
  to parse the full `docs/run-log.md` table row for the headline throughput,
  scoring, interpretation notes, and ignored result-directory patterns.
- Kept generated `results/*` artifacts ignored and added a `.gitignore` rule
  for local `metadata/*.json` files so machine-local metadata stays out of
  normal commits.

### Open Questions

- Curated source report-set manifests can be added later when a run-log entry
  needs a durable named group, but generated `results/*` artifacts still stay
  ignored unless intentionally curated.

## 2026-05-05 (tmux metadata matrix helper)

### Changed

- Added `scripts/benchpack-tmux-matrix` as a narrow operational helper for the
  metadata-backed benchmark matrix.
- The helper requires explicit `--adapter`, `--model`, `--host-label-prefix`,
  and `--run-metadata`, and passes the metadata file to every generated
  `benchpack run` command.
- The default matrix is `smoke-chat`, `runtime-sweep`, `desktop-django-wrap`,
  and `patch-from-failure`, with stable host-label suffixes `smoke`,
  `runtime`, `wrap`, and `patch`.
- Added a dry-run path that prints the assembled `benchpack run` and tmux
  commands without starting tmux, contacting an endpoint, or running live M4/M5
  benchmarks.
- Tmux windows are created deterministically but benchmark commands are gated
  to run sequentially so the packs do not contend for the same runtime.
- Failed pack windows now set a tmux session failure marker and signal the next
  gate so downstream windows wake up, report that they were skipped, and stay
  inspectable rather than blocking indefinitely.
- Launch mode now checks that the supplied metadata file exists before creating
  tmux windows; dry-run mode still accepts placeholder paths.
- Kept `--force` opt-in, allowed optional `--endpoint`, and allowed optional
  `--openai-stream-usage include|omit` while preserving the underlying
  `benchpack run` default when omitted.
- Updated README, architecture, Apple Silicon runbook, and implementation plan
  to document the helper as an operational wrapper, not a new core CLI command
  or benchmark semantic change.

### Open Questions

- A future manifest or report-set format may still be useful for naming paired
  local/remote result directories and report inputs, but this slice deliberately
  leaves live M4/M5 execution and report assembly manual.

## 2026-05-05 (Qwen3.6 operational benchmark defaults)

### Changed

- Documented the default no-more-guessing model targets for M4/M5
  MLX-vs-llama.cpp-vs-Ollama benchmark requests: `Qwen/Qwen3.6-35B-A3B` for
  the 30B-class MoE target and `Qwen/Qwen3.6-27B` for the dense target.
- Added preferred GGUF artifacts for llama.cpp/Ollama and preferred MLX
  conversions for the MLX path to `AGENTS.md` and the Apple Silicon runbook.
- Clarified that llama.cpp and Ollama should share the same GGUF artifact when
  possible, while MLX comparisons should be labeled as runtime-and-format
  comparisons unless artifact parity is otherwise established.
- Clarified that already-installed Qwen2.5, Qwen3-Coder, or other models should
  not be silently substituted when the user asks for Qwen3.6 benchmarks.

### Open Questions

- Qwen3.6 MLX serving support may vary by conversion and server package. If the
  selected MLX OpenAI-compatible server cannot load a target, record that
  runtime/model pair as blocked instead of changing the benchmark target.

## 2026-05-04 (generated result ignore policy)

### Changed

- Updated `.gitignore` so generated `results/*` directories are ignored by
  default while preserving the tracked `results/.gitkeep`.
- Curated result artifacts can still be committed intentionally with
  `git add -f` when a `docs/run-log.md` entry calls for them.
- Updated specification, architecture, and run-log guidance to reflect that
  force-add workflow.

### Open Questions

- Existing tracked curated result artifacts remain tracked. Future curation
  should stay explicit and small.

## 2026-05-03 (structured runtime metadata artifact)

### Changed

- Added `benchpack run --run-metadata <json-file>` for explicit,
  user-supplied runtime/run metadata capture.
- The metadata file must be JSON with an object root. Known optional sections
  `runtime`, `model`, and `operating_conditions` must be objects when present,
  and `notes` must be a string when present.
- Supplied metadata is written as a small sibling artifact,
  `run-metadata.json`, beside `hardware.json` and is summarized in
  `summary.md`.
- `benchpack report` now reads optional `run-metadata.json` and renders a
  concise runtime/model/operating-condition metadata table. Missing metadata is
  tolerated and reported explicitly; malformed metadata fails clearly.
- Kept metadata capture user-driven and runner/reporting-side only: no runtime
  autodiscovery, server probing, checksum scanning, power/thermal capture,
  adapter schema changes, benchmark semantics changes, `run.jsonl` row field
  additions, or compare median/cache/parity behavior changes were added.
- Updated README, specification, architecture, Apple Silicon runbook,
  hardware-target notes, decisions, run-log guidance, and implementation plan
  for the new metadata workflow.

### Open Questions

- Future metadata may need richer conventions for runtime options or curated
  result subsets, but auto-capture remains intentionally out of scope until a
  runtime-specific design is justified.
- Existing local 2026-05-03 generated result artifacts still remain local
  evidence and should not be committed unless a later curated run-log entry
  calls for a small subset.

## 2026-05-03 (Apple Silicon comparison report generator)

### Changed

- Added `benchpack report`, a read-only Markdown report generator over existing
  result directories.
- The report command loads `run.jsonl` through the compare loader and optionally
  reads sibling `hardware.json` for host identity fields. Missing
  `hardware.json` is tolerated and reported explicitly.
- Report output includes input directories, pack id/version, adapter/model/
  endpoint values, row and `ok` counts, scoring pass/fail/unscored counts, and
  compare medians for wall time, TTFT, prefill TPS, decode TPS, total TPS,
  output tokens, prompt tokens, cached prompt tokens, cache rows, warnings, and
  `prefill parity`.
- The report median/parity section reuses compare summarization, warning, and
  prefill-parity helpers so it does not diverge from `benchpack compare`.
- Updated README, specification, architecture, Apple Silicon runbook, and
  implementation plan for the new reporting workflow.
- Kept the command read-only: no benchmark execution, adapter loading,
  hardware collection, `raw/` reads, result artifact writes, result-directory
  mutation, row schema changes, compare behavior changes, pack semantic
  changes, or hardware collector changes were added.

### Open Questions

- Future reporting may need runtime metadata capture if manual server-command,
  runtime-version, checksum, power, thermal, and background-load notes remain
  error-prone.
- Curated result subsets for live M4/M5 runs remain a separate decision; broad
  generated `raw/`, `workspace/`, `patch/`, `task/`, and `verify/` artifacts
  should still stay out of normal commits.

## 2026-05-03 (Apple Silicon comparison reporting polish)

### Changed

- Added benchmark matrix/reporting polish to the Apple Silicon M4/M5 runbook
  before live comparison runs.
- Tightened the recommended four-pack matrix so `smoke-chat` is endpoint
  sanity, `runtime-sweep` is the current performance pack,
  `desktop-django-wrap` is prompt-only coding-agent-shaped behavior, and
  `patch-from-failure` is a tiny verifier-backed repo-task smoke benchmark.
- Added a comparison report checklist and compact report skeleton that
  separates host identity read from `hardware.json` (`chip`,
  `hardware_model`, `hardware_model_name`, `hardware_model_identifier`,
  `ram_mb`, `os`, and `gpus`) from manual runtime/model/cache/power notes.
- Documented manual notes for runtime/server version, server command, adapter
  and endpoint shape, model id/tag/file, quantization, checksum when practical,
  context size, GPU layer/batch/cache options, `--openai-stream-usage` mode,
  power mode, thermal state, background load, result directories, compare
  warnings, and `prefill parity` statuses.
- Clarified that `benchpack compare` derives prompt/cache warnings and
  prefill parity from normalized `run.jsonl` fields only and does not infer
  runtime/cache parity from raw files, timing fields, or endpoint behavior.
- Updated the implementation plan to mark the benchmark matrix/reporting polish
  slice as landed.
- No live benchmark rows, generated result artifacts, CLI flags, adapter
  fields, result row fields, compare behavior, pack semantics, hardware
  collector behavior, remote SSH orchestration, or private host/model/path
  details were added.

### Open Questions

- Live M4/M5 benchmark execution and curated run-log entries remain future
  operational work.
- Broad coding-agent conclusions still need production external harness
  execution, richer task status/reporting if needed, and larger repo-task
  packs.
- Runtime metadata automation may be useful later if manual report capture
  proves too error-prone, but runtime process discovery, checksum discovery,
  endpoint probing, and power/thermal measurement automation remain out of
  scope for this slice.

## 2026-05-03 (Apple Silicon comparison hardware metadata)

### Changed

- Audited Apple Silicon `hardware.json` metadata for the M4/M5 comparison
  track and found that chip, unified memory, macOS version, and GPU model were
  already captured on the local M5 path, but machine class/model identity was
  not explicit enough for M5 Max versus M4 Max Studio interpretation.
- Added optional Darwin host-model metadata to `hardware.json`:
  `hardware_model` from `sysctl hw.model`, plus
  `hardware_model_name` and `hardware_model_identifier` from
  `system_profiler SPHardwareDataType` when available.
- Added `SPHardwareDataType` fallbacks for Apple chip, CPU core count, and
  memory when `sysctl` output is generic or unavailable.
- Kept the collector best-effort: missing `sysctl` or `system_profiler` data
  still degrades to `null` or an empty GPU list and does not block a run.
- Documented that runtime versions, server commands, model checksums,
  quantization, context size, power/thermal state, and cache settings remain
  run-note responsibilities instead of broad runtime discovery.
- No CLI flags, adapter fields, `run.jsonl` row fields, raw artifact paths,
  pack semantics, compare behavior, remote SSH orchestration, or live
  benchmark artifacts were added.

### Open Questions

- Future M4/M5 work still needs benchmark matrix/reporting polish and, later,
  production external harness execution plus larger repo-task packs before
  drawing broad coding-agent conclusions.
- Runtime metadata may need a later narrow collector slice if repeated run-note
  capture proves too error-prone, but this slice intentionally avoided runtime
  process discovery or endpoint probing.

## 2026-05-03 (Apple Silicon comparison runbook)

### Changed

- Added `docs/apple-silicon-m4-m5-runbook.md` as the first operational
  runbook for comparing this local M5 Max machine with an M4 Max Studio over
  SSH.
- The runbook covers local M5 commands, SSH M4 commands, placeholder endpoint
  and model usage, host-label and result-directory conventions, result pullback
  with `rsync` or `scp`, and read-only `benchpack compare` invocation.
- Kept the slice documentation-only: no helper script, CLI flag, adapter field,
  result row field, benchmark semantic change, or generated benchmark artifact
  was added.
- Linked the runbook from `README.md` and updated the implementation plan to
  mark the runbook/SSH orchestration slice as landed while keeping hardware
  metadata audit and reporting polish as future work.
- Documented troubleshooting for endpoint smoke failures, OpenAI-compatible
  servers that reject `stream_options.include_usage`, SSH quoting/path issues,
  missing result directories, and compare prompt/cache/prefill warnings.

### Open Questions

- The hardware metadata audit still needs to confirm whether current
  `hardware.json` output is sufficient for Apple Silicon M4/M5 comparisons.
- Future slices still need benchmark matrix/reporting polish and, later,
  production external harness execution plus larger repo-task packs before
  drawing broad coding-agent conclusions.

## 2026-05-03 (Apple Silicon comparison operational track planning)

### Changed

- Added an operational implementation-plan track for comparing the local M5 Max
  machine with the M4 Max Studio over SSH.
- The planned track separates runbook/SSH orchestration, hardware/runtime
  metadata audit, and benchmark matrix/reporting polish into focused
  implementation handoffs.
- The first recommended matrix is `smoke-chat`, `runtime-sweep`,
  `desktop-django-wrap`, and `patch-from-failure`, with clear interpretation
  boundaries for prompt-only and tiny repo-task coverage.
- Documented fairness constraints for same model, quantization, runtime path,
  endpoint options, cache/context settings, power/thermal state, and background
  load.
- Live M4/M5 benchmark runs remain out of implementation validation unless
  explicitly requested; curated outcomes belong in `docs/run-log.md`.

### Open Questions

- The first runbook slice should decide whether a manual SSH workflow is enough
  or whether a narrow helper script is worth adding. Resolved by the
  2026-05-03 runbook slice: documentation-only is enough for now.
- The hardware metadata audit still needs to confirm whether current
  `hardware.json` output is sufficient for Apple Silicon M4/M5 comparisons.

## 2026-05-03 (Phase 3 external harness contract and task timeout)

### Changed

- Defined the production external repo-task harness contract as a docs-first
  boundary without implementing a production external coding-agent harness.
- Future external harnesses are public repo-task harnesses selected only by
  explicit case-local `harness.id`; selection must not be inferred from model,
  adapter, endpoint, fixture shape, verifier, host, or pack id.
- Documented that normal adapter request/result schemas remain unchanged by
  default, and future harness-owned model calls are runner/harness concerns
  rather than normal adapter request fields.
- Documented external harness write boundaries: mutate only the prepared
  workspace and write only allowed run-output artifacts; pack fixtures,
  prompts, verifier scripts, source docs, and raw model artifacts remain
  immutable or runner-owned.
- Added `harness.timeout_s` for `repo-task` harness declarations. Positive TOML
  integers and floats are accepted; booleans, strings, zero, negative values,
  arrays, tables, extra harness keys, and harness timeout on non-`repo-task`
  cases are rejected.
- The only implemented public harness id remains `fenced-patch`. Explicit
  `harness = { id = "fenced-patch", timeout_s = ... }` routes to the existing
  fenced model-output `diff`/`patch` executor with subprocess timeout
  enforcement on both `git apply --check` and `git apply`.
- A preflight timeout is a deterministic task outcome with unchanged workspace,
  task stderr, patch capture afterward, and verifier execution afterward. An
  apply timeout after successful preflight is a runner failure because partial
  workspace mutation cannot be ruled out.
- Internal in-process agent-session harness callables reject task timeout.
- Adapter schemas, raw artifact paths, task stdout/stderr paths, `run.jsonl`
  row shapes, patch capture ordering, verifier ordering, repo-task warmup
  rejection, source fixture immutability, and bundled `patch-from-failure`
  behavior remain unchanged.
- No CLI flags, production external coding-agent integration, manifest task
  commands, task environment, workspace retention options, broad artifacts
  object, pack-level harness defaults, repo-task warmups, or new adapter fields
  were added.

### Open Questions

- Future slices still need production external coding-agent integration, richer
  task status/reporting if needed, repo-task warmup support, workspace
  cleanup/retention options, task environment support, source fixture metadata
  if later needed, recursive directory deletion if later needed, pack-level
  harness defaults if later needed, and larger bundled repo-task conversion.

## 2026-05-03 (Phase 3 public fenced-patch harness selection)

### Changed

- Added typed manifest parsing for case-local
  `harness = { id = "fenced-patch" }` on `repo-task` cases.
- The only implemented public harness id is `fenced-patch`; malformed harness
  tables, unknown ids, extra keys, and harness declarations on non-`repo-task`
  cases are rejected at manifest load time.
- CLI repo-task runs now pass the parsed public harness id into the task
  executor. Explicit `fenced-patch` and absent `harness` both route to the
  existing fenced model-output `diff`/`patch` executor.
- The task executor rejects unknown public harness ids if they somehow reach
  that layer, and rejects ambiguous direct calls that combine public
  `harness_id` with the internal runner-side `agent_session_harness`.
- Adapter request/result schemas, raw request/response paths, `run.jsonl` row
  shapes, task stdout/stderr paths, patch capture after the task phase,
  verifier execution after patch capture, repo-task warmup rejection, bundled
  `patch-from-failure` behavior, and chat behavior remain unchanged except for
  clear validation when chat cases declare `harness`.
- No CLI flags, production external coding-agent integration, manifest task
  commands, task environment, task timeout, workspace retention, richer task
  status/reporting, pack-level harness defaults, repo-task warmups, or new
  result fields were added.

### Open Questions

- Future slices still need production external coding-agent integration, richer
  task status/reporting if needed, repo-task warmup support, workspace
  cleanup/retention options, task environment support, task timeout support,
  source fixture metadata if later needed, recursive directory deletion if
  later needed, pack-level harness defaults if later needed, and larger bundled
  repo-task conversion.

## 2026-05-03 (Phase 3 internal harness workspace file delete helper)

### Changed

- Added `AgentSessionHarnessRequest.delete_workspace_file(relative_path)` for
  runner-side internal harnesses.
- The delete helper uses the same validated workspace-relative path boundary as
  existing read/write/exists helpers.
- It returns true after deleting an existing regular file or in-workspace
  symlink-to-file workspace entry, returns false for missing paths and
  directories, and leaves symlink targets intact when deleting a symlink entry.
- Unsafe delete paths, absolute paths, `..` escapes, symlink escapes outside
  the prepared workspace, and delete `OSError`s raise `TaskError` before task
  stdout/stderr logs are recorded.
- Focused tests now prove regular-file delete, missing path false, directory
  false, unsafe delete rejection, escaping symlink rejection, in-workspace
  symlink-entry deletion, no task logs after unsafe helper failure, patch
  capture of harness deletions, verifier observation after patch capture, and a
  fake harness flow using list, exists, read, write, and delete together.
- No manifest harness selection, CLI task flags, adapter schema changes, result
  row fields, raw artifact path changes, task log path changes, task timeout or
  environment support, repo-task warmups, workspace retention options, source
  fixture metadata on the harness request, directory deletion, recursive
  deletion, or production external coding-agent integration were added.

### Open Questions

- Future slices still need public harness selection if needed, production
  external coding-agent integration, richer task status/reporting if needed,
  repo-task warmup support, cleanup and retention options, task environment
  support if needed, task timeout support if needed, source fixture metadata if
  later needed, recursive directory deletion if later needed, and larger
  bundled repo-task conversion.

## 2026-05-03 (Phase 3 docs-first public harness selection contract)

### Changed

- Defined a future public repo-task harness selection shape as an explicit
  case-local `harness = { id = "..." }` table.
- Kept the contract design-only: no manifest parser changes, validation
  changes, CLI flags, harness registry, executor selection behavior, adapter
  schema changes, raw artifact path changes, task log path changes, or
  `run.jsonl` row fields were added.
- Documented that absence of `harness` keeps the current fenced model-output
  `diff`/`patch` executor default, and harness selection must not be inferred
  from model names, adapters, endpoints, fixture shape, verifier choice, host
  environment, or pack id.
- Documented compatibility boundaries for future selection: adapter
  request/result schemas stay unchanged by default; existing task stdout/stderr
  paths remain the task-phase artifact paths unless a later schema slice
  changes them; patch capture still reflects the post-task workspace; verifier
  execution still happens after patch capture; repo-task warmups remain
  rejected.
- Left task environment, task timeout, workspace retention, richer
  status/reporting, pack-level harness defaults, and production external
  coding-agent integration as explicit future slices.

### Open Questions

- Future slices still need actual public manifest parsing and executor
  selection if needed, production external coding-agent integration, richer
  task status/reporting if needed, repo-task warmup support, workspace
  cleanup/retention options, task environment support, task timeout support,
  pack-level harness defaults if needed, and larger bundled repo-task
  conversion.

## 2026-05-03 (Phase 3 internal harness workspace directory discovery helper)

### Changed

- Added `AgentSessionHarnessRequest.list_workspace_dirs()` for runner-side
  internal harnesses.
- The directory listing helper returns deterministic sorted POSIX
  workspace-relative paths for directories under the prepared workspace.
- Directory listings include nested directories and directories created earlier
  in the same harness invocation, exclude the workspace root and files, and
  exclude symlinks including symlinks to directories.
- Failed directory listing, including a prepared workspace path that is not a
  directory, raises `TaskError` before task stdout/stderr logs are recorded.
- Focused tests now prove sorted POSIX nested directory paths, file and root
  exclusion, same-invocation created directory visibility, symlink-to-directory
  exclusion, no task logs after listing failure, and a fake harness flow using
  file and directory helpers together.
- No public harness selection behavior, CLI flags, manifest parser changes,
  adapter schema changes, result row fields, raw artifact path changes, task
  log path changes, task timeout or environment support, repo-task warmups,
  workspace retention options, directory deletion, recursive deletion, or
  production external coding-agent integration were added.

### Open Questions

- Future slices still need actual public harness selection if needed,
  production external coding-agent integration, richer task status/reporting if
  needed, repo-task warmup support, cleanup and retention options, task
  environment support, task timeout support, source fixture metadata if later
  needed, recursive directory deletion if later needed, and larger bundled
  repo-task conversion.

## 2026-05-03 (Phase 3 internal harness workspace discovery helpers)

### Changed

- Added `AgentSessionHarnessRequest.list_workspace_paths()` for runner-side
  internal harnesses.
- The listing helper returns deterministic sorted POSIX workspace-relative
  paths for regular files only, excludes directories, and observes files
  created earlier in the same harness invocation.
- Symlinks to regular files are listed only when their target resolves inside
  the prepared workspace.
- Added `AgentSessionHarnessRequest.workspace_file_exists(relative_path)` for
  runner-side internal harnesses.
- The existence helper uses the same validated workspace-relative path boundary
  as the existing read/write helpers, returns true only for existing regular
  files including in-workspace symlinks to regular files, and returns false for
  missing paths and directories.
- Unsafe existence-check paths raise `TaskError` before task stdout/stderr logs
  are recorded, matching existing unsafe read/write helper behavior.
- Focused tests now prove deterministic listing, POSIX nested paths,
  same-invocation created files, directory exclusion, file-existence checks,
  unsafe existence rejection, and a list/exists/read/write harness flow.
- No manifest harness selection, CLI task flags, adapter schema changes, result
  row fields, raw artifact path changes, task log path changes, task timeout or
  environment support, repo-task warmups, workspace retention options, source
  fixture metadata on the harness request, or production external coding-agent
  integration were added.

### Open Questions

- Future slices still need public harness selection if needed, production
  external coding-agent integration, richer task status/reporting if needed,
  repo-task warmup support, cleanup and retention options, task environment
  support if needed, task timeout support if needed, source fixture metadata if
  later needed, and larger bundled repo-task conversion.

## 2026-05-03 (Phase 3 internal harness workspace read helper)

### Changed

- Added `AgentSessionHarnessRequest.read_workspace_text(relative_path)` for
  runner-side internal harnesses.
- The read helper uses the same validated workspace-relative path boundary as
  existing harness workspace writes and returns UTF-8 text from the prepared
  workspace.
- Unsafe paths, absolute paths, `..` escapes, missing files, and unreadable
  text reads raise `TaskError` before task stdout/stderr logs are recorded.
- Focused tests now prove harness read-before-write behavior, unsafe read
  rejection, missing-file read rejection, and the existing realistic fake-agent
  edit sequence using reads and writes together.
- No manifest harness selection, CLI task flags, adapter schema changes, result
  row fields, raw artifact path changes, task log path changes, task timeout or
  environment support, repo-task warmups, workspace retention options, or
  production external coding-agent integration were added.

### Open Questions

- Future slices still need public harness selection if needed, production
  external coding-agent integration, richer task status/reporting if needed,
  repo-task warmup support, cleanup and retention options, task environment
  support if needed, task timeout support if needed, and larger bundled
  repo-task conversion.

## 2026-05-03 (Phase 3 internal agent-session harness path)

### Changed

- Added the first narrow internal agent-session harness executor path behind
  `run_repo_task_executor`.
- Runner-side callers can supply a harness that receives the prepared
  workspace path, case metadata, model output text, run output directory,
  measured repetition, and deterministic task log paths.
- The internal harness context provides validated workspace-relative text
  writes, so focused tests can prove harness mutation stays in the prepared
  workspace while pack-owned source fixtures remain unchanged.
- Harness task outcomes use the existing
  `task/<case-id>/rep-NNN.stdout.log` and
  `task/<case-id>/rep-NNN.stderr.log` artifacts and the existing
  `{"stdout_path": ..., "stderr_path": ...}` task record shape.
- Patch capture still runs after the task phase and observes harness workspace
  mutations; verifier execution still runs after patch capture and observes the
  same mutated workspace.
- Current CLI repo-task runs still use the fenced model-output `diff`/`patch`
  executor by default, and bundled `patch-from-failure` behavior remains
  unchanged.
- No manifest harness selection, CLI task flags, manifest task commands, task
  environment configuration, task timeout configuration, repo-task warmups,
  workspace retention options, broad generic artifact object, adapter schema
  changes, or result row fields were added.

### Open Questions

- Future slices still need public harness selection if needed, production
  external coding-agent integration, richer task status/reporting if needed,
  repo-task warmup support, cleanup and retention options, task environment
  support if needed, task timeout support if needed, and larger bundled
  repo-task conversion.

## 2026-05-03 (Phase 3 repo-task task-executor boundary)

### Changed

- Introduced a narrow internal repo-task task-executor boundary around the
  existing measured fenced model-output patch phase.
- The only implemented executor remains the behavior-preserving fenced
  `diff`/`patch` model-output bridge: it extracts the first matching fenced
  block, applies it as a unified diff inside the prepared workspace, and writes
  the same deterministic task stdout/stderr artifacts.
- The CLI now invokes the task phase through that internal boundary after the
  adapter call and before patch capture. Patch capture and verifier execution
  order remain unchanged.
- Adapter request shape, raw request/response paths, workspace, patch, task,
  verify, repo_task, and scoring row shapes, task log paths and contents,
  repo-task warmup rejection, prompt-output scoring, non-repo-task behavior,
  verifier timeout and environment handling, and bundled `patch-from-failure`
  behavior remain unchanged.
- No real agent-session harness, manifest task commands, task environment
  configuration, task timeout configuration, CLI task flags, workspace
  retention options, repo-task warmups, broad generic artifact object, or new
  result fields were added.

### Open Questions

- Future slices still need full agent-session harness integration, richer task
  status/reporting if needed, repo-task warmup support, cleanup and retention
  options, task environment support if needed, and larger bundled repo-task
  conversion.

## 2026-05-03 (Phase 3 docs-first agent-session harness contract)

### Changed

- Defined the planned real agent-session harness as a future internal
  repo-task executor behind the existing task-executor boundary.
- Documented likely runner-side harness inputs: prepared workspace path, case
  metadata, pack metadata as needed, model/adapter/endpoint/default context as
  needed, run output directory, measured repetition, and deterministic task log
  paths.
- Documented the harness write boundary: it may mutate only the prepared
  workspace and write only under the run output directory, and it must not
  mutate pack-owned fixtures, prompts, verifier scripts, source docs, or public
  adapter/result schemas by default.
- Kept the current implemented behavior explicit: the fenced model-output
  `diff`/`patch` executor remains the only implemented executor, task logs
  still live under `task/<case-id>/rep-NNN.*.log`, patch capture remains after
  task execution, verifier execution remains after patch capture, and result
  row shapes remain unchanged.
- No real agent-session harness, manifest task commands, task environment
  configuration, task timeout configuration, CLI task flags, workspace
  retention options, repo-task warmups, broad generic artifact object, or new
  result fields were added.

### Open Questions

- Future slices still need real agent-session harness implementation, richer
  task status/reporting if needed, repo-task warmup support, cleanup and
  retention options, task environment support if needed, task timeout support if
  needed, and larger bundled repo-task conversion.

## 2026-05-02 (Phase 3 manifest verifier timeout)

### Changed

- Added manifest-configurable verifier timeouts for measured `repo-task`
  `verify-script` scoring through optional `scoring.timeout_s`.
- `timeout_s` is a first-class scoring field, not an opaque extra key, and is
  validated as a positive TOML int or float. Booleans, strings, zero, and
  negative values fail manifest loading.
- Verifier execution now uses the effective scoring table's timeout, so
  case-local scoring overrides pack-level scoring for `timeout_s` the same way
  they already override `mode` and `script`.
- The default remains `300.0` seconds when `timeout_s` is absent. Timeout
  verifier JSON records the actual configured value, while normal result rows
  do not gain new top-level timeout fields.
- Adapter request shape, raw request/response paths, workspace, patch, task,
  verify, repo_task, and scoring row shapes, repo-task warmup rejection,
  prompt-output scoring, non-repo-task `verify-script` rejection, verifier
  environment handling, task timeout handling, and workspace retention behavior
  remain unchanged.

### Open Questions

- Future slices still need full agent-session harness integration, richer task
  status/reporting if needed, repo-task warmup support, cleanup and retention
  options, task environment support if needed, and larger bundled repo-task
  conversion.

## 2026-05-02 (Phase 3 manifest verifier environment)

### Changed

- Added manifest-configurable verifier environment support for measured
  `repo-task` `verify-script` scoring through optional `scoring.environment`.
- `environment` is a first-class scoring field, not an opaque extra key, and is
  validated as a TOML table of string keys to string values. Empty string values
  are allowed. Non-table values, non-string values, nested tables, arrays, empty
  names, names with unsafe characters, names starting with a digit, and values
  containing NUL fail manifest loading.
- Verifier execution now uses the effective scoring table's environment, so
  case-local scoring overrides pack-level scoring as a whole instead of
  field-merging environment entries.
- When `environment` is absent, verifier subprocesses keep the previous inherited
  environment behavior. When present, the runner copies the current environment,
  overlays the manifest entries, and passes that copy only to the verifier.
- Adapter request shape, raw request/response paths, workspace, patch, task,
  verify, repo_task, and scoring row shapes, timeout behavior and timeout JSON,
  repo-task warmup rejection, prompt-output scoring, non-repo-task
  `verify-script` rejection, task environment handling, task timeout handling,
  and workspace retention behavior remain unchanged.

### Open Questions

- Future slices still need full agent-session harness integration, richer task
  status/reporting if needed, repo-task warmup support, cleanup and retention
  options, task environment support if needed, and larger bundled repo-task
  conversion.

## 2026-05-02 (Phase 3 bundled repo-task patch pack)

### Changed

- Added the first bundled measured repo-mutating `repo-task` pack:
  `patch-from-failure` version `0.1.0`.
- The pack declares one tiny stdlib-only Python `kind = "repo"` fixture and one
  measured `fix-greeting` case with `defaults.warmup = 0`,
  `defaults.repetitions = 1`, `defaults.stream = false`, and case-local
  `scoring.mode = "verify-script"`.
- The prompt tells the model to return only a fenced `diff` block containing a
  unified diff from the repository root, exercising the current model-output
  patch bridge as an actual bundled benchmark surface.
- The verifier is stdlib-only and deterministic: it imports `greeter.py` from
  the prepared workspace, requires `greet("Ada") == "Hello, Ada!"`, requires a
  non-empty captured patch artifact, writes JSON to the runner-provided output
  path, and uses the process exit code as the pass/fail authority.
- Added bundled pack loading coverage and a mocked-adapter CLI test that runs
  `patch-from-failure` by name, applies a fenced diff, confirms source fixture
  immutability, and checks the existing `workspace`, `patch`, `task`, `verify`,
  `repo_task`, `scoring`, and `raw` row shapes without adding a generic
  `artifacts` object.
- No adapter request fields, CLI flags, manifest shell commands, manifest task
  commands, environment configuration, task timeout configuration, repo-task
  warmups, workspace retention options, live benchmark output, larger bundled
  repo-task conversion, broad generic artifact object, or new task status/result
  fields were added.

### Open Questions

- Future slices still need full agent-session harness integration, richer task
  status/reporting if needed, repo-task warmup support, cleanup and retention
  options, configurable verifier environment support, and larger
  bundled repo-task conversion.

## 2026-05-02 (Phase 3 repo-task verifier timeout)

### Changed

- Added a fixed runner-owned timeout for measured `repo-task`
  `verify-script` subprocess execution so verifier hangs do not hang the whole
  benchmark run.
- Verifier timeouts are recorded as completed failed measured rows rather than
  runner crashes. Timeout rows keep the existing `workspace`, `patch`,
  `verify`, `repo_task`, and top-level `scoring` shape.
- Timeout rows set `repo_task.status = "failed"`,
  `repo_task.verify_exit_code = null`, and top-level scoring to
  `{"mode": "verify-script", "passed": false}`.
- Timeout verifier JSON is created or corrected with authoritative
  `exit_code: null`, `passed: false`, `timed_out: true`, and `timeout_s`.
  If timeout-time JSON is an object, non-authoritative fields are preserved; if
  it is missing, malformed, or not an object, it is replaced with the minimal
  timeout object.
- Timeout stdout/stderr logs are always written at the deterministic verifier
  artifact paths. Captured partial output from `subprocess.TimeoutExpired` is
  preserved when Python exposes it; otherwise empty log files are created.
- Non-timeout verifier behavior, script path safety, prompt-output scoring,
  raw request/response paths, adapter request shape, workspace preparation,
  patch capture, repo-task fixture validation, symlink escape rejection,
  repo-task warmup rejection, and non-repo-task `verify-script` rejection remain
  unchanged.
- No manifest timeout field, CLI timeout flag, environment configuration, task
  execution logs, agent-session harness, model-output mutation/application,
  workspace retention option, repo-task warmup support, bundled pack
  conversion, live benchmark run, or generated result artifact was added.

### Open Questions

- Future slices still need real task or agent execution, model-output patch
  application, warmup workspace support, cleanup and retention options,
  configurable verifier environment support, and bundled pack
  conversion.

## 2026-05-02 (Phase 3 repo-task model-output patch application)

### Changed

- Added the next narrow measured `repo-task` task phase: after adapter
  execution, the runner extracts the first fenced code block whose info string
  is exactly `diff` or `patch`, treats that block body as a unified diff, and
  applies it inside the prepared workspace before source-vs-workspace patch
  capture and verifier execution.
- Non-matching fenced blocks are ignored. Missing matching blocks, empty patch
  blocks, unsafe paths, and unapplicable diffs are written as deterministic task
  stderr messages and do not crash the benchmark row.
- Successful application writes a short deterministic task stdout message and
  leaves task stderr empty. The existing top-level `task.stdout_path` and
  `task.stderr_path` row metadata shape is unchanged.
- Patch capture now observes any applied model patch, so
  `patch/<case-id>/rep-NNN.diff` reflects the mutated workspace. `verify-script`
  verifiers also observe the mutated workspace because they still run after
  patch capture.
- Path preflight rejects absolute paths, `..` traversal, null bytes, and paths
  that resolve outside the prepared workspace. Pack-owned source fixtures remain
  immutable and are not passed to the patch applier.
- Raw request/response paths, adapter request shape, workspace metadata,
  patch metadata, verifier pass/fail/timeout behavior, repo-task fixture
  validation, symlink escape rejection, repo-task warmup rejection,
  prompt-output scoring, non-repo-task `verify-script` rejection, and chat row
  shapes remain unchanged.
- No agent-session harness, shell command manifest, environment configuration,
  task timeout configuration, CLI task flags, workspace retention option,
  repo-task warmup support, bundled pack conversion, live benchmark run, broad
  generic `artifacts` object, or new task status/result field was added.

### Open Questions

- Future slices still need full agent-session harness integration, richer task
  status/reporting if needed, repo-task warmup support, cleanup and retention
  options, configurable verifier environment support, and bundled pack
  conversion.

## 2026-05-02 (Phase 3 repo-task task log artifacts)

### Changed

- Added deterministic task stdout/stderr log artifacts for every measured
  `repo-task` execution at `task/<case-id>/rep-NNN.stdout.log` and
  `task/<case-id>/rep-NNN.stderr.log`, including `rep-001` for
  single-repetition packs.
- The current task phase remains a runner-owned no-op placeholder, so the new
  task log files are created empty. No agent-session harness, shell command
  execution, manifest task command, or model-output mutation/application was
  added.
- Measured repo-task `run.jsonl` rows now include top-level `task.stdout_path`
  and `task.stderr_path` with run-relative POSIX paths. Repo-task rows using
  prompt-output scoring include `workspace`, `patch`, and `task`, while
  `verify` and `repo_task` remain limited to `verify-script`.
- Chat records, including chat cases that reference repo directory fixtures,
  still do not include `workspace`, `patch`, `task`, `verify`, or
  `repo_task`.
- Raw model request/response paths under `raw/`, adapter request shape,
  workspace preparation, patch capture, verifier pass/fail/timeout behavior,
  repo-task fixture validation, symlink escape rejection, repo-task warmup
  rejection, prompt-output scoring, and non-repo-task `verify-script`
  rejection remain unchanged.
- No manifest task-log fields, CLI flags, environment configuration, task
  timeout configuration, workspace retention option, repo-task warmup support,
  bundled pack conversion, live benchmark run, or generated result artifact was
  added.

### Open Questions

- Future slices still need real task or agent execution, model-output mutation
  or patch application, warmup workspace support, cleanup and retention options,
  configurable verifier environment support, and bundled pack
  conversion.

## 2026-05-02 (Phase 3 repo-task verifier artifacts)

### Changed

- Added measured `repo-task` verifier execution for
  `scoring.mode = "verify-script"`. The runner executes verifier scripts after
  workspace preparation, adapter execution, and patch capture, but before
  writing the measured `run.jsonl` row.
- Verifier scripts are resolved as pack-relative paths, must exist, and are
  rejected if absolute or escaping the pack root. The initial execution shape is
  `sys.executable <script>` with deterministic command-line arguments for the
  prepared workspace, case id, pack id/version, source fixture id, patch path,
  and requested output JSON path.
- Verifier artifacts are written beside `raw/` under
  `verify/<case-id>/rep-NNN.json`,
  `verify/<case-id>/rep-NNN.stdout.log`, and
  `verify/<case-id>/rep-NNN.stderr.log`, including `rep-001` for
  single-repetition packs.
- If a verifier does not create structured JSON, the runner writes a minimal
  object containing `exit_code` and `passed`. If the verifier writes a JSON
  object, the runner preserves it while making `exit_code` and `passed`
  authoritative from the process result.
- Measured repo-task `verify-script` rows now include top-level `verify`,
  `repo_task`, and `scoring` objects. `repo_task.status` is `"passed"` for exit
  code `0` and `"failed"` for nonzero; `repo_task.verify_exit_code` records the
  integer process exit code; top-level scoring is
  `{"mode": "verify-script", "passed": <bool>}`.
- Non-repo-task cases that request `verify-script` fail clearly. Normal chat
  records, including chat cases with repo directory fixtures, still do not
  include `workspace`, `patch`, `verify`, or `repo_task`.
- Adapter requests remain unchanged and still receive only prompt, model,
  endpoint, defaults, and raw request/response paths.
- Existing raw path behavior, prompt-output scoring, workspace metadata, patch
  metadata, repo-task fixture validation, symlink escape rejection, and
  repo-task warmup rejection remain unchanged.
- No agent-session harness, model-output mutation/application, workspace
  cleanup/retention option, repo-task warmup support, timeout/environment
  configuration, bundled pack conversion, live benchmark run, or generated
  result artifact was added.

### Open Questions

- Future slices still need real task or agent execution, model-output patch
  application, warmup workspace support, cleanup and retention options,
  timeout/environment configuration, and bundled pack conversion.

## 2026-05-02 (Phase 3 repo-task patch artifacts)

### Changed

- Added deterministic patch artifact capture for measured `repo-task`
  executions. After the adapter call, the runner compares the immutable source
  repo fixture directory to the prepared workspace directory and writes
  `patch/<case-id>/rep-NNN.diff`.
- Measured repo-task `run.jsonl` rows now include a top-level `patch` object
  with run-relative `patch.path`, alongside the existing `workspace` metadata.
- Patch files are written for every measured repo-task execution, including
  no-change runs where the patch file is empty. The path includes `rep-001`
  even when the pack has one measured repetition.
- Patch capture uses a deterministic directory snapshot diff rather than
  `git diff`, so repo fixtures do not need to be Git repositories. Text changes
  use unified diff output, added/deleted files are represented deterministically,
  symlink target changes are text diffs of link targets, UTF-8 text line endings
  are normalized before comparison, and binary changes use deterministic marker
  lines.
- Chat records, including chat cases that reference repo directory fixtures,
  still do not include `workspace` or `patch`.
- Adapter requests remain unchanged and still receive only prompt, model,
  endpoint, defaults, and raw request/response paths.
- Raw request/response path behavior, scoring, repo-task fixture validation,
  symlink escape rejection, measured workspace preparation, and repo-task
  warmup rejection remain unchanged.
- No verifier execution, final repo-task status, task or agent harness,
  workspace cleanup/retention option, bundled pack conversion, or live
  benchmark result artifact was added.

### Open Questions

- Future slices still need verifier invocation, verifier/log artifact paths,
  final repo-task status fields, task or agent execution, warmup workspace
  support, cleanup and retention options, and curated artifact rules for
  repo-task outputs.

## 2026-05-01 (Phase 3 measured repo-task workspaces)

### Changed

- Implemented the first narrow repo-task runtime slice: measured `repo-task`
  executions now prepare a disposable run-owned workspace before the adapter
  call.
- The runner requires each repo-task case to reference exactly one
  `kind = "repo"` directory fixture. Additional referenced file fixtures remain
  prompt/context inputs, while non-repo directory fixtures, missing repo
  fixtures, multiple repo fixtures, and repo fixtures that are not directories
  fail before adapter execution.
- Workspaces are copied under the run output directory at
  `workspace/<case-id>/rep-NNN/`, including `rep-001` for single-repetition
  packs. Existing destinations fail rather than being merged.
- Workspace preparation rejects absolute symlinks and relative symlinks whose
  target resolves outside the source repo fixture before copying, while
  allowing internal relative symlinks.
- Source fixtures under `benchpacks/<pack>/fixtures/` remain immutable by
  contract. Existing chat cases still treat referenced directory fixtures as
  metadata-only and do not create workspaces.
- Repo-task warmups are rejected for now because warmup workspace semantics are
  intentionally deferred.
- Adapter requests and `run.jsonl` records are unchanged; no workspace paths,
  repo-task status fields, verifier output, patch artifacts, agent harness, or
  live benchmark result artifacts were added.

### Open Questions

- Future slices still need verifier invocation, patch capture, repo-task result
  schema fields, task or agent execution, warmup workspace support, cleanup and
  retention options, and curated artifact rules for repo-task outputs.

## 2026-05-01 (Phase 3 repo-task workspace result metadata)

### Changed

- Added the next narrow repo-task result schema slice: measured `repo-task`
  `run.jsonl` rows now include a top-level `workspace` object.
- The workspace object records `path`, `source_fixture_id`, and `source_path`.
  `path` is relative to the run output directory, for example
  `workspace/<case-id>/rep-NNN`, and `source_path` is the manifest-declared
  fixture path rather than an absolute resolved path.
- Chat records, including chat cases that reference repo directory fixtures,
  still do not include `workspace`.
- Adapter requests remain unchanged and still receive only prompt, model,
  endpoint, defaults, and raw request/response paths.
- Raw request/response path behavior, scoring, repo-task fixture validation,
  symlink escape rejection, and repo-task warmup rejection remain unchanged.
- No verifier execution, patch capture, final repo-task status, task or agent
  harness, workspace cleanup/retention option, bundled pack conversion, or live
  benchmark result artifact was added.

### Open Questions

- Future slices still need verifier invocation, patch capture, repo-task patch
  and verifier artifact paths, final repo-task status fields, task or agent
  execution, warmup workspace support, cleanup and retention options, and
  curated artifact rules for repo-task outputs.

## 2026-04-30 (Phase 3 repo-task contract design)

### Changed

- Defined the docs-first repo-task contract for future disposable repository
  execution before adding runner support.
- Specified that pack-owned `kind = "repo"` directory fixtures are immutable
  source artifacts and that future repo-task mutation must happen only in a
  run-owned disposable workspace under the result directory.
- Documented the planned repo-task fixture rule: one primary repo directory
  fixture per repo-task case, with additional referenced file fixtures remaining
  prompt/context inputs unless a later explicit field gives them another role.
- Documented planned repo-task artifacts: prepared workspace metadata,
  retained `workspace/` contents when explicitly kept, `patch.diff`, task
  stdout/stderr logs, verifier output such as `verify.json`, and final status.
- Clarified that `verify-script` is the intended deterministic repo-task
  scoring mode once implemented, while `contains` and `regex` remain
  prompt-output scoring modes.
- Added durable decision D-021 for run-owned disposable workspaces and explicit
  repo-task artifacts.
- Preserved the current `desktop-django-wrap` behavior: it remains prompt-only,
  file fixture contents assemble into prompts, and the directory-shaped
  `synthetic-django-repo` fixture remains metadata-only.
- No runner implementation, adapter change, result schema writer change,
  fixture copying code, verifier execution, patch extraction, prompt change,
  pack manifest change, scoring change, live benchmark run, or generated result
  artifact was added.

### Open Questions

- Exact result schema keys for repo-task status and artifact paths still need to
  be designed with the implementation slice.
- The first coding slice should choose the concrete workspace path convention
  under each result directory and implement disposable directory copy for one
  repo fixture per measured execution.
- Later slices still need verifier invocation details, patch capture rules,
  timeout/environment handling, workspace retention options, and agent-session
  integration.

## 2026-04-30 (Phase 3 directory fixture snapshot)

### Changed

- Added a compact pack-local `desktop-django-wrap` directory fixture at
  `fixtures/synthetic-django-repo/` with a tiny synthetic Django source
  snapshot.
- Declared the snapshot as top-level fixture `synthetic-django-repo` with
  `kind = "repo"` and a pack-relative directory path.
- Bumped `desktop-django-wrap` to version `0.1.4` and linked both existing
  cases to `synthetic-django-app` and `synthetic-django-repo` in that order.
- The existing referenced file fixture still assembles into `Case.prompt`; the
  directory fixture remains metadata-only and is not read, copied, executed, or
  injected into prompts.
- No live benchmark run, adapter change, compare change, result schema change,
  scoring change, repo mutation, disposable worktree, directory copying,
  fixture execution, verifier execution, patch extraction, prompt templating,
  agent-session replay, or generated result artifact was added.

### Open Questions

- Future Phase 3 slices still need to define disposable repo-task execution,
  directory fixture execution or copying semantics, prompt import from
  `desktop-django-starter`, verifier scripts, patch extraction, and eventual
  real agent-session replay.

## 2026-04-30 (Phase 3 regex output contract)

### Changed

- Implemented executable deterministic `regex` scoring with Python
  `re.search(pattern, output)` and no implicit regex flags.
- Bumped `desktop-django-wrap` to version `0.1.5`.
- Tightened both `desktop-django-wrap` prompts to require the same short output
  skeleton: `DDS_WRAP_PLAN`, then `Inspect:`, `Electron shell:`,
  `Django runtime:`, `Packaging:`, and `Verification:` in order.
- Changed `desktop-django-wrap` scoring from marker-only `contains` to `regex`
  so the marker and fixed labels must appear in order.
- The `synthetic-django-app` file fixture still assembles into prompts with
  stable delimiters, and the `synthetic-django-repo` directory fixture remains
  metadata-only and is not read, copied, executed, or injected into prompts.
- No live benchmark run, adapter change, compare change, result schema change,
  repo mutation, disposable worktree, directory copying, fixture execution,
  verifier execution, patch extraction, prompt templating, agent-session
  replay, or generated result artifact was added.

### Open Questions

- Future Phase 3 slices still need to define disposable repo-task execution,
  directory fixture execution or copying semantics, prompt import from
  `desktop-django-starter`, verifier scripts, patch extraction, and eventual
  real agent-session replay.

## 2026-04-30 (Phase 2 closure docs)

### Changed

- Closed Phase 2 administratively in `docs/implementation-plan.md` after
  reviewing the landed runtime-sweep, streaming TTFT, warmup/repetition,
  Ollama native timing, MLX validation, llama-server validation, compare,
  cache metadata, cache-aware compare, prompt/cache parity, prefill parity,
  gated prefill TPS, and OpenAI streaming usage compatibility slices.
- Marked Phase 2 as implemented/closed while preserving validation caveats:
  the curated run log has MLX and llama-server evidence, the 2026-04-29
  llama-server runtime rows are warm-cache rows, prompt-cache parity remains
  required for prefill-speed interpretation, and a curated Ollama
  `runtime-sweep` live run remains optional future validation.
- Kept Phase 3 as the active current workstream; `desktop-django-wrap`,
  prompt-file support, static fixture metadata, and case-level fixture refs
  remain the started Phase 3 surface.
- No live benchmark run, adapter change, compare change, result schema change,
  scoring change, pack format change, pack manifest change, or generated result
  artifact was added.

### Open Questions

- Whether to add a curated Ollama `runtime-sweep` live run later for additional
  Phase 2 validation evidence remains optional and should be recorded in
  `docs/run-log.md` only if an actual run is performed and curated.

## 2026-04-30 (Phase 3 file fixture prompt assembly)

### Changed

- Added fixture-backed prompt assembly for referenced file fixtures.
- Loaded `Case.prompt` remains the final adapter prompt. The base prompt still
  comes from exactly one `prompt` or `prompt_file` source, then referenced file
  fixture contents are appended in `fixture_refs` order.
- Appended file fixtures use stable plain-text delimiters that include the
  fixture id, kind, and pack-relative path.
- Directory fixture refs remain valid metadata-only refs and are not copied,
  executed, read into prompts, or turned into disposable repositories.
- `Case.raw` still preserves the manifest fields, `Case.fixture_refs` still
  exposes fixture id strings, and `Pack.fixtures` still exposes fixture
  metadata.
- Bumped `desktop-django-wrap` to version `0.1.3` because both effective
  prompts now include the referenced `synthetic-django-app` file fixture.
- No live benchmark run, adapter change, compare change, result schema change,
  scoring change, repo mutation, verifier execution, patch extraction,
  agent-session replay, or generated result artifact was added.

### Open Questions

- Future Phase 3 slices still need to define directory fixture semantics,
  disposable repo-task execution, prompt templating or multi-message support if
  needed, verifier scripts, patch extraction, and eventual real agent-session
  replay.

## 2026-04-30 (Phase 3 case fixture refs)

### Changed

- Added optional case-level `fixture_refs` support to benchpack manifests.
- Loaded `Case` objects now expose `fixture_refs` as fixture id strings, with
  cases that omit the field loading as `[]`.
- `fixture_refs` must be a TOML array of strings. Each ref must match the
  existing id grammar, be unique within the case, and point to an existing
  top-level fixture id in the same pack.
- Fixture refs are validated against the loaded top-level fixture inventory, so
  `[[fixtures]]` may appear before or after `[[cases]]` in TOML.
- Bumped `desktop-django-wrap` to version `0.1.2` and linked both existing
  cases to the existing portable `synthetic-django-app` fixture by id.
- Existing `desktop-django-wrap` case ids, defaults, prompt-file entries,
  scoring mode, prompt marker behavior, and fixture declaration/path remain
  unchanged.
- No live benchmark run, new adapter, new scoring engine, compare change,
  prompt templating, fixture content loading, fixture execution, disposable
  worktree handling, verifier script, patch extraction, repo mutation, or agent
  execution harness was added.

### Open Questions

- Future Phase 3 slices still need to define prompt assembly from fixtures,
  fixture loading semantics beyond metadata refs, directory fixture use,
  disposable target repos, `repo-task` execution, patch extraction, and
  verify-script scoring.

## 2026-04-29 (Phase 3 fixture metadata support)

### Changed

- Added top-level `[[fixtures]]` support to the benchpack manifest loader.
- Fixture ids use the existing id grammar and duplicate fixture ids fail at
  load time.
- Fixture kind values must be non-empty strings. Fixture paths must be strings,
  relative to the pack directory, exist, point to a file or directory, and not
  resolve to the pack directory itself.
- Fixture path resolution rejects absolute paths, `..` traversal outside the
  pack, and symlink targets outside the pack directory.
- Loaded `Pack` objects now expose `fixtures` metadata while packs without
  fixtures continue to load with an empty fixture list.
- Added one portable synthetic `desktop-django-wrap` fixture file under
  `benchpacks/desktop-django-wrap/fixtures/` and bumped that pack to version
  `0.1.1`.
- Existing `desktop-django-wrap` case ids, defaults, prompt-file entries,
  scoring mode, and `DDS_WRAP_PLAN` marker behavior remain unchanged.
- No live benchmark run, new adapter, new scoring engine, compare change,
  prompt templating, fixture execution, disposable worktree handling, verifier
  script, patch extraction, repo mutation, or agent execution harness was
  added.

### Open Questions

- Future Phase 3 slices still need to define prompt assembly from fixtures,
  directory fixture loading semantics, disposable target repos, `repo-task`
  execution, patch extraction, and verify-script scoring.

## 2026-04-29 (Phase 3 prompt-file support)

### Changed

- Added case-level `prompt_file` support to the benchpack manifest loader.
- `prompt_file` paths are resolved relative to the pack directory, must be
  relative paths, and must resolve inside the pack after following symlinks.
- Cases now fail at load time when they define both `prompt` and `prompt_file`,
  or neither prompt source.
- The loader reads prompt files as UTF-8 text and stores the contents in
  `Case.prompt`, so existing CLI, adapter, scoring, reporter, and result record
  behavior remains unchanged.
- Moved the bundled `desktop-django-wrap` prompts from inline TOML strings to
  pack-local files under `benchpacks/desktop-django-wrap/prompts/`, while
  keeping pack id, version, defaults, case ids, scoring mode, and marker check
  unchanged.
- No live benchmark run, new adapter, new scoring engine, compare change,
  fixture support, disposable worktree handling, verifier script, repo mutation,
  or agent execution harness was added.

### Open Questions

- Future Phase 3 slices still need fixture loading, disposable target repos,
  repo-task semantics, patch extraction or agent-harness integration, and
  verify-script scoring contracts before this becomes a repo-mutating wrapping
  benchmark.

## 2026-04-29 (Phase 3 desktop-django-wrap starter pack)

### Changed

- Added the bundled `desktop-django-wrap` pack as the first Phase 3
  coding-agent-shaped workload surface.
- The pack is prompt-only and portable: two inline chat cases ask for concise
  Django-in-Electron wrapping plans derived from the
  `desktop-django-starter` workflow, without local paths, target repo
  checkouts, network dependencies, fixtures, repo mutation, patch extraction,
  or verifier scripts.
- The pack sets `defaults.stream = true`, `defaults.warmup = 0`,
  `defaults.repetitions = 1`, and `defaults.max_tokens = 384`.
- Scoring uses the existing executable `contains` mode against the explicit
  marker `DDS_WRAP_PLAN` as a minimal deterministic sanity check.
- No live benchmark run, new adapter, new scoring engine, compare change,
  fixture support, disposable worktree handling, or agent execution harness was
  added.

### Open Questions

- Future Phase 3 slices still need compact target fixtures, disposable target
  repos, deterministic verify scripts, patch extraction or agent-harness
  integration, and eventual replay of fuller wrapping sessions.

## 2026-04-29 (Phase 2 OpenAI stream usage compatibility)

### Changed

- Added `benchpack run --openai-stream-usage {include,omit}` as an explicit
  `openai-chat` streaming compatibility switch.
- The default `include` mode preserves the existing request shape by sending
  `stream_options.include_usage` whenever the pack requests streaming.
- The `omit` mode still sends `"stream": true` but omits the `stream_options`
  key entirely for endpoints that reject OpenAI streaming usage options.
- In omit mode, streamed output text, raw chunks, `timing.wall_s`, and
  `timing.ttft_s` remain available when content chunks arrive. If no usage chunk
  is reported, `tokens.prompt`, `tokens.output`, `tokens.cached_prompt`,
  `timing.prefill_tps`, and `timing.decode_tps` remain null.
- The CLI passes the option through a private per-request defaults key for
  `openai-chat` only, without changing benchpack manifest semantics or mutating
  the loaded pack defaults.
- No automatic retry, endpoint detection, new adapter, compare behavior change,
  live benchmark run, or generated result artifact update was added.

### Open Questions

- Future work may add endpoint presets or manifest-level adapter options if
  several compatibility switches accumulate, but this slice intentionally keeps
  the usage mode as an explicit run-time option.
- Live validation against a server that rejects `stream_options.include_usage`
  remains useful when such a target is available.

## 2026-04-29 (Phase 2 gated compare prefill TPS)

### Changed

- Added a `prefill_tps med` column to `benchpack compare`.
- The column is a median of normalized `run.jsonl` `timing.prefill_tps` values
  using the same numeric filter as the other compare metrics.
- Numeric prefill TPS is rendered only when the case-level `prefill parity`
  status is `comparable`; `missing-case`, `prompt-missing`, `prompt-diff`,
  `cache-missing`, and `cache-diff` render `—` even if timing values exist.
- Existing prompt/cache warnings, cache coverage, and parity status priority
  remain unchanged.
- Compare still reads only normalized `run.jsonl` records and does not inspect
  ignored `raw/` artifacts or infer prompt/cache state from timing fields.

### Open Questions

- Future compare slices may add stronger summaries for comparable prefill cases,
  but they should preserve the parity gate unless a better deterministic parity
  contract replaces it.
- Historical artifacts without normalized cache fields will continue to suppress
  prefill speed display until rerun or otherwise supported by explicit
  normalized metadata.

## 2026-04-29 (Phase 2 compare prefill parity status)

### Changed

- Added a compact `prefill parity` column to `benchpack compare`, repeated on
  each run row with a case-level status.
- Status values use deterministic priority order: `missing-case`,
  `prompt-missing`, `prompt-diff`, `cache-missing`, `cache-diff`, then
  `comparable`.
- The status is derived only from normalized `run.jsonl` summaries: case row
  presence, complete numeric `tokens.prompt` coverage, prompt-token medians,
  complete numeric `tokens.cached_prompt` coverage, and cached prompt-token
  medians.
- Existing prompt/cache warnings remain, cache metadata coverage remains, and
  `timing.prefill_tps` remains omitted from the primary compare table.

### Open Questions

- A future compare slice can expose `prefill_tps` only after deciding how to
  gate the numeric speed column on the explicit parity status.
- Historical artifacts without `tokens.cached_prompt` will continue to show
  non-comparable status for prefill interpretation until rerun or otherwise
  supported by explicit normalized cache metadata.

## 2026-04-29 (Phase 2 compare prompt/cache parity)

### Changed

- Added prompt/cache parity context to `benchpack compare`: the table now shows
  median numeric `tokens.prompt` beside median `tokens.cached_prompt`.
- Compare warns when all compared runs for a case have measured rows and every
  row has numeric prompt-token metadata but the prompt-token medians differ,
  because cache parity is not comparable across different prompt token counts.
- Existing cache metadata warnings remain: compare still warns for incomplete
  `tokens.cached_prompt` metadata and for differing complete cached prompt-token
  medians, while suppressing prompt/cache median mismatch warnings when a case
  is absent from one compared run.
- `timing.prefill_tps` remains omitted. This slice adds prompt/cache parity
  visibility only; it does not make prefill-speed claims and does not read raw
  artifacts or infer token/cache state.

### Open Questions

- Future compare work can add `prefill_tps` only after the output makes
  prompt/cache parity explicit enough to avoid mixing different prompts or
  warm-cache and cold-prefill behavior.

## 2026-04-29 (Phase 2 compare cache awareness)

### Changed

- Extended `benchpack compare` to report median numeric `tokens.cached_prompt`
  and cache metadata coverage for each case/run row while keeping
  `timing.prefill_tps` out of the primary table.
- Added deterministic per-case warnings when cache metadata is incomplete for
  compared measured rows or when all compared runs for a case have complete
  cache metadata but cached prompt-token medians differ.
- Compare still reads only normalized `run.jsonl` records. It does not inspect
  ignored `raw/` artifacts and does not infer cache counts from prompt length,
  timing, or backend-specific duration fields.
- Existing historical rows that lack `tokens.cached_prompt`, or carry null or
  non-numeric values, remain readable and are displayed as missing cache
  metadata.

### Open Questions

- Future compare work may reintroduce `prefill_tps` only after cache parity is
  explicit enough to avoid warm-cache and cold-prefill comparisons being mixed.

## 2026-04-29 (Phase 2 compare command)

### Changed

- Added `benchpack compare <result-dir> <result-dir> [...]` as the first
  read-only comparison slice over existing result directories that contain
  `run.jsonl`.
- The compare command loads normalized result rows only, groups by case and
  input run, and prints a deterministic Markdown table with row count, `ok`
  count, and median `wall_s`, `ttft_s`, `decode_tps`, `total_tps`, and
  `tokens.output`.
- Compare warns when pack ids or versions differ and handles missing, empty, or
  malformed `run.jsonl` inputs with clear nonzero CLI errors.
- `prefill_tps` is intentionally omitted from the primary table because
  normalized result rows do not include prompt-cache parity metadata. The
  2026-04-29 `llama-server` runtime rows remain warm-cache rows, so compare
  output must not be read as cross-server cold-prefill evidence.
- No adapter behavior, adapter return payload shape, benchmark pack semantics,
  result record schema, compatibility fallback, live server orchestration, or
  generated result artifacts changed in this slice.

### Open Questions

- A future result schema may need normalized cached-token fields before
  `prefill_tps` can be compared across servers with cache parity.
- Future compare slices may add richer aggregation or output formats, but this
  slice deliberately stays at per-case medians over measured rows.

## 2026-04-29 (Phase 2 prompt-cache metadata)

### Changed

- Added normalized `tokens.cached_prompt` to new `run.jsonl` records. The field
  is the backend-reported count of prompt tokens served from cache, or `null`
  when unavailable.
- `openai-chat` now extracts
  `usage.prompt_tokens_details.cached_tokens` from both non-streaming responses
  and final streaming usage chunks while preserving existing prompt/output token
  behavior.
- `ollama-generate` leaves `tokens.cached_prompt` as `null`; its native
  `prompt_eval_*` fields are timing/count fields, not equivalent cache-hit
  counts.
- Existing committed result artifacts were not rewritten. Historical rows may
  lack `tokens.cached_prompt`; compare continues to read those rows.
- `benchpack compare` keeps the same table columns and still omits
  `prefill_tps`; its caveat now names `tokens.cached_prompt`. The new field
  makes future cache-parity checks possible, but missing or unequal cached-token
  counts do not support cross-server prefill-speed conclusions.

### Open Questions

- A future compare slice can summarize `tokens.cached_prompt` or warn on cache
  mismatch before exposing any prefill-speed comparison.
- Old curated artifacts without `tokens.cached_prompt` remain useful for
  wall/TTFT/decode/total/output comparisons, but not for cache-aware prefill
  analysis without separate evidence.

## 2026-04-29 (Phase 2 llama-server validation passed)

### Changed

- Completed the Phase 2 `llama-server` validation slice on `atlas.local` after
  preparing the host with Homebrew `llama.cpp` 8960
  (`version: 8960 (19821178b)`) and a local GGUF instruct model.
- Used model repository `bartowski/Qwen2.5-0.5B-Instruct-GGUF` at repository
  SHA `41ba88dbac95fed2528c92514c131d73eb5a174b` and model file
  `/Users/jochen/models/gguf/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf`
  (`sha256: 6eb923e7d26e9cea28811e1a8e852009b21242fb157b26149d3b188f3a8c8653`).
  `llama-server` reported GGUF V3, file type `Q4_K - Medium`, 494.03M
  parameters, and Qwen2.5 0.5B Instruct metadata.
- Verified local server usage before benchmark execution. Relevant help output
  confirmed `--model`, `--host`, `--port`, `--alias`, `--ctx-size`,
  `--gpu-layers`, and OpenAI-compatible server flags. The live server command
  was:
  `llama-server --model /Users/jochen/models/gguf/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf --alias qwen2.5-0.5b-instruct-q4_k_m --host 127.0.0.1 --port 8081 --ctx-size 4096 --gpu-layers auto`.
- The server listened at `http://127.0.0.1:8081`; the runner endpoint was
  `http://127.0.0.1:8081/v1`, which resolved to
  `http://127.0.0.1:8081/v1/chat/completions` in result rows.
- `smoke-chat` passed through the existing `openai-chat` adapter with exactly
  one measured row, `ok = true`, `scoring.passed = true`, output containing
  `Paris`, and non-streaming usage fields populated.
- `runtime-sweep` passed through the existing `openai-chat` adapter with
  exactly nine measured rows, no warmup rows in `run.jsonl`, and non-null
  `timing.ttft_s`, `timing.prefill_tps`, `timing.decode_tps`, and
  `tokens.output` for every measured row. Warmup raw files were generated
  locally under `raw/` and are not committed.
- `llama-server` accepted the current streaming request shape, including
  `stream_options.include_usage`, and returned streaming usage chunks with
  prompt and completion token counts. Because each case's warmup primed the
  llama.cpp prompt cache, all nine measured `runtime-sweep` rows were warm-cache
  rows: `short` reported 103 cached / 104 prompt tokens, `medium` reported
  375 / 376, and `long` reported 810 / 811. TTFT-derived `prefill_tps` in this
  run is therefore a prompt-cache fast-path artifact, not cold prefill speed.
- No adapter behavior, request shape, result schema, CLI flags, benchmark pack
  semantics, compatibility fallback, compare command, or aggregation changed in
  this slice.

### Open Questions

- The Phase 2 OpenAI-compatible server-path question is resolved for
  `mlx_lm.server` and this Homebrew `llama-server` build: both accept
  `stream_options.include_usage`. The next useful Phase 2 slice is
  `benchpack compare`, with prompt-cache parity handled before drawing numeric
  prefill-speed conclusions across servers.
- A future compatibility slice may still be useful for older or different
  OpenAI-compatible local servers that reject `stream_options.include_usage`,
  but it is no longer blocking compare for the validated MLX and llama.cpp
  server paths.

## 2026-04-29 (Phase 2 llama-server validation blocker, rechecked; superseded)

### Changed

- Attempted the next Phase 2 `llama-server` validation slice on `atlas.local`;
  a second 2026-04-29 implementation pass on branch
  `phase2-llama-server-live-validation` rechecked the prerequisites before any
  benchmark command was run. Live benchmark execution remained blocked by
  missing local server/model prerequisites rather than by an adapter
  compatibility result.
- No `llama-server`, `llama.cpp-server`, `llama-cpp-server`, or `llama-cli`
  executable was available on `PATH`; `llama-server --help` and
  `llama-server --version` therefore failed with `command not found`.
- Local executable searches checked `/opt/homebrew/bin`, `/usr/local/bin`,
  `~/.local/bin`, `~/bin`, and `~/projects` for `llama-server`,
  `*llama*server*`, and `server`-named files. Local GGUF searches checked
  `~/.cache`, `~/models`, `~/.local/share`, `~/Library/Caches`,
  `/opt/homebrew`, `~/Projects`, and `~/projects` with `*.gguf` file globs,
  plus Spotlight `mdfind 'kMDItemFSName == "*.gguf"c'`. The second pass also
  checked Homebrew package metadata for `llama.cpp` and scanned
  `/opt/homebrew`, `/usr/local`, `~/projects`, `~/Projects`, and `$HOME` for
  executable `llama-server`-compatible binaries. Those searches found no usable
  `llama-server` executable and no `.gguf` model file.
- `ollama list` showed local Ollama tags, but those are not directly usable as
  the GGUF model file required to start `llama-server` for this validation
  slice.
- No `smoke-chat` or `runtime-sweep` `llama-server` benchmark command was run,
  because the server command, endpoint, model file, model label, and
  quantization could not be verified locally.
- The blocked run means the `llama-server` success criteria in the Validation
  section of `docs/implementation-plan.md` remain untested: `smoke-chat` still
  needs exactly one measured row with `ok = true`, `scoring.passed = true`, and
  a resolved `/v1/chat/completions` endpoint, while `runtime-sweep` still needs
  exactly nine measured rows, no warmup rows in `run.jsonl`, and non-null
  `timing.ttft_s`, `timing.prefill_tps`, `timing.decode_tps`, and
  `tokens.output` for every measured row.
- No adapter behavior, request shape, result schema, CLI flags, benchmark pack
  semantics, or compatibility fallback changed in this slice.

### Open Questions

- Superseded by the later 2026-04-29 `llama-server` validation pass above:
  this blocker no longer represents the current Phase 2 state.

## 2026-04-28 (Phase 2 MLX server-path planning)

### Changed

- Validated `mlx_lm.server` through the existing `openai-chat` adapter on
  `atlas.local` using `mlx-community/Qwen2.5-0.5B-Instruct-4bit` at
  `http://localhost:8080/v1`.
- `smoke-chat` passed with exactly one measured row, `ok = true`,
  `scoring.passed = true`, and the resolved endpoint
  `http://localhost:8080/v1/chat/completions`.
- `runtime-sweep` passed with exactly nine measured rows, no warmup rows in
  `run.jsonl`, and non-null `timing.ttft_s`, `timing.prefill_tps`,
  `timing.decode_tps`, and `tokens.output` for every measured row.
- `mlx_lm.server` accepted the current streaming request shape, including
  `stream_options.include_usage`; no `openai-chat` compatibility slice is
  needed before validating `llama-server`.
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

- Whether `llama-server` accepts `stream_options.include_usage` remains to be
  validated locally. If it rejects the option, the next slice should be a
  narrow `openai-chat` streaming compatibility mode before `benchpack compare`.

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
