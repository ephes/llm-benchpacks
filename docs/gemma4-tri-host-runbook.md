# Gemma 4 Tri-host Runbook

This runbook prepares a Gemma 4 benchmark campaign across the local M5, the M4
Studio, and a Hetzner CUDA host. It is planning and operator workflow only. Do
not run live benchmarks, contact Hetzner endpoints, or add generated
`results/*` artifacts while applying documentation-only planning slices.
Explicit local preflight work should keep machine-local facts in ignored
`metadata/*.json` files and add only durable status notes here.

The first campaign mode is strict same-GGUF parity through `llama-server` on
all three hosts, subject to artifact, runtime, and memory-fit validation. The
fallback mode is a service-shaped runtime-and-format comparison: Apple Silicon
uses MLX or GGUF while Hetzner serves Hugging Face weights through vLLM. That
fallback is operationally useful, but it is not strict artifact parity and must
be labeled as runtime-and-format in metadata and reports.

## Non-goals

- No live M4, M5, or Hetzner benchmark matrix runs.
- No SSH commands, Hetzner endpoint calls, or generated result artifacts in
  documentation-only slices.
- No live Gemma 4 load, serving, checksum, or memory-fit validation unless the
  operator is explicitly performing a preflight slice.
- No SSH orchestration implementation.
- No serving, LiteLLM, vLLM, or sibling-repo deployment changes.
- No result schema, manifest syntax, compare/report, or adapter semantics
  changes.
- No secret storage, credential files, token values in docs, or automatic
  `OPENAI_API_KEY` usage.

## Preflight Checklist

Complete these checks before any live run:

- Repo state: same `llm-benchpacks` commit on M5, M4, and Hetzner, or an
  intentional documented difference.
- Packs: use the default four-pack matrix unless the run note says otherwise:
  `smoke-chat`, `runtime-sweep`, `desktop-django-wrap`, and
  `patch-from-failure`.
- Gemma 4 artifacts: exact model IDs, revisions, artifact filenames,
  quantization, license gates, and authentication requirements are recorded in
  `docs/model-targets.md`. Artifact checksums and memory-fit notes are
  host-local preflight fields; the local M5 E2B Q4_K_M checksum/load note is
  recorded below, while M4 and Hetzner remain placeholders.
- Strict-parity runtime: the same GGUF artifact loads through `llama-server` on
  Apple Silicon and on the CUDA host, with comparable context, cache, batch,
  and GPU-offload settings.
- Service-shaped fallback: exact Apple MLX/GGUF artifact and exact Hetzner
  Hugging Face/vLLM model revision are recorded, with `comparison_mode` set to
  `runtime-and-format`.
- Runtime support: llama.cpp, MLX, vLLM, transformers, tokenizer/chat template,
  and OpenAI-compatible `/v1` behavior are confirmed for the selected Gemma 4
  variant before launching matrices.
- Memory fit: RAM, VRAM, KV-cache size, context length, batch settings, and
  expected concurrency fit on each host. Do not infer fit from artifact file
  size alone.
- Hetzner inventory: SSH access, GPU model, VRAM, driver, CUDA, runtime
  versions, disk, and current service state are verified through deployment
  notes or read-only checks.
- Auth: authenticated Hetzner `/v1` access has a provisioned token in an
  operator-owned environment variable such as
  `BENCHPACK_HETZNER_OPENAI_TOKEN`. Do not put token values in commands,
  metadata, result artifacts, docs, or handoffs.
- Endpoints: local M5, M4, and Hetzner endpoint base URLs are recorded as
  placeholders in shared docs and exact values in local operator notes.
- Operating conditions: power mode, thermal state, intentional background load,
  cooling constraints, and network conditions are noted for each host.

## Comparison Modes

Primary mode:

- `comparison_mode`: `strict-same-gguf-llama-server`
- Runtime: `llama-server` on M5, M4, and Hetzner.
- Model: one verified Gemma 4 GGUF file, with the same artifact revision and
  checksum on all hosts.
- Use when the exact GGUF artifact fits and loads correctly on every host.
- This is the cleanest first hardware/runtime comparison because it avoids
  mixing MLX, GGUF, and Hugging Face/vLLM artifacts.
