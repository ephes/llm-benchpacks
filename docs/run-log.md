# Run Log

Curated benchmark runs should be recorded here. Raw artifacts under
`results/*/raw/` are ignored by default; a curated `summary.md`, `hardware.json`,
and (when small) `run.jsonl` may be committed alongside.

| Date | Host | Runtime | Model | Pack | Result | Artifacts | Notes |
|------|------|---------|-------|------|--------|-----------|-------|
| 2026-04-30 | atlas.local (Apple M5 Max, 64 GB) | `llama-server` 8980 (`41a63be28`) through `openai-chat` | `qwen2.5-0.5b-instruct-q4_k_m`; GGUF `Q4_K_M` | `desktop-django-wrap` 0.1.5 | fail: 0/2 rows passed `regex` scoring, while both rows had `ok=true` and timing/token fields populated | `results/2026-04-30-llama-server-desktop-django-wrap/summary.md`; `results/2026-04-30-llama-server-desktop-django-wrap/run.jsonl` | Server command: `llama-server --model /Users/jochen/models/gguf/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf --alias qwen2.5-0.5b-instruct-q4_k_m --host 127.0.0.1 --port 8081 --ctx-size 4096 --gpu-layers auto`. Endpoint `http://127.0.0.1:8081/v1` resolved to `/v1/chat/completions`; `stream_options.include_usage` was accepted. `wrap-plan-small` emitted 384 output tokens and was cut off after starting to copy the fixture; `wrap-plan-context` emitted 342 output tokens and copied the appended fixture instead of the required skeleton. Raw requests confirmed prompt-only file fixture assembly: `synthetic-django-app` was appended, while the directory-shaped `synthetic-django-repo` fixture was not injected. Model SHA256: `6eb923e7d26e9cea28811e1a8e852009b21242fb157b26149d3b188f3a8c8653`. |
| 2026-04-29 | atlas.local (Apple M5 Max, 64 GB) | `llama-server` 8960 (`19821178b`) through `openai-chat` | `qwen2.5-0.5b-instruct-q4_k_m`; GGUF `Q4_K_M` | `smoke-chat` 0.1.0 | pass: 1/1 row `ok=true`, `contains` scoring passed | `results/2026-04-29-llama-server-smoke/summary.md` | Server command: `llama-server --model /Users/jochen/models/gguf/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf --alias qwen2.5-0.5b-instruct-q4_k_m --host 127.0.0.1 --port 8081 --ctx-size 4096 --gpu-layers auto`. Endpoint `http://127.0.0.1:8081/v1` resolved to `/v1/chat/completions`. Model SHA256: `6eb923e7d26e9cea28811e1a8e852009b21242fb157b26149d3b188f3a8c8653`. |
| 2026-04-29 | atlas.local (Apple M5 Max, 64 GB) | `llama-server` 8960 (`19821178b`) through `openai-chat` | `qwen2.5-0.5b-instruct-q4_k_m`; GGUF `Q4_K_M` | `runtime-sweep` 0.1.0 | pass: 9/9 measured rows `ok=true` with TTFT, prefill TPS, decode TPS, and output tokens populated | `results/2026-04-29-llama-server-runtime/summary.md` | `stream_options.include_usage` was accepted. One warmup per case produced local raw files only; no warmup rows appear in `run.jsonl`. Warmup primed the llama.cpp prompt cache for every measured row: short 103/104, medium 375/376, and long 810/811 prompt tokens were cached. The prefill TPS in this run is warm-cache behavior and should not be compared directly with `mlx_lm.server` prefill TPS without cache parity. |
| 2026-04-29 | atlas.local (Apple M5 Max, 64 GB) | `llama-server` through `openai-chat` | n/a | `smoke-chat` 0.1.0 and `runtime-sweep` 0.1.0 | blocked: no live rows generated | local | Rechecked on branch `phase2-llama-server-live-validation` before running benchmarks. `llama-server`, `llama.cpp-server`, `llama-cpp-server`, and `llama-cli` were not on `PATH`; `llama-server --help` and `--version` failed with `command not found`. Executable searches covered `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin`, `~/bin`, `~/projects`, Homebrew package metadata, `/opt/homebrew`, `/usr/local`, `~/Projects`, and `$HOME`; model searches covered `~/.cache`, `~/models`, `~/.local/share`, `~/Library/Caches`, `/opt/homebrew`, `~/Projects`, `~/projects`, and Spotlight. No startup command, endpoint, model label, quantization, or `.gguf` model file could be verified, so the benchmark commands were not run. |
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
- For curated Apple Silicon M4/M5 comparison entries, copy the runbook's
  report checklist into the notes: identify host fields from `hardware.json`
  separately from manual runtime/server, model, quantization, checksum,
  context, cache, power, thermal, and background-load notes.
- When citing `benchpack compare` for M4/M5 runs, record any warnings and the
  `prefill parity` status for the relevant cases. Do not turn
  `desktop-django-wrap` or `patch-from-failure` into broad coding-agent claims;
  describe their prompt-only or tiny repo-task-smoke scope.
