# Qwen3.6 27B Strict-GGUF Tri-host Preflight Summary

Status date: 2026-05-10.

This summarizes the narrow strict same-GGUF Qwen3.6 27B preflight across the
local M5, remote M4 Studio, and Hetzner CUDA host. It covers load,
`smoke-chat`, and one deterministic endpoint-only repo-task pack. It is not a
full four-pack matrix or a default benchmark promotion.

## Scope

Comparison mode: `strict-same-gguf-llama-server`.

All three hosts used the same GGUF artifact:

- Model: `Qwen/Qwen3.6-27B`
- Artifact repo: `unsloth/Qwen3.6-27B-GGUF`
- File: `Qwen3.6-27B-Q4_K_M.gguf`
- SHA-256:
  `5ed60d0af4650a854b1755bd392f9aef4872643dc25a254bc68043fa638392a0`
- Alias: `qwen36-27b-q4km`

All runs used `llama-server`, `openai-chat`, `--reasoning off`, 4K context,
f16 KV caches, `--parallel 1`, `--cache-prompt`, and matching batch settings
where the platform allowed them. The local M5 and M4 listened on
`127.0.0.1:18082`; the Hetzner strict-lane server also listened only on
`127.0.0.1:18082` from the remote host's point of view.

This is separate from:

- Qwen2.5 production vLLM evidence through the public Django Bearer-auth path;
- Qwen3-Coder Ollama or external-agent direct-edit evidence;
- any MLX-vs-GGUF or service-vs-strict comparison.

## Result Directories

M5:

- `results/2026-05-09-m5-max-qwen36-27b-llamacpp-recount-preflight-20260509-215133-smoke`
- `results/2026-05-09-m5-max-qwen36-27b-llamacpp-recount-preflight-20260509-215133-endpoint-correctness`

M4:

- `results/2026-05-09-m4-max-qwen36-27b-llamacpp-strict-preflight-20260509-220411-smoke`
- `results/2026-05-09-m4-max-qwen36-27b-llamacpp-strict-preflight-20260509-220411-endpoint-correctness`

Hetzner:

- `results/2026-05-10-hetzner-gex44-qwen36-27b-llamacpp-strict-preflight-20260509-234711-smoke`
- `results/2026-05-10-hetzner-gex44-qwen36-27b-llamacpp-strict-preflight-20260509-234711-endpoint-correctness`

## Outcome Matrix

| Host | Runtime build | `smoke-chat` | `endpoint-python-correctness` |
| --- | --- | --- | --- |
| M5 Max | `llama-server` 9090 (`5757c4dcb`), Metal | pass: 1/1 `ok=true`, contains passed, total TPS 15.64 | pass: `ok=true`, `verify_exit=0`, `patch_bytes=1284`, total TPS 23.79 |
| M4 Max | `llama-server` 9080 (`9f5f0e689`), Metal | pass: 1/1 `ok=true`, contains passed, total TPS 10.39 | pass: `ok=true`, `verify_exit=0`, `patch_bytes=1284`, total TPS 18.09 |
| Hetzner RTX 4000 SFF Ada | `llama-server` 9030 (`a09a00e50`), CUDA | pass: 1/1 `ok=true`, contains passed, total TPS 10.93 | pass: `ok=true`, `verify_exit=0`, `patch_bytes=1419`, total TPS 13.78 |

All observed failures from the earlier local M5 pre-recount run are superseded
for this preflight by the recount-capable runner path. The M4 and Hetzner runs
both used the recount-capable worktree state.

## Interpretation Boundaries

- This establishes same-artifact load plus one smoke and one deterministic
  endpoint-coding pass on all three hosts.
- The two-pack set is intentionally narrow. It does not replace the standard
  four-pack matrix and does not justify broad coding-agent quality claims.
- Throughput values are useful for basic preflight sizing only. The run does
  not include `runtime-sweep`, controlled thermal/power capture, or a broader
  repeated performance matrix.
- Hetzner used a local-only loopback `llama-server`; it did not use the public
  Django Bearer-auth API path or `BENCHPACK_HETZNER_OPENAI_TOKEN`.
- The Hetzner strict lane required an exclusive GPU window because production
  `llm.service` normally occupies most VRAM. Production was restored healthy
  after the run.

## Artifact Policy

For the remote M4 and Hetzner runs, only compact artifacts were pulled back:
`run.jsonl`, `summary.md`, `hardware.json`, and `run-metadata.json`.

Remote `raw/`, `workspace/`, `patch/`, `task/`, and `verify/` payloads stayed on
their source hosts. Generated `results/*` artifacts remain ignored and were
not force-added for this summary.