- First strict-parity dry-run candidate once fit is confirmed:
  `bartowski/google_gemma-4-E2B-it-GGUF` at revision
  `b5e99bd964eaacc27ba484bb2eb3e9f6160b9143`, file
  `google_gemma-4-E2B-it-Q4_K_M.gguf`, base model
  `google/gemma-4-E2B-it`. The optional multimodal projector files in that
  repo are verified but are not needed for the current text-only four-pack
  matrix unless a future multimodal pack is added. The local M5 preflight below
  confirms checksum and a conservative load command for this artifact only;
  M4 and Hetzner checksum/load/fit still need their own preflights.
- Alternative verified GGUF sources, to use only if the first candidate is
  rejected during preflight:
  `ggml-org/gemma-4-E2B-it-GGUF` has Q8_0/BF16 files but no Q4_K_M file in
  that repo as of 2026-05-06, while `ggml-org/gemma-4-E4B-it-GGUF` has
  `gemma-4-E4B-it-Q4_K_M.gguf`. Use one exact repo revision and one exact file
  across all strict-parity hosts.

Secondary/fallback mode:

- `comparison_mode`: `runtime-and-format`
- Apple Silicon runtime: MLX OpenAI-compatible server or `llama-server` with
  GGUF.
- Hetzner runtime: vLLM serving Hugging Face weights through an authenticated
  OpenAI-compatible `/v1` endpoint.
- Use when strict same-GGUF parity is blocked by artifact availability,
  runtime support, or memory fit, or when the operational question is service
  behavior rather than bit-identical artifact behavior.
- Every report must state that this mode is not artifact parity.
- Verified service-shaped candidates are
  `mlx-community/gemma-4-e2b-it-4bit` or
  `mlx-community/gemma-4-e4b-it-4bit` on Apple Silicon and
  `google/gemma-4-E2B-it` or `google/gemma-4-E4B-it` through vLLM on Hetzner.
  The MLX conversion cards document `mlx-vlm` usage; `mlx_lm.server` or any
  other OpenAI-compatible MLX path still needs local preflight before live
  matrices.

## M5 Local Preflight Status

Status as of 2026-05-06 for the first strict same-GGUF candidate only:

- Artifact:
  `bartowski/google_gemma-4-E2B-it-GGUF` revision
  `b5e99bd964eaacc27ba484bb2eb3e9f6160b9143`, file
  `google_gemma-4-E2B-it-Q4_K_M.gguf`.
- Local M5 SHA-256:
  `b5310340b3a23d31655d7119d100d5df1b2d8ee17b3ca8b0a23ad7e9eb5fa705`.
- Local alias: `gemma4-e2b-q4km`.
- Runtime: `/opt/homebrew/bin/llama-server`, llama.cpp version
  `9030 (a09a00e50)`, built with AppleClang
  `21.0.0.21000099` for Darwin arm64.
- Load command:
  `llama-server --model <downloaded-gguf> --alias gemma4-e2b-q4km --host 127.0.0.1 --port 8081 --ctx-size 8192 --batch-size 1024 --ubatch-size 512 --cache-type-k f16 --cache-type-v f16 --gpu-layers auto --parallel 1 --cache-prompt --no-webui`.
- Load result: succeeded on the local M5 with Metal, offloading 36/36 layers,
  `n_ctx=8192`, `n_batch=1024`, `n_ubatch=512`, f16 KV caches, and the server
  listening on `http://127.0.0.1:8081`.
- Tokenizer/chat-template notes: GGUF metadata includes
  `tokenizer.chat_template`; `llama-server` initialized a Gemma-style chat
  template with `thinking=1`. Load logs warned that control-looking tokens
  `<|tool_response>` and `</s>` were overridden, and `</s>` was removed from
  the EOG list because `<|tool_response>` is present. A direct local
  non-streaming `/v1/chat/completions` smoke call returned exact
  `GEMMA4_SMOKE_OK` content without visible template, tool, thinking, or EOG
  leakage. A tiny streaming request with `stream_options.include_usage=true`
  was accepted and returned a final usage chunk, so the local M5
  `openai-chat` path can keep the default `--openai-stream-usage include`.
  The streaming request emitted only `reasoning_content` before
  `finish_reason=length`, so Gemma 4 thinking behavior may consume an entire
  very small streaming token budget before any normal content is emitted.
