# Qwen3.6 M4/M5 Benchmark Summary

Date: 2026-05-05

This is the compact reader-facing summary for the completed Qwen3.6 M4/M5
sweep. The detailed curated run entry remains in `docs/run-log.md`; generated
`results/*` directories are local ignored artifacts unless a later run-log
entry explicitly curates a small subset with `git add -f`.

## Scope

Hosts:

| host label | machine | memory | model id |
| --- | --- | ---: | --- |
| M5 | atlas.local, Apple M5 Max MacBook Pro | 64 GB | `Mac17,7` |
| M4 | studio, Apple M4 Max Mac Studio | 128 GB | `Mac16,9` |

Models:

| target | model | llama.cpp/Ollama artifact | MLX artifact |
| --- | --- | --- | --- |
| MoE | `Qwen3.6-35B-A3B` | GGUF `UD-Q4_K_M` | MLX `MXFP4` |
| dense | `Qwen3.6-27B` | GGUF `Q4_K_M` | MLX 4-bit |

Runtimes:

| runtime | adapter | version/path note |
| --- | --- | --- |
| llama.cpp `llama-server` | `openai-chat` | build 9020, `--reasoning off` |
| Ollama | `ollama-generate` | 0.20.5, native `/api/generate`, `num_ctx 4096` |
| MLX-LM | `openai-chat` | `mlx_lm.server` 0.31.3, `enable_thinking=false` |

Each host/runtime/model combination ran `smoke-chat`, `runtime-sweep`,
`desktop-django-wrap`, and `patch-from-failure` with local
`metadata/*.json` passed through `--run-metadata`.

## Runtime-Sweep Throughput

Median total tokens/sec, shown as M5 vs M4 for short / medium / long cases:

| runtime | model | M5 | M4 |
| --- | --- | ---: | ---: |
| llama.cpp | MoE | 91.87 / 91.41 / 91.60 | 65.98 / 72.54 / 69.35 |
| llama.cpp | dense | 24.96 / 24.25 / 23.69 | 21.66 / 21.78 / 21.25 |
| Ollama | MoE | 49.98 / 46.75 / 47.22 | 40.56 / 38.05 / 38.95 |
| Ollama | dense | 16.75 / 13.86 / 13.88 | 15.02 / 13.08 / 13.63 |
| MLX | MoE | 102.54 / 106.84 / 103.65 | 89.81 / 88.66 / 90.44 |
| MLX | dense | 29.46 / 29.92 / 29.58 | 25.46 / 25.95 / 26.02 |

## Scoring

- All `smoke-chat` and `runtime-sweep` rows were `ok=true`.
- `desktop-django-wrap` regex scoring passed for MLX on both models and hosts.
- `desktop-django-wrap` regex scoring passed for llama.cpp on both models and
  hosts.
- `desktop-django-wrap` regex scoring failed for Ollama on both models and
  hosts.
- `patch-from-failure` wrote `ok=true` rows, but the verifier failed for every
  runtime/model/host combination.

## Interpretation Notes

- Treat MLX-vs-GGUF numbers as runtime-and-format comparisons, not pure
  runtime-only comparisons, because the MLX and GGUF artifacts are not
  bit-identical.
- llama.cpp and MLX reported cache metadata for `runtime-sweep`; Ollama native
  rows reported decode timing but not cached-prompt fields, so report output
  warned about incomplete cache metadata.
- Power and thermal state were not captured.
- Background load was not intentionally controlled.
- The `desktop-django-wrap` pack is prompt-only. The `patch-from-failure` pack
  is a tiny repo-task smoke benchmark, not a broad coding-agent quality claim.

## Result Directory Patterns

Generated result directories follow these local ignored patterns:

```text
results/2026-05-05-{m5,m4}-qwen36-moe-llamacpp-153657-{smoke,runtime,wrap,patch}/
results/2026-05-05-{m5,m4}-qwen36-dense-llamacpp-154321-{smoke,runtime,wrap,patch}/
results/2026-05-05-{m5,m4}-qwen36-moe-ollama-154846-{smoke,runtime,wrap,patch}/
results/2026-05-05-{m5,m4}-qwen36-dense-ollama-155051-{smoke,runtime,wrap,patch}/
results/2026-05-05-{m5,m4}-qwen36-moe-mlx-155645-{smoke,runtime,wrap,patch}/
results/2026-05-05-{m5,m4}-qwen36-dense-mlx-155943-{smoke,runtime,wrap,patch}/
```

For remote M4 runs, only `run.jsonl`, `summary.md`, `hardware.json`, and
`run-metadata.json` were pulled back locally. Raw responses, workspaces, patch
artifacts, task logs, and verifier artifacts stayed generated/local unless a
future curated run explicitly needs them.

## Next Follow-Up

A narrow report-set manifest may be useful for naming the paired result
directories that feed `benchpack report`, but it should be designed as a small
source-only, read-only CLI shape with tests and docs. This run finalization does
not add that manifest.
