# Qwen3.6 27B Strict-GGUF Tri-host Summary

Status date: 2026-05-10.

This summarizes the strict same-GGUF Qwen3.6 27B lane across the local M5,
remote M4 Studio, and Hetzner CUDA host. The lane now covers load,
`smoke-chat`, `endpoint-python-correctness`, and the default four-pack matrix.
It is still scoped to this exact artifact and runtime setup.

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
where the platform allowed them. The benchmark endpoint was loopback
`http://127.0.0.1:18082/v1` on each host.

This is separate from Qwen2.5 production vLLM evidence through the public
Django Bearer-auth path, Qwen3-Coder Ollama or external-agent evidence, and any
MLX-vs-GGUF or service-vs-strict comparison.

## Result Directories

Preflight:

- `results/2026-05-09-m5-max-qwen36-27b-llamacpp-recount-preflight-20260509-215133-smoke`
- `results/2026-05-09-m5-max-qwen36-27b-llamacpp-recount-preflight-20260509-215133-endpoint-correctness`
- `results/2026-05-09-m4-max-qwen36-27b-llamacpp-strict-preflight-20260509-220411-smoke`
- `results/2026-05-09-m4-max-qwen36-27b-llamacpp-strict-preflight-20260509-220411-endpoint-correctness`
- `results/2026-05-10-hetzner-gex44-qwen36-27b-llamacpp-strict-preflight-20260509-234711-smoke`
- `results/2026-05-10-hetzner-gex44-qwen36-27b-llamacpp-strict-preflight-20260509-234711-endpoint-correctness`

Four-pack matrix:

- `results/2026-05-10-m5-max-qwen36-27b-llamacpp-strict-fourpack-20260510-131758-{smoke,runtime,wrap,patch}`
- `results/2026-05-10-m4-max-qwen36-27b-llamacpp-strict-fourpack-20260510-131758-{smoke,runtime,wrap,patch}`
- `results/2026-05-10-hetzner-gex44-qwen36-27b-llamacpp-strict-fourpack-20260510-131758-{smoke,runtime,wrap,patch}`

## Preflight Outcome

| Host | Runtime build | `smoke-chat` | `endpoint-python-correctness` |
| --- | --- | --- | --- |
| M5 Max | `llama-server` 9090 (`5757c4dcb`), Metal | pass: total TPS 15.64 | pass: `verify_exit=0`, `patch_bytes=1284`, total TPS 23.79 |
| M4 Max | `llama-server` 9080 (`9f5f0e689`), Metal | pass: total TPS 10.39 | pass: `verify_exit=0`, `patch_bytes=1284`, total TPS 18.09 |
| Hetzner RTX 4000 SFF Ada | `llama-server` 9030 (`a09a00e50`), CUDA | pass: total TPS 10.93 | pass: `verify_exit=0`, `patch_bytes=1419`, total TPS 13.78 |

All observed failures from the earlier local M5 pre-recount run are superseded
for this lane by the recount-capable runner path.

## Four-Pack Outcome

All three hosts completed `smoke-chat`, `runtime-sweep`, `desktop-django-wrap`,
and `patch-from-failure` without command failures. Scored cases passed
everywhere: smoke contains scoring, both wrap regex cases, and the
`patch-from-failure` verifier.

Runtime-sweep median total TPS:

| Case | M5 Max | M4 Max | Hetzner RTX 4000 SFF Ada |
| --- | ---: | ---: | ---: |
| short | 25.04 | 21.19 | 14.44 |
| medium | 24.26 | 21.39 | 14.44 |
| long | 23.07 | 21.84 | 14.31 |

Runtime-sweep compare reported `prefill parity=comparable` for short, medium,
and long, with complete cached-prompt metadata on all three hosts.

Other scored four-pack outcomes:

| Pack / case | M5 Max | M4 Max | Hetzner RTX 4000 SFF Ada |
| --- | ---: | ---: | ---: |
| `smoke-chat` total TPS | 15.30 | 11.82 | 11.15 |
| `desktop-django-wrap` small total TPS | 19.75 | 16.38 | 12.99 |
| `desktop-django-wrap` context total TPS | 19.04 | 15.81 | 12.81 |
| `patch-from-failure` total TPS | 18.85 | 13.64 | 12.17 |

`patch-from-failure` passed with `verify_exit=0` on all three hosts.

## Interpretation Boundaries

- This establishes same-artifact load, endpoint sanity, runtime performance,
  prompt-only wrap scoring, one endpoint-only Python correctness task, and one
  tiny repo-mutating fenced-patch verifier task on all three hosts.
- It is strong evidence for this exact Qwen3.6 27B Q4_K_M strict-GGUF
  `llama-server --reasoning off` lane.
- It does not justify broad coding-agent quality claims and should not be
  generalized to unrelated Ollama, MLX, public API, or external-agent lanes.
- Power and thermal conditions were not explicitly controlled on Apple hosts.
  Hetzner used an exclusive GPU window because production `llm.service`
  normally occupies most VRAM.
- Hetzner used a local-only loopback `llama-server`; it did not use the public
  Django Bearer-auth API path or `BENCHPACK_HETZNER_OPENAI_TOKEN`.

## Artifact Policy

For the remote M4 and Hetzner runs, only compact artifacts were pulled back:
`run.jsonl`, `summary.md`, `hardware.json`, and `run-metadata.json`.

Remote `raw/`, `workspace/`, `patch/`, `task/`, and `verify/` payloads stayed on
their source hosts. Generated `results/*` artifacts remain ignored and were not
force-added for this summary.
