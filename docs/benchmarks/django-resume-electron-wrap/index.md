# Django Resume Electron Wrap Benchmark

Status: current hard one-shot external-agent benchmark, driven by
`scripts/run-agent-wrap-oneshot`.

This benchmark asks an agent to wrap a clean `django-resume` checkout in an
Electron desktop shell from scratch. It uses the `desktop-django-starter`
wrapping prompt, captures the model-authored diff, then runs deterministic
verification against the generated Electron app.

This is distinct from the smaller prompt-only `desktop-django-wrap` benchpack.
The prompt-only pack asks for a plan. This benchmark requires a real generated
Electron wrapper that passes install, tests, and packaged smoke.

## Current Runner

The runner is:

```text
scripts/run-agent-wrap-oneshot
```

Default inputs:

- source project: `~/projects/django-resume-bench-main`
- starter/prompt source: `~/projects/desktop-django-starter`
- output root: `results/agent-wrap-oneshot/`
- target clone: `~/projects/django-resume-oneshot-<label>`

The runner clones the source project into a disposable target, runs one
unattended agent session, captures the diff before verification mutates the
clone, and records result artifacts under `results/agent-wrap-oneshot/<label>/`.

## Supported Agent Lanes

The helper currently supports:

- `codex-yolo`: Codex CLI with `--reasoning-effort`.
- `claude-yolo`: Claude Code with `--effort`.
- `pi`: Pi with a selected provider/model and `--thinking`.

Example dry run:

```sh
scripts/run-agent-wrap-oneshot \
  --dry-run \
  --label gpt55-codex-yolo-django-resume-030-low \
  --runner codex-yolo \
  --model gpt-5.5 \
  --reasoning-effort low
```

Example run:

```sh
scripts/run-agent-wrap-oneshot \
  --label gpt55-codex-yolo-django-resume-030-low \
  --runner codex-yolo \
  --model gpt-5.5 \
  --reasoning-effort low
```

## Verification

The verifier checks:

- `electron/package.json` exists;
- `npm --prefix electron install` succeeds;
- generated Electron Node tests pass when present;
- `npm --prefix electron run smoke:packaged` succeeds when declared;
- packaged smoke reaches the Django app over HTTP, including `/health/` and
  either `/` or the `/` to `/resume/` redirect path.

A benchmark pass requires both:

- packaged app served successfully;
- generated Node tests passed.

## Curated Results

Curated normalized rows live in:

```text
data/agent-wrap-oneshot-results.json
```

The registry importer can load them with:

```sh
uv run benchpack registry agent-wrap import \
  --db registry/llm-benchpacks.sqlite \
  data/agent-wrap-oneshot-results.json
```

`just registry-site` imports these rows into the local registry-backed site.
The historical narrative remains in [Run Log](../../run-log.md).

## Historical Notes

Older staged DS4/Pi work is kept here as historical context:

- [Legacy DS4/Pi staged benchmark](legacy-ds4-pi-wrap-benchmark.md)
- [Legacy DS4 goal prompt](legacy-ds4-goal-prompt.md)
