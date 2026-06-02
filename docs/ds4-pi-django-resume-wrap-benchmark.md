# DS4 Pi Django Resume Wrap Benchmark

Status: manual external-agent benchmark setup, not a `benchpack run` pack yet.

This benchmark is the real repo-mutating follow-up to the synthetic
`desktop-django-wrap` prompt pack. It asks Pi, backed by local DS4 / DeepSeek V4
Flash, to wrap a clean `django-resume` worktree in Electron using
`desktop-django-starter`'s staged workflow.

## Workspace

The prepared workspace is:

```sh
cd ~/workspaces/ds4-pi-django-resume
```

It was created with `desktop-django-lab` and contains paired worktrees:

- `django-resume`: target worktree from `origin/main` at
  `ccbd5cf34ecd2cabbfc392476a31bb531db1bef4`, branch
  `desktop-lab/ds4-pi-django-resume`
- `desktop-django-starter`: starter worktree from `origin/main` at
  `805f621a002ed50978af49d09a5ed4859447560f`, branch
  `desktop-lab/ds4-pi-django-resume`
- `ds4-pi`: local checkout of `https://github.com/mitsuhiko/ds4`, branch
  `pi-polish`, patched locally to prefer `q2-imatrix`/`q4-imatrix`

The existing dirty exploratory workspace at `~/workspaces/tmp/django-resume`
was left untouched.

## Local DS4/Pi Setup

The local Pi extension is installed as symlinks:

```text
~/.pi/agent/extensions/pi-sd4-provider.ts -> ~/workspaces/ds4-pi-django-resume/ds4-pi/pi-sd4-provider.ts
~/.pi/ds4/support -> ~/workspaces/ds4-pi-django-resume/ds4-pi
```

The DS4 model path is the existing preferred imatrix GGUF:

```text
~/src/ds4/gguf/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf
```

The workspace `ds4-pi` checkout has:

- `gguf -> ~/src/ds4/gguf`
- `ds4flash.gguf -> ~/src/ds4/gguf/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf`
- a built `ds4-server`

Verify Pi provider discovery without starting inference:

```sh
cd ~/workspaces/ds4-pi-django-resume/django-resume
DS4_MODEL_QUANT=q2-imatrix \
DS4_GGUF_DIR="$HOME/src/ds4/gguf" \
pi --offline --list-models ds4
```

Expected row:

```text
ds4  deepseek-v4-flash  100K  384K  yes  no
```

## Baseline Validation

Before a model run, the clean target should pass:

```sh
cd ~/workspaces/ds4-pi-django-resume/django-resume
just check
```

The setup validation on 2026-06-01 passed lint/format, mypy, and 129 tests.
During the completed wrap run, `uv run` also resynced the stale editable
`django-resume` version in `uv.lock` from `0.1.14` to the `pyproject.toml`
version `0.2.0`; keep that lockfile sync with the wrapped target change.

## Benchmark Procedure

Start from a clean target:

```sh
just -f ~/.config/desktop-django-lab/Justfile status
cd ~/workspaces/ds4-pi-django-resume/django-resume
git status --short
```

If a previous run must be discarded, use the lab reset intentionally:

```sh
just -f ~/.config/desktop-django-lab/Justfile reset ds4-pi-django-resume
```

Run Stage 1 deterministic scaffold:

```sh
cd ~/workspaces/ds4-pi-django-resume/django-resume
../desktop-django-starter/skills/wrap-existing-django-in-electron-staged/scripts/scaffold-target.sh "$PWD"
```

Then run Pi/DS4 for Stage 2 and Stage 3, using the staged prompt files from:

```text
../desktop-django-starter/skills/wrap-existing-django-in-electron-staged/prompt-stage-2-electron.md
../desktop-django-starter/skills/wrap-existing-django-in-electron-staged/prompt-stage-3-django.md
```

The model invocation should include:

```sh
DS4_MODEL_QUANT=q2-imatrix \
DS4_GGUF_DIR="$HOME/src/ds4/gguf" \
pi --model ds4/deepseek-v4-flash --thinking high -p "<stage prompt>"
```

Use the staged workflow's stop-early contract:

- Stage 2 may edit only `electron/**`.
- Stage 3 may edit only Django-side integration files unless a tiny Electron
  compatibility fix is unavoidable.
- If a stage's verification bundle passes, the model should stop instead of
  rereading files.
- Feed exact failure output into Stage 4 only when a concrete check fails.

## Success Criteria

The benchmark is a pass only when the resulting wrapped target satisfies all of
the following from the clean workspace:

```sh
cd ~/workspaces/ds4-pi-django-resume/django-resume
just check
just desktop-install
just desktop-stage
just desktop-smoke
```

Also run the packaged navigation check used by prior
`desktop-django-starter` experiments: detail and CV pages must expose a visible
path back to the resume list, and the packaged Electron smoke must reach the
wrapped `/resume/` app rather than landing on a login page.

Record the final result in `docs/run-log.md` and, if useful, in
`../desktop-django-starter/skills/wrap-existing-django-in-electron-staged/run-log.md`.

## Current Result

On 2026-06-01, the benchmark was run with Pi backed by local DS4 /
`ds4/deepseek-v4-flash` using the q2-imatrix GGUF.

