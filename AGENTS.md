# llm-benchpacks Agent Instructions

## Repo Intent

Build a compact benchmark runner for local LLM runtimes and coding-agent-shaped
workloads. Keep benchmark packs portable across Apple Silicon, Linux CUDA hosts,
and OpenAI-compatible local servers.

## Read First

- `README.md`
- `docs/specification.md`
- `docs/architecture.md`
- `docs/implementation-plan.md`
- `docs/benchpack-format.md`
- `docs/hardware-targets.md`
- `docs/decisions.md`
- `docs/spec-log.md`
- `docs/run-log.md`

## Working Rules

- Treat benchmark packs, specs, and result schemas as source contracts.
- Keep raw generated results out of git unless a small curated artifact is
  intentionally committed.
- Prefer deterministic scoring over LLM-as-judge. If a pack uses LLM-as-judge,
  document that explicitly in the pack.
- Do not assume Apple Silicon. Linux CUDA hosts and small GPUs such as Hetzner
  GEX44-class machines are first-class targets.
- Do not hide backend-specific metrics when they are useful. Normalize common
  fields, but preserve native Ollama, llama.cpp, MLX, or CUDA timing details.
- Consult `docs/model-targets.md` when the user asks for current, preferred, or
  interesting model targets. Keep that catalog current before substantial live
  benchmark campaigns.

## Default Qwen M4/M5 Benchmark Workflow

When the user asks to benchmark "MLX vs llama.cpp vs Ollama" across the local
M5 and the M4 Studio and does not provide exact runtime/model details, use this
default workflow instead of asking for basic choices again. Ask only when a
real blocker remains, such as missing SSH access, authentication-gated model
downloads, insufficient disk, or an explicit cost/time concern.

These Qwen3.6 defaults are for explicit Qwen M4/M5 comparison work and
continuity with existing curated results. They do not override the current
preferred-target catalog in `docs/model-targets.md` for new generic model
selection questions.

Default model targets:

- MoE target: `Qwen/Qwen3.6-35B-A3B`.
- Dense target: `Qwen/Qwen3.6-27B`.
- llama.cpp/Ollama GGUF defaults:
  - `unsloth/Qwen3.6-35B-A3B-GGUF` file
    `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`.
  - `unsloth/Qwen3.6-27B-GGUF` file `Qwen3.6-27B-Q4_K_M.gguf`.
- MLX defaults:
  - `majentik/Qwen3.6-35B-A3B-MLX-MXFP4` for the MoE target.
  - `mlx-community/Qwen3.6-27B-4bit` for the dense target.

Operational defaults:

- Compare M4 vs M5 only when both hosts use the same repo commit, same
  benchmark packs, same model target, same runtime family, and comparable
  runtime options.
- Use `llama-server` on an OpenAI-compatible endpoint, normally
  `http://127.0.0.1:8081/v1`, with the GGUF file and an explicit alias.
- Use Ollama through `benchpack run --adapter ollama-generate`, preferably from
  an Ollama model created from the same GGUF file used by `llama-server`.
- Use an MLX OpenAI-compatible server on `http://127.0.0.1:8080/v1`. For the
  listed Qwen 3.6 MLX conversions, use the validated `mlx_lm.server` path with
  `--chat-template-args '{"enable_thinking":false}'`; treat `mlx-vlm` as a
  fallback only when `mlx_lm.server` cannot load the selected conversion.
- Treat MLX-vs-GGUF numbers as runtime-and-format comparisons unless the exact
  quantization and model artifact parity is documented. Do not silently
  substitute Qwen2.5, Qwen3-Coder, or another already-installed model when the
  user requested Qwen3.6.
- Run the standard four-pack matrix unless the user says otherwise:
  `smoke-chat`, `runtime-sweep`, `desktop-django-wrap`, and
  `patch-from-failure`.
- Create local, ignored `metadata/*.json` files for every host/runtime/model
  combination and pass `--run-metadata` to every pack run. Metadata should
  record the exact server command, model artifact, quantization, runtime
  version, endpoint, context/cache options, power/thermal/background notes, and
  whether the run is a strict artifact-parity comparison or a
  runtime-and-format comparison. The `.gitignore` metadata rule keeps these
  machine-local files out of normal commits.
- Use `scripts/benchpack-tmux-matrix --dry-run` before launching each runtime
  matrix. Launch real benchmark matrices in tmux only after the dry run shows
  the intended commands. Keep `--force` opt-in. When adding or changing tmux
  helpers, wrap scripted window commands with an explicit POSIX shell such as
  `/bin/sh -c`; do not assume tmux's default shell is POSIX-compatible.
- For remote M4 runs, run the same setup and benchmark commands over SSH in the
  remote repo. Pull back only `run.jsonl`, `summary.md`, `hardware.json`, and
  `run-metadata.json`; leave `raw/`, `workspace/`, `patch/`, `task/`, and
  `verify/` local unless a curated run-log entry explicitly needs them.
- After local and remote runs finish, use `benchpack report` over the paired
  result directories. Do not commit generated `results/*` artifacts unless a
  small curated subset is intentionally force-added with a `docs/run-log.md`
  entry.

## Spec And Log Discipline

- Update `docs/specification.md` when behavior, result schema, CLI shape, or pack
  semantics change.
- Update `docs/architecture.md` when component boundaries, adapter contracts, or
  result envelopes change.
- Update `docs/benchpack-format.md` when manifest fields, case kinds, or scoring
  modes change.
- Update `docs/hardware-targets.md` when supported targets or hardware metadata
  fields change.
- Add durable design choices to `docs/decisions.md`.
- Add dated design movement and open questions to `docs/spec-log.md`.
- Add curated benchmark outcomes to `docs/run-log.md`.
- Update documentation in the same change as implementation.

## Validation

- Repo-level validation command: `uv run pytest`.
- For documentation-only changes, additionally review links and check
  `git status --short`.
- For end-to-end checks, run the smoke pack against a reachable endpoint, e.g.
  `uv run benchpack run smoke-chat --adapter ollama-generate --model <model>`.
