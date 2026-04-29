# Run Log

Curated benchmark runs should be recorded here. Raw artifacts under
`results/*/raw/` are ignored by default; a curated `summary.md`, `hardware.json`,
and (when small) `run.jsonl` may be committed alongside.

| Date | Host | Runtime | Model | Pack | Result | Artifacts | Notes |
|------|------|---------|-------|------|--------|-----------|-------|
| 2026-04-29 | atlas.local (Apple M5 Max, 64 GB) | `llama-server` through `openai-chat` | n/a | `smoke-chat` 0.1.0 and `runtime-sweep` 0.1.0 | blocked: no live rows generated | local | `llama-server`, `llama.cpp-server`, `llama-cpp-server`, and `llama-cli` were not on `PATH`; `llama-server --help` and `--version` failed with `command not found`; no local GGUF model file was found. No server command or endpoint could be verified, so the benchmark commands were not run. |
| 2026-04-28 | atlas.local (Apple M5 Max, 64 GB) | `mlx_lm.server` 0.31.3 through `openai-chat` | `mlx-community/Qwen2.5-0.5B-Instruct-4bit` | `smoke-chat` 0.1.0 | pass: 1/1 row `ok=true`, `contains` scoring passed | `results/2026-04-28-mlx-lm-smoke/summary.md` | Cold model/server path for this pack: no pack warmup. Endpoint `http://localhost:8080/v1` resolved to `/v1/chat/completions`; server command is in the summary. |
| 2026-04-28 | atlas.local (Apple M5 Max, 64 GB) | `mlx_lm.server` 0.31.3 through `openai-chat` | `mlx-community/Qwen2.5-0.5B-Instruct-4bit` | `runtime-sweep` 0.1.0 | pass: 9/9 measured rows `ok=true` with TTFT, prefill TPS, decode TPS, and output tokens populated | `results/2026-04-28-mlx-lm-runtime/summary.md` | Warm measured rows after one pack warmup per case. `stream_options.include_usage` was accepted; warmup raw files were generated locally under `raw/`, with no warmup rows in `run.jsonl`. |
| 2026-04-26 | n/a | n/a | n/a | n/a | repo created | n/a | Initial documentation scaffold only. |

## Run Entry Guidance

- Use stable host labels such as `m5-mbp-64gb` or `hetzner-gex44`. Result
  directories follow `<date>-<host-label>` (e.g. `2026-04-26-m5-mbp-64gb`).
  Validation slices may use workload-shaped labels when the plan prescribes
  them, but the host column and `hardware.json` should still identify the
  actual machine.
- Include runtime version in the artifact summary.
- Record whether the model was cold or warm.
- Link to committed summaries (and `run.jsonl` when it accompanies a curated
  run), not large raw responses.
- The `Artifacts` column should hold a repo-relative path to a committed
  `summary.md` (e.g. `results/2026-04-26-m5-mbp-64gb/summary.md`). Use `local`
  when nothing was committed, or an external URL for remote-host runs whose
  artifacts live elsewhere.
- If a run is exploratory and not comparable, say that explicitly.
