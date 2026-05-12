# Gemma 4 26B A4B Strict-GGUF Tri-host Summary

Status date: 2026-05-12.

This summarizes the completed Gemma 4 26B A4B Q4_K_M strict same-GGUF
campaign across the local M5, remote M4 Studio, and Hetzner CUDA host. It is a
compact reading path for the expensive 2026-05-12 lane; generated `results/*`
artifacts remain ignored and are not committed.

## Scope

Comparison mode: `strict-same-gguf-llama-server`.

All three hosts used the same pinned GGUF artifact:

- Base model: `google/gemma-4-26B-A4B-it`
- Base revision: `462a98a12e28e2cbcfccaf78fe41e3e50235e6ae`
- GGUF repo: `ggml-org/gemma-4-26B-A4B-it-GGUF`
- GGUF repo revision: `ae4d537a6345467d1c86bb5cc0d4505ff3ebe0f3`
- File: `gemma-4-26B-A4B-it-Q4_K_M.gguf`
- File size: `16,796,015,136` bytes
- SHA-256:
  `88f4a13b0bb95f031a7fad973e10854122fb67ebc34d214d39a2f65053046abc`
- Alias: `gemma4-26b-a4b-q4km`

All runs used `llama-server`, `openai-chat`, `--reasoning off`, 4K context,
f16 KV caches, `--parallel 1`, `--cache-prompt`, `--batch-size 1024`, and
`--ubatch-size 512`. The benchmark endpoint was loopback
`http://127.0.0.1:18083/v1` on each host.

This is separate from:

- Gemma 4 E2B strict-GGUF evidence in
  `docs/gemma4-strict-gguf-trihost-summary.md`;
- Qwen2.5 production vLLM authenticated smoke through the public Django
  Bearer-auth path;
- Gemma 4 service-shaped vLLM readiness using Hugging Face BF16 weights;
- any MLX-vs-GGUF, Ollama, public API, or external-agent comparison.

## Result Directories

M5 local preflight and default-evidence set:

- `results/2026-05-12-m5-max-gemma4-26b-a4b-llamacpp-strict-preflight-smoke-20260512`
- `results/2026-05-12-m5-max-gemma4-26b-a4b-llamacpp-strict-preflight-runtime-20260512`
- `results/2026-05-12-m5-max-gemma4-26b-a4b-llamacpp-strict-preflight-wrap-20260512`
- `results/2026-05-12-m5-max-gemma4-26b-a4b-llamacpp-strict-preflight-patch-20260512`
- `results/2026-05-12-m5-max-gemma4-26b-a4b-llamacpp-strict-preflight-tool-json-20260512`
- `results/2026-05-12-m5-max-gemma4-26b-a4b-llamacpp-strict-preflight-endpoint-correctness-20260512`
- `results/2026-05-12-m5-max-gemma4-26b-a4b-llamacpp-strict-preflight-python-regression-20260512`
- `results/2026-05-12-m5-max-gemma4-26b-a4b-llamacpp-strict-preflight-dashboard-regression-20260512`
- `results/2026-05-12-m5-max-gemma4-26b-a4b-llamacpp-strict-preflight-mini-project-20260512`

M4 preflight and four-pack matrix:

- `results/2026-05-12-m4-max-gemma4-26b-a4b-llamacpp-strict-preflight-20260512-smoke`
- `results/2026-05-12-m4-max-gemma4-26b-a4b-llamacpp-strict-preflight-20260512-runtime`
- `results/2026-05-12-m4-max-gemma4-26b-a4b-llamacpp-strict-preflight-20260512-endpoint-correctness`
- `results/2026-05-12-m4-max-gemma4-26b-a4b-llamacpp-strict-fourpack-20260512-{smoke,runtime,wrap,patch}`

Hetzner preflight and four-pack matrix:

- `results/2026-05-12-hetzner-gex44-gemma4-26b-a4b-llamacpp-strict-preflight-20260512-smoke`
- `results/2026-05-12-hetzner-gex44-gemma4-26b-a4b-llamacpp-strict-preflight-20260512-runtime`
- `results/2026-05-12-hetzner-gex44-gemma4-26b-a4b-llamacpp-strict-fourpack-20260512-{smoke,runtime,wrap,patch}`