- Benchpack smoke status: a single local M5
  `benchpack run smoke-chat --adapter openai-chat` reached the endpoint and
  wrote one measured row with `ok=true`, but scoring failed. The response used
  the full `max_tokens=64` completion budget on `reasoning_content`, returned
  empty normal assistant content, and did not contain `Paris`. Treat this as a
  local serving/prompt-budget blocker, not as permission to launch
  `runtime-sweep` or the four-pack matrix.
- Thinking-control status: a follow-up direct HTTP smoke with the same
  `smoke-chat` France prompt, `temperature=0`, `max_tokens=64`, and
  `stream=false` succeeded when the same local `llama-server` command added
  `--reasoning off`. The server logged `thinking = 0`, returned normal
  assistant content `The capital of France is Paris.`, omitted
  `reasoning_content`, and stopped with `finish_reason=stop`. The next local
  M5 `benchpack smoke-chat` retry should start `llama-server` with
  `--reasoning off`; `--reasoning-budget 0` remains untested because the first
  control resolved the direct smoke behavior.
- Reasoning-off benchpack smoke status: the local M5 `benchpack run
  smoke-chat --adapter openai-chat` retry passed with the same
  `--reasoning off` server command. The measured row had `ok=true`,
  `scoring.passed=true`, `finish_reason=stop`, normal assistant content
  `The capital of France is Paris.`, no `reasoning_content`, 21 prompt tokens,
  8 output tokens, and 0 cached prompt tokens. This resolves the local M5
  smoke-chat scoring blocker for this selected strict-GGUF candidate only; it
  is not M4, Hetzner, `runtime-sweep`, or four-pack matrix readiness.
- Memory note: this is a local M5 load observation only. With the settings
  above, `llama-server` reported mapped model buffers of 3287.18 MiB on MTL0
  and 2152.50 MiB on CPU, process RSS was 3614048 KiB while idle-loaded, and
  `memory_pressure` reported 84 percent free with no throttled pages. Do not
  infer M4 or Hetzner fit from this.
- Local metadata: `metadata/m5-gemma4-llama-server.json` records the full
  machine-local path, command, checksum, load notes, direct chat-completions
  smoke observations, benchpack smoke result, and dry-run status. The file is
  ignored and should not be committed by default.

## Metadata Examples

Create local ignored files under `metadata/` before launching any real matrix.
The snippets below are examples only; keep placeholders until exact artifact
and host details are verified.

M5 strict GGUF through `llama-server`:

The M5 snippet is a portable template. The captured local M5 values for this
preflight are in ignored `metadata/m5-gemma4-llama-server.json` and summarized
above.

```json
{
  "comparison_mode": "strict-same-gguf-llama-server",
  "host": {
    "label": "m5-max",
    "repo_commit": "<commit>"
  },
  "runtime": {
    "name": "llama-server",
    "version": "<llama-cpp-version>",
    "command": "llama-server --model google_gemma-4-E2B-it-Q4_K_M.gguf --host 127.0.0.1 --port 8081 --ctx-size <ctx-size> --gpu-layers <gpu-layers>",
    "endpoint": "http://127.0.0.1:8081/v1",
    "auth_env_var": null,
    "options": {
      "ctx_size": "<ctx-size>",
      "cache": "<cache-settings>",
      "batch": "<batch-settings>",
      "openai_stream_usage": "include"
    }
  },
  "model": {
    "id": "google/gemma-4-E2B-it",
    "artifact_repo": "bartowski/google_gemma-4-E2B-it-GGUF",
    "artifact_file": "google_gemma-4-E2B-it-Q4_K_M.gguf",
    "revision": "b5e99bd964eaacc27ba484bb2eb3e9f6160b9143",
    "quantization": "Q4_K_M",
    "sha256": "<checksum>"
  },
  "operating_conditions": {
    "power": "<power-notes>",
    "thermal": "<thermal-notes>",
    "background_load": "<background-load-notes>"
  },
  "notes": "Strict same-GGUF candidate; unresolved fields must be filled before live runs."
}
```

M4 strict GGUF through `llama-server`:

