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