## Host And Runtime Setup

| Host | Runtime build | Endpoint | Model path | Checksum and load note |
| --- | --- | --- | --- | --- |
| M5 Max | `llama-server` 9090 (`5757c4dcb`), Metal | `http://127.0.0.1:18083/v1` | `/Users/jochen/models/gguf/gemma4-26b-a4b/gemma-4-26B-A4B-it-Q4_K_M.gguf` | SHA-256 matched; all 31/31 layers offloaded; projected about 16,900 MiB device memory; RSS about 16,966,528 KiB after load |
| M4 Max | `llama-server` 9110 (`ef22b3e4a`), Metal | `http://127.0.0.1:18083/v1` | `/Users/jochen/models/gguf/gemma4-26b-a4b/gemma-4-26B-A4B-it-Q4_K_M.gguf` | SHA-256 matched; all 31/31 layers offloaded; RSS about 16,965,936 KiB after load |
| Hetzner RTX 4000 SFF Ada | CUDA `llama-server` 9030 (`a09a00e50`) | `http://127.0.0.1:18083/v1` | `/var/lib/llm/gemma4-26b-a4b-gguf/gemma-4-26B-A4B-it-Q4_K_M.gguf` | SHA-256 matched; projected 16,915 MiB device memory against 19,850 MiB free; about 2,934 MiB left free; `nvidia-smi` showed about 17,116 MiB used after load |

Apple command shape:

```sh
llama-server --model /Users/jochen/models/gguf/gemma4-26b-a4b/gemma-4-26B-A4B-it-Q4_K_M.gguf --alias gemma4-26b-a4b-q4km --host 127.0.0.1 --port 18083 --ctx-size 4096 --batch-size 1024 --ubatch-size 512 --cache-type-k f16 --cache-type-v f16 --gpu-layers auto --parallel 1 --cache-prompt --no-webui --reasoning off
```

Hetzner command shape:

```sh
/opt/llm/lnb011-llama-cpp-a09a00e50/build-cuda/bin/llama-server --model /var/lib/llm/gemma4-26b-a4b-gguf/gemma-4-26B-A4B-it-Q4_K_M.gguf --alias gemma4-26b-a4b-q4km --host 127.0.0.1 --port 18083 --ctx-size 4096 --batch-size 1024 --ubatch-size 512 --cache-type-k f16 --cache-type-v f16 --gpu-layers auto --parallel 1 --cache-prompt --no-webui --reasoning off
```

## Preflight Outcome

Direct non-streaming smoke returned exact `GEMMA4_26B_SMOKE_OK` on all three
hosts.

| Host | Preflight result |
| --- | --- |
| M5 Max | `smoke-chat` passed; `runtime-sweep` wrote 9/9 `ok=true`; `desktop-django-wrap` passed both regex cases; `patch-from-failure` passed; `tool-json` passed both schema cases |
| M4 Max | `smoke-chat` passed; `runtime-sweep` wrote 9/9 `ok=true`; `endpoint-python-correctness` reached the endpoint with adapter `ok=true` but failed deterministic verification after a source mutation |
| Hetzner RTX 4000 SFF Ada | Memory fit was confirmed before benchmarks; direct smoke passed; `smoke-chat` passed; `runtime-sweep` wrote 9/9 `ok=true` |

The M4 `endpoint-python-correctness` failure is model/task-quality evidence,
not a serving failure. Local M5 broader repo-task evidence was also mixed: 2/5
deterministic verifier passes across the stronger repo-task set.

## Four-Pack Outcome

The default four-pack passed on all three hosts:
`smoke-chat`, `runtime-sweep`, `desktop-django-wrap`, and
`patch-from-failure`.