```json
{
  "comparison_mode": "strict-same-gguf-llama-server",
  "host": {
    "label": "m4-max",
    "repo_commit": "<commit>"
  },
  "runtime": {
    "name": "llama-server",
    "version": "<llama-cpp-version>",
    "command": "llama-server --model google_gemma-4-E2B-it-Q4_K_M.gguf --host 127.0.0.1 --port 8081 --ctx-size <ctx-size> --gpu-layers <gpu-layers>",
    "endpoint": "http://127.0.0.1:8081/v1",
    "auth_env_var": null,
    "options": {
      "ctx_size": "<ctx-size>",
      "cache": "<cache-settings>",
      "batch": "<batch-settings>",
      "openai_stream_usage": "include"
    }
  },
  "model": {
    "id": "google/gemma-4-E2B-it",
    "artifact_repo": "bartowski/google_gemma-4-E2B-it-GGUF",
    "artifact_file": "google_gemma-4-E2B-it-Q4_K_M.gguf",
    "revision": "b5e99bd964eaacc27ba484bb2eb3e9f6160b9143",
    "quantization": "Q4_K_M",
    "sha256": "<checksum>"
  },
  "operating_conditions": {
    "power": "<power-notes>",
    "thermal": "<thermal-notes>",
    "background_load": "<background-load-notes>"
  },
  "notes": "Strict same-GGUF candidate; M4 endpoint is from the M4 host's point of view."
}
```

Hetzner strict GGUF through `llama-server`:

```json
{
  "comparison_mode": "strict-same-gguf-llama-server",
  "host": {
    "label": "hetzner-cuda",
    "repo_commit": "<commit>",
    "inventory": "<gpu-driver-cuda-vram-notes>"
  },
  "runtime": {
    "name": "llama-server",
    "version": "<llama-cpp-version>",
    "command": "llama-server --model google_gemma-4-E2B-it-Q4_K_M.gguf --host <bind-host> --port <port> --ctx-size <ctx-size> --gpu-layers <gpu-layers>",
    "endpoint": "<hetzner-openai-compatible-v1-url>",
    "auth_env_var": "BENCHPACK_HETZNER_OPENAI_TOKEN",
    "options": {
      "ctx_size": "<ctx-size>",
      "cache": "<cache-settings>",
      "batch": "<batch-settings>",
      "gpu_layers": "<gpu-layers>",
      "openai_stream_usage": "include"
    }
  },
  "model": {
    "id": "google/gemma-4-E2B-it",
    "artifact_repo": "bartowski/google_gemma-4-E2B-it-GGUF",
    "artifact_file": "google_gemma-4-E2B-it-Q4_K_M.gguf",
    "revision": "b5e99bd964eaacc27ba484bb2eb3e9f6160b9143",
    "quantization": "Q4_K_M",
    "sha256": "<checksum>"
  },
  "operating_conditions": {
    "power": "<power-notes>",
    "thermal": "<thermal-or-throttle-notes>",
    "background_load": "<background-load-notes>"
  },
  "notes": "Strict same-GGUF candidate; auth env var name only, never the token value."
}
```

Optional Hetzner vLLM service-shaped mode:

```json
{
  "comparison_mode": "runtime-and-format",
  "host": {
    "label": "hetzner-cuda",
    "repo_commit": "<commit>",
    "inventory": "<gpu-driver-cuda-vram-notes>"
  },
  "runtime": {
    "name": "vLLM",
    "version": "<vllm-version>",
    "command": "vllm serve google/gemma-4-E2B-it --host <bind-host> --port <port> --max-model-len <ctx-size>",
    "endpoint": "<hetzner-openai-compatible-v1-url>",
    "auth_env_var": "BENCHPACK_HETZNER_OPENAI_TOKEN",
    "options": {
      "ctx_size": "<ctx-size>",
      "cache": "<cache-settings>",
      "batch": "<batch-or-scheduler-settings>",
      "openai_stream_usage": "include"
    }
  },
  "model": {
    "id": "google/gemma-4-E2B-it",
    "artifact_repo": "google/gemma-4-E2B-it",
    "artifact_file": null,
    "revision": "6b7e72c67d3c4556f42b56d5a68b4b8e864c63b4",
    "quantization": "<served-precision-or-quantization>",
    "sha256": "<checksum-or-revision-pin>"
  },
  "operating_conditions": {
    "power": "<power-notes>",
    "thermal": "<thermal-or-throttle-notes>",
    "background_load": "<background-load-notes>"
  },
  "notes": "Runtime-and-format fallback; the HF revision pin is the weights parity anchor, sha256 may stay null when no local checksum is captured; do not compare as strict artifact parity."
}
```