Outcome: pass with scaffold/harness fixes. Stage 2 completed under DS4/Pi with
a verification-only zero-edit summary in 86.38s. Stage 3 ran under DS4/Pi and
executed the early verification commands, but ended after 318.01s with provider
`finish_reason=error` after malformed inline smoke-test output. Final external
verification and target validation passed after local scaffold compatibility
fixes for the current `desktop-django-starter` templates.

Final validation from `~/workspaces/ds4-pi-django-resume/django-resume`:

```text
just check            # passed, 129 tests
just desktop-install  # passed
just desktop-stage    # passed
just desktop-smoke    # passed; / redirected to /resume/ and /resume/ returned 200
```

Additional packaged checks proved `/health/`, `/` -> `/resume/` without a login
page, packaged static serving, seeded media bootstrap, and visible
`Back to all resumes` links on both the detail and CV pages.

The local starter scaffold helper was updated during the run for the current
Electron template and target compatibility: refreshed template guards, kept the
updater-aware Electron menu while adding Navigate actions, rewrote the default
release repo, ignored generated `.stage/`, emitted lint-clean URL scaffolding,
guarded packaged-only URL patterns with `getattr(..., False)`, and made seed
management commands opt-in instead of assuming the starter-only
`seed_demo_content` command exists.

## Runtime / Model Comparison (2026-06-02)

A follow-up on 2026-06-02 (same host: studio, Apple M4 Max, 128 GB) ran the
identical staged `django-resume` wrap across four local serving paths to compare
runtimes and models for daily-development suitability. Each run was driven by Pi
as a tool-using agent and independently judged by `pi / openai-codex/gpt-5.5`,
which re-ran the packaged smoke itself. The qwen runs used a shared runner that
`rm -rf`s and re-`git clone`s the target before every run; the source repo was
pristine at `ccbd5cf`, and local `git clone` checks out HEAD only, so no
generated artifacts leaked across runs.

| Serving path | Model / quant | Tool calling | Stage 2 | Stage 3 | Raw decode | Judge |
|---|---|---|---|---|---|---|
| Ollama | qwen 3.6 27b GGUF Q4_K_M (`qwen36-27b-tools`) | derived Modelfile needed (imported GGUF had a bare `{{ .Prompt }}` template) | 73.7s | 97.4s | 16.0 tok/s | PASS |
| llama.cpp `--jinja` | qwen 3.6 27b `Qwen3.6-27B-Q4_K_M.gguf` | native (reads GGUF chat template) | 41.7s | 70.7s | 22.5 tok/s | PASS |
| MLX `mlx_lm.server` | qwen 3.6 27b `mlx-community/Qwen3.6-27B-4bit` | native (send exact HF repo id as `model`) | 40.0s | 70.2s | 26.9 tok/s | PASS |
| ds4.c `ds4-server` (non-thinking) | DeepSeek V4 Flash IQ2XXS | native | 28.6s | 70.1s | 29.9 tok/s | PASS |
| ds4.c `ds4-server` (thinking=high, 2026-06-01) | DeepSeek V4 Flash IQ2XXS | native | 86.38s | 318.01s (ended `finish_reason=error`) | n/a | pass only after manual fixes |

Stage times are wall-clock and include fixed tool execution (uv venv resolve,
npm install, node tests, packaged smoke), which dominates and compresses the gap
between runtimes; raw decode (250-word essay, `max_tokens=300`, `temp=0`, warmed)
isolates model throughput.

Notes for daily-dev model selection:

- **All four reached the same correct outcome** (working packaged Electron app,
  zero model edits, judge PASS). On this scaffold-covered task the differentiator
  is speed and reliability, not capability.
- **Decode order: ds4 (29.9) > MLX (26.9) > llama.cpp (22.5) > Ollama (16.0)
  tok/s.** For the same qwen weights, MLX and llama.cpp are ~1.7x and ~1.4x faster
  than Ollama; Ollama also needed Modelfile surgery to enable tool calling.
- **Thinking mode hurt here:** the same ds4 model in `--thinking high` was ~3x
  slower on Stage 2 and derailed Stage 3 with a provider error on malformed inline
  tool output, while non-thinking ds4 was the fastest and cleanest path. For
  agentic, verification-heavy dev loops with many short tool steps, non-thinking
  (or low-effort) decoding was strictly better on this task.
- This is staged-workflow evidence: Stage 1's deterministic scaffold does the
  mechanical wrapping and the model runs verification-first Stages 2–3, so these
  numbers measure agentic tool-driving speed/reliability, not from-scratch code
  authoring.

Reproduction tooling lives in the `desktop-django-starter` checkout under
`.bench-qwen36/` (`pi-ollama-provider.ts`, `pi-localserver-provider.ts`,
`pi-ds4local-provider.ts`, `run-staged-wrap.sh`, `RUNTIME-COMPARISON.md`), and the
qwen runs are also recorded as entries 30–32 in that repo's staged
`run-log.md`. A step-by-step demo runbook (start each server, clean clone, run
the stages manually or via the runner, judge, and per-model timings) is a
rendered Sphinx page in that repo at `docs/demo-local-model-wrap.md` (build with
`just docs`; linked from the docs index under **Guides**).
