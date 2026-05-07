# Gemma 4 Strict-GGUF Tri-host Summary

Status date: 2026-05-07.

This summarizes the first compact strict same-GGUF Gemma 4 E2B Q4_K_M
four-pack evidence across the local M5, remote M4 Studio, and Hetzner CUDA
host. It is benchmark-result interpretation only; generated `results/*`
artifacts remain ignored and are not committed.

## Scope

Comparison mode: `strict-same-gguf-llama-server`.

All three hosts used the same pinned GGUF artifact:

- Model: `google/gemma-4-E2B-it`
- Artifact repo: `bartowski/google_gemma-4-E2B-it-GGUF`
- File: `google_gemma-4-E2B-it-Q4_K_M.gguf`
- Revision: `b5e99bd964eaacc27ba484bb2eb3e9f6160b9143`
- SHA-256:
  `b5310340b3a23d31655d7119d100d5df1b2d8ee17b3ca8b0a23ad7e9eb5fa705`
- Alias: `gemma4-e2b-q4km`

All runs used `llama-server` `9030 (a09a00e50)`, `openai-chat`,
`--reasoning off`, 8K context, f16 KV caches, `--parallel 1`,
`--cache-prompt`, and matching batch settings. Apple runs listened on
`127.0.0.1:8081`; Hetzner strict-lane runs listened only on
`127.0.0.1:18011` from the remote host's point of view.

This is separate from:

- the Qwen2.5 production vLLM authenticated smoke through the public Django
  Bearer-auth path;
- Gemma 4 service-shaped vLLM readiness using Hugging Face BF16 weights;
- any MLX-vs-GGUF or service-vs-strict comparison.

## Result Directories

M5:

- `results/2026-05-07-m5-max-gemma4-llama-reasoning-off-4pack-20260507-1112-smoke`
- `results/2026-05-07-m5-max-gemma4-llama-reasoning-off-4pack-20260507-1112-runtime`
- `results/2026-05-07-m5-max-gemma4-llama-reasoning-off-4pack-20260507-1112-wrap`
- `results/2026-05-07-m5-max-gemma4-llama-reasoning-off-4pack-20260507-1112-patch`

M4:

- `results/2026-05-07-m4-max-gemma4-llama-reasoning-off-4pack-20260507-1116-smoke`
- `results/2026-05-07-m4-max-gemma4-llama-reasoning-off-4pack-20260507-1116-runtime`
- `results/2026-05-07-m4-max-gemma4-llama-reasoning-off-4pack-20260507-1116-wrap`
- `results/2026-05-07-m4-max-gemma4-llama-reasoning-off-4pack-20260507-1116-patch`

Hetzner:

- `results/2026-05-07-hetzner-gex44-gemma4-llama-strict-gguf-20260507-154814-smoke`
- `results/2026-05-07-hetzner-gex44-gemma4-llama-strict-gguf-20260507-154814-runtime`
- `results/2026-05-07-hetzner-gex44-gemma4-llama-strict-gguf-20260507-161956-wrap`
- `results/2026-05-07-hetzner-gex44-gemma4-llama-strict-gguf-20260507-161956-patch`

## Outcome Matrix

| Host | `smoke-chat` | `runtime-sweep` | `desktop-django-wrap` | `patch-from-failure` |
| --- | --- | --- | --- | --- |
| M5 Max | pass: 1/1 `ok=true`, `contains` passed | pass: 9/9 `ok=true` | pass: 2/2 `ok=true`, regex passed | fail scoring: 1/1 `ok=true`, `verify-script` failed |
| M4 Max | pass: 1/1 `ok=true`, `contains` passed | pass: 9/9 `ok=true` | pass: 2/2 `ok=true`, regex passed | fail scoring: 1/1 `ok=true`, `verify-script` failed |
| Hetzner RTX 4000 SFF Ada | pass: 1/1 `ok=true`, `contains` passed | pass: 9/9 `ok=true` | pass: 2/2 `ok=true`, regex passed | fail scoring: 1/1 `ok=true`, `verify-script` failed |

The patch result is consistent across all three hosts: the adapter reached the
endpoint and produced an `ok=true` row, but deterministic verification failed.
On Hetzner, sampled task/verify artifacts showed the generated unified diff
could not be applied cleanly and the workspace was left unchanged. Treat that
as a tiny repo-task model/task-quality signal, not a serving or adapter
failure.

## Runtime Throughput

Use these numbers for performance comparison. The matching `runtime-sweep`
directories have comparable prompt/cache metadata for `short`, `medium`, and
`long`.

| Case | M5 total TPS | M4 total TPS | Hetzner total TPS | M5 decode TPS | M4 decode TPS | Hetzner decode TPS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| short | 158.45 | 137.19 | 118.49 | 164.00 | 142.55 | 122.14 |
| medium | 159.73 | 137.83 | 117.50 | 163.63 | 141.75 | 120.58 |
| long | 161.02 | 138.63 | 117.33 | 163.90 | 141.02 | 119.38 |

The runtime result says that, for this strict same-GGUF `runtime-sweep`
configuration, Hetzner is slower than both Apple hosts on decode and total
tokens/s. It does not by itself explain whether the gap comes from Metal vs
CUDA backend behavior, CPU/GPU scheduling, memory bandwidth, server build
details, or host operating conditions.

## Hetzner Workload TPS

These rows are useful for local Hetzner run inspection, but they should not be
used as cross-pack performance claims.

| Pack/case | Rows | Scoring | Total TPS | Decode TPS |
| --- | ---: | --- | ---: | ---: |
| `runtime-sweep` short | 3 | unscored, 3/3 `ok=true` | 118.49 | 122.14 |
| `runtime-sweep` medium | 3 | unscored, 3/3 `ok=true` | 117.50 | 120.58 |
| `runtime-sweep` long | 3 | unscored, 3/3 `ok=true` | 117.33 | 119.38 |
| `desktop-django-wrap` small | 1 | regex passed | 97.01 | 118.14 |
| `desktop-django-wrap` context | 1 | regex passed | 107.41 | 118.60 |
| `patch-from-failure` fix-greeting | 1 | `verify-script` failed | 108.09 | n/a |

## Interpretation Boundaries

- `runtime-sweep` is the only pack in this set suitable for token/s comparison.
- `desktop-django-wrap` is prompt-only behavior. Its value here is that regex
  scoring passed on all three hosts for the same artifact and runtime family.
- `patch-from-failure` is a tiny repo-task smoke benchmark. The consistent
  verifier failure is useful evidence, but it is not a broad coding-agent
  quality conclusion.
- The Hetzner strict lane did not use the public Django Bearer-auth endpoint or
  `BENCHPACK_HETZNER_OPENAI_TOKEN`.
- The Hetzner runs required exclusive GPU windows because production
  `llm.service` normally occupies most VRAM. Production was restored healthy
  after both strict-lane windows.

## Artifact Policy

For the remote M4 and Hetzner runs, only compact artifacts were pulled back:
`run.jsonl`, `summary.md`, `hardware.json`, and `run-metadata.json`.

Remote `raw/`, `workspace/`, `patch/`, `task/`, and `verify/` payloads stayed
on their source hosts unless explicitly sampled there to classify a result.
Generated `results/*` artifacts remain ignored and were not force-added for
this summary.