## Dry-run Matrix Commands

Always inspect the dry run before launching real tmux sessions. The helper only
assembles `benchpack run` commands; it does not read token values, contact
endpoints, or create result artifacts in `--dry-run` mode.

Local M5 strict GGUF:

```sh
scripts/benchpack-tmux-matrix \
  --dry-run \
  --session-name 'bench-m5-gemma4-llama-<stamp>' \
  --adapter openai-chat \
  --model '<gemma4-server-alias>' \
  --endpoint 'http://127.0.0.1:8081/v1' \
  --host-label-prefix 'm5-max-gemma4-llama-<stamp>' \
  --run-metadata metadata/m5-gemma4-llama-server.json
```

M4 strict GGUF over SSH. The endpoint is from the M4 host's point of view:

```sh
ssh <m4-studio-host> '
  set -eu
  cd <remote-repo>
  uv sync

  scripts/benchpack-tmux-matrix \
    --dry-run \
    --session-name "bench-m4-gemma4-llama-<stamp>" \
    --adapter openai-chat \
    --model "<gemma4-server-alias>" \
    --endpoint "http://127.0.0.1:8081/v1" \
    --host-label-prefix "m4-max-gemma4-llama-<stamp>" \
    --run-metadata metadata/m4-gemma4-llama-server.json
'
```

If the M4 workflow is local rather than SSH-launched, run the same helper
directly in the M4 repo with the M4 metadata file and host-label prefix.

Hetzner strict GGUF through an authenticated OpenAI-compatible `/v1` endpoint:

```sh
scripts/benchpack-tmux-matrix \
  --dry-run \
  --session-name 'bench-hetzner-gemma4-llama-<stamp>' \
  --adapter openai-chat \
  --model '<gemma4-server-alias>' \
  --endpoint '<hetzner-openai-compatible-v1-url>' \
  --openai-api-key-env BENCHPACK_HETZNER_OPENAI_TOKEN \
  --host-label-prefix 'hetzner-gemma4-llama-<stamp>' \
  --run-metadata metadata/hetzner-gemma4-llama-server.json
```

Hetzner service-shaped vLLM fallback:

```sh
scripts/benchpack-tmux-matrix \
  --dry-run \
  --session-name 'bench-hetzner-gemma4-vllm-<stamp>' \
  --adapter openai-chat \
  --model '<gemma4-hf-model-id-or-server-alias>' \
  --endpoint '<hetzner-openai-compatible-v1-url>' \
  --openai-api-key-env BENCHPACK_HETZNER_OPENAI_TOKEN \
  --host-label-prefix 'hetzner-gemma4-vllm-<stamp>' \
  --run-metadata metadata/hetzner-gemma4-vllm.json
```

Use `--openai-stream-usage omit` only when the selected OpenAI-compatible
server rejects `stream_options.include_usage`. Record that choice in metadata.

## Auth Boundary

For authenticated OpenAI-compatible endpoints, pass only the environment
variable name:

```sh
--openai-api-key-env BENCHPACK_HETZNER_OPENAI_TOKEN
```

Set the variable from an operator-owned secret store outside this repository.
The runner reads that environment variable only when the option is supplied and
does not implicitly read `OPENAI_API_KEY`. The tmux helper passes the name
through to `benchpack run`; it does not read, validate, or print the value.

## Pullback Policy

For remote M4 or Hetzner runs, pull back only the small artifacts required for
compare/report unless a later curated run-log entry explicitly needs more:

- `run.jsonl`
- `summary.md`
- `hardware.json`
- `run-metadata.json`

Example pattern:

```sh
mkdir -p results/<date>-<remote-host-label>

rsync -a \
  --include '/run.jsonl' \
  --include '/summary.md' \
  --include '/hardware.json' \
  --include '/run-metadata.json' \
  --exclude '*' \
  <remote-host>:<remote-repo>/results/<date>-<remote-host-label>/ \
  results/<date>-<remote-host-label>/
```