| Host | `smoke-chat` | `runtime-sweep` | `desktop-django-wrap` | `patch-from-failure` |
| --- | --- | --- | --- | --- |
| M5 Max | pass: contains scoring passed, total TPS 53.16 | pass: 9/9 `ok=true` | pass: 2/2 regex rows | pass: verifier passed, total TPS 85.94 |
| M4 Max | pass: contains scoring passed, total TPS 33.94 | pass: 9/9 `ok=true` | pass: 2/2 regex rows | pass: verifier passed, total TPS 61.79 |
| Hetzner RTX 4000 SFF Ada | pass: contains scoring passed, total TPS 25.51 | pass: 9/9 `ok=true` | pass: 2/2 regex rows | pass: verifier passed, total TPS 53.38 |

## Runtime Throughput

Use these rows for performance comparison within this lane. The matching
`runtime-sweep` compare reported `prefill parity=comparable` for short,
medium, and long.

| Case | M5 total TPS | M4 total TPS | Hetzner total TPS | Prefill parity |
| --- | ---: | ---: | ---: | --- |
| short | 106.99 | 87.58 | 72.51 | comparable |
| medium | 108.70 | 89.08 | 71.93 | comparable |
| long | 107.65 | 87.25 | 68.91 | comparable |

The M5 local preflight run log also recorded TTFT at about 28-32 ms on
measured rows. This summary does not add unsourced TTFT, prefill TPS, or decode
TPS values beyond the recorded compare output.

## Hetzner Production Window

The existing Hetzner checkout at `/Users/jochen/projects/llm-benchpacks` was
dirty at `38f2017` and was preserved untouched. The campaign used a clean
detached checkout cloned from a local git bundle at
`/Users/jochen/projects/llm-benchpacks-gemma4-26b-20260512`, checked out at
`20667e7`.

Before stopping production, `llm.service`, `llm-mgmt.service`, and
`caddy.service` were active/enabled. Public `/healthz/` returned 200,
`/readyz/` returned 200 with `backend_available=true`, unauthenticated
`/v1/models` returned 401, and production vLLM GPU memory was about
18,328 MiB.

Production `llm.service` was stopped only for the exclusive GPU window. After
the strict-lane runs, the temporary server was stopped and production
`llm.service` was restarted. Final checks returned `/healthz/` 200,
`/readyz/` 200 with `backend_available=true`, unauthenticated `/v1/models`
401, no strict-lane listener on port 18083, and GPU memory back around
18.3 GiB.

## Interpretation Boundaries

- This establishes same-artifact load, direct endpoint smoke, default
  four-pack behavior, and runtime throughput for this exact Gemma 4 26B A4B
  Q4_K_M `llama-server --reasoning off` lane.
- `runtime-sweep` is the only pack in this summary intended for token/s
  comparison.
- `desktop-django-wrap` is prompt-only behavior. Its value here is that regex
  scoring passed on all three hosts for the same artifact and runtime family.
- `patch-from-failure` is a tiny repo-task smoke benchmark. Passing it on all
  three hosts is useful narrow evidence, not broad coding-agent quality proof.
- The M4 endpoint-correctness caveat and local M5 stronger repo-task results
  keep broader repo-task packs explicit opt-in paths for this artifact.
- Hetzner strict-lane runs used local loopback `llama-server`; they did not use
  the public Django Bearer-auth API path or `BENCHPACK_HETZNER_OPENAI_TOKEN`.
- This summary does not compare against service-shaped vLLM, MLX, Ollama,
  public API, external-agent, or other model artifacts.
- Power and thermal conditions were not controlled beyond the notes already
  recorded in the run log and runbook.

## Artifact Policy

For the remote M4 and Hetzner runs, only compact artifacts were pulled back:
`run.jsonl`, `summary.md`, `hardware.json`, and `run-metadata.json`.

Remote `raw/`, `workspace/`, `patch/`, `task/`, and `verify/` payloads stayed
on their source hosts. Generated `results/*` artifacts remain ignored and were
not force-added for this summary. Ignored metadata files remain under
`metadata/*gemma4-26b-a4b-llamacpp-strict-preflight-20260512.json`.
