# Run Log

Curated benchmark runs should be recorded here. Raw artifacts under
`results/*/raw/` are ignored by default; a curated `summary.md`, `hardware.json`,
and (when small) `run.jsonl` may be committed alongside.

| Date | Host | Runtime | Model | Pack | Result | Artifacts | Notes |
|------|------|---------|-------|------|--------|-----------|-------|
| 2026-04-28 | atlas.local (Apple M5 Max, 64 GB) | `mlx_lm.server` 0.31.3 through `openai-chat` | `mlx-community/Qwen2.5-0.5B-Instruct-4bit` | `smoke-chat` 0.1.0 | pass: 1/1 row `ok=true`, `contains` scoring passed | `results/2026-04-28-mlx-lm-smoke/summary.md` | Server command used `uvx --from mlx-lm mlx_lm.server --model mlx-community/Qwen2.5-0.5B-Instruct-4bit --host 127.0.0.1 --port 8080`; endpoint `http://localhost:8080/v1` resolved to `/v1/chat/completions`. |
| 2026-04-28 | atlas.local (Apple M5 Max, 64 GB) | `mlx_lm.server` 0.31.3 through `openai-chat` | `mlx-community/Qwen2.5-0.5B-Instruct-4bit` | `runtime-sweep` 0.1.0 | pass: 9/9 measured rows `ok=true` with TTFT, prefill TPS, decode TPS, and output tokens populated | `results/2026-04-28-mlx-lm-runtime/summary.md` | `stream_options.include_usage` was accepted. Warmup raw files were generated locally under `raw/`, but no warmup rows appear in `run.jsonl`. |
| 2026-04-26 | n/a | n/a | n/a | n/a | repo created | n/a | Initial documentation scaffold only. |

## Run Entry Guidance

- Use stable host labels such as `m5-mbp-64gb` or `hetzner-gex44`. Result
  directories follow `<date>-<host-label>` (e.g. `2026-04-26-m5-mbp-64gb`).
- Include runtime version in the artifact summary.
- Record whether the model was cold or warm.
- Link to committed summaries (and `run.jsonl` when it accompanies a curated
  run), not large raw responses.
- The `Artifacts` column should hold a repo-relative path to a committed
  `summary.md` (e.g. `results/2026-04-26-m5-mbp-64gb/summary.md`). Use `local`
  when nothing was committed, or an external URL for remote-host runs whose
  artifacts live elsewhere.
- If a run is exploratory and not comparable, say that explicitly.