Leave `raw/`, `workspace/`, `patch/`, `task/`, `verify/`, and other generated
payloads on the source host unless a later curated run-log entry explicitly
calls for them.

## Compare And Report

After live runs exist, compare matching pack result directories. These commands
are read-only and operate on existing result directories:

```sh
uv run benchpack compare \
  results/<date>-m5-max-gemma4-llama-<stamp>-runtime \
  results/<date>-m4-max-gemma4-llama-<stamp>-runtime \
  results/<date>-hetzner-gemma4-llama-<stamp>-runtime

uv run benchpack report \
  results/<date>-m5-max-gemma4-llama-<stamp>-smoke \
  results/<date>-m4-max-gemma4-llama-<stamp>-smoke \
  results/<date>-hetzner-gemma4-llama-<stamp>-smoke \
  results/<date>-m5-max-gemma4-llama-<stamp>-runtime \
  results/<date>-m4-max-gemma4-llama-<stamp>-runtime \
  results/<date>-hetzner-gemma4-llama-<stamp>-runtime \
  results/<date>-m5-max-gemma4-llama-<stamp>-wrap \
  results/<date>-m4-max-gemma4-llama-<stamp>-wrap \
  results/<date>-hetzner-gemma4-llama-<stamp>-wrap \
  results/<date>-m5-max-gemma4-llama-<stamp>-patch \
  results/<date>-m4-max-gemma4-llama-<stamp>-patch \
  results/<date>-hetzner-gemma4-llama-<stamp>-patch
```

For service-shaped runs, compare/report commands are the same shape, but the
report notes must state that the Apple and Hetzner model artifacts differ and
that the result is runtime-and-format evidence.

## Remaining Blockers

- Post-download checksum and conservative `llama-server` load behavior are now
  captured for the local M5 first candidate only. Equivalent checksum,
  strict same-GGUF `llama-server` load behavior, and memory fit remain
  unverified on M4 and Hetzner. The Hetzner deployment-side repo has verified
  SSH/inventory and an isolated Gemma-4-capable vLLM candidate, but not
  same-GGUF llama.cpp parity or full-card Gemma 4 memory fit.
- Confirm whether the primary E2B Q4_K_M GGUF candidate is preferable to the
  upstream `ggml-org/gemma-4-E4B-it-GGUF` Q4_K_M alternative after explicit
  quality authorization; the local M5 load and minimal smoke checks are not
  benchmark quality evidence.
- Local M5 Gemma 4 thinking behavior is resolved for smoke-chat when
  `llama-server` is started with `--reasoning off`; local `runtime-sweep`
  remains the next explicit M5 performance gate before any four-pack matrix.
- Confirm strict same-GGUF llama.cpp support and memory fit on M4 and the
  Hetzner CUDA host with comparable runtime options.
- Confirm Apple MLX OpenAI-compatible serving path for the verified
  `mlx-community/gemma-4-*-it-4bit` conversions, or document that service-shaped
  Apple runs should use GGUF instead.
- Provision and test the Hetzner authenticated `/v1` token outside the repo.
- Hetzner SSH/inventory is confirmed in the sibling deployment repo, but the
  next deployment-side gate is GPU-driver/service recovery after a post-apt
  NVIDIA driver/library mismatch: `nvidia-smi` fails, `llm.service` is in
  `activating (auto-restart)`, local Qwen2.5 `/v1/models` is down, and
  management `/readyz/` reports `backend_available: false`.
- After the deployment host is healthy again, serving readiness is still
  blocked on LNB-008: an operator-approved exclusive-GPU full-card E2B load
  preflight with the resident Qwen2.5 service stopped, because Qwen2.5 occupied
  about 16.1 GiB of the 20,475 MiB RTX 4000 SFF Ada card during the first
  isolated preflight. Schedule Hetzner benchmark runs only after that preflight
  succeeds and the Qwen2.5 service has been restored and re-verified.
- On Hetzner, use the sibling readiness notes for the isolated Hugging Face
  cache layout; the complete pinned E2B weights are under the alternate
  `models--google--gemma-4-E2B-it/snapshots/...` layout, not the incomplete
  standard `hub/models--...` snapshot.
- Record runtime versions, exact server commands, endpoint URLs, context/cache
  settings, power/thermal/background state, and same repo commit before launch.
