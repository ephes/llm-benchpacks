# desktop-django-wrap

Prompt-only first Phase 3 workload for coding-agent-shaped Django/Electron
wrapping behavior. It approximates the planning surface of wrapping an existing
server-rendered Django app in an Electron desktop shell, but it does not execute
an agent, mutate a target repository, execute fixtures, extract patches, or run
verification scripts.

Pack version: `0.1.5`.

## Cases

- `wrap-plan-small`: compact task brief for a short wrapping outline.
- `wrap-plan-context`: slightly richer synthetic project context.

Both prompts live in pack-local files under `prompts/`, referenced from
`benchpack.toml` with `prompt_file`. They are synthetic and portable: no local
paths, private repository checkout, network access, Apple Silicon assumptions,
CUDA assumptions, or endpoint-specific behavior.

Both prompts require the same short output skeleton:

```text
DDS_WRAP_PLAN
Inspect: ...
Electron shell: ...
Django runtime: ...
Packaging: ...
Verification: ...
```

Both cases reference the pack's fixtures by id through `fixture_refs`, in this
order: `synthetic-django-app`, then `synthetic-django-repo`. The loader appends
the file fixture to each loaded prompt with stable `BEGIN FIXTURE` /
`END FIXTURE` delimiters before adapter requests are created. The directory
fixture ref validates as metadata only; its contents are not injected into
`Case.prompt`.

## Fixtures

The pack declares two static fixtures:

- `synthetic-django-app`: a portable context file at
  `fixtures/synthetic-django-app.md` describing a compact synthetic Django app
  shape for wrap planning.
- `synthetic-django-repo`: a compact static source snapshot at
  `fixtures/synthetic-django-repo/` with a tiny Django project, one inventory
  app, a template, static CSS, and a health endpoint.

Both fixtures are validated as pack-local paths and linked from cases by id.
Only the file fixture is assembled into the final case prompt. The directory
snapshot remains metadata-only: the runner does not read it into prompts, copy
it, execute it, install dependencies, create a disposable repository from it,
extract patches, run verifier scripts, replay an agent session, or mutate a
target repository.

## Runtime Defaults

The pack sets:

- `stream = true`
- `warmup = 0`
- `repetitions = 1`
- `temperature = 0`
- `max_tokens = 384`
- `scoring.mode = "regex"`
- `scoring.pattern` requires `DDS_WRAP_PLAN` first, followed by the fixed
  labels `Inspect:`, `Electron shell:`, `Django runtime:`, `Packaging:`, and
  `Verification:` in order.

Streaming is enabled deliberately so OpenAI-compatible adapters can measure
time to first token on a coding-agent-shaped prompt. The pack has no warmup and
one measured repetition because this first Phase 3 slice is a portable workload
surface, not a statistical runtime sweep.

The scoring check is still a deterministic prompt-following check, not a
repository verifier. Passing the regex means the model followed the short
answer skeleton; it does not mean the model can complete a real repository
wrap.

## Example Commands

```sh
uv run benchpack run desktop-django-wrap --adapter openai-chat --model <model> --endpoint http://localhost:11434/v1 --host-label local-wrap --force
uv run benchpack run desktop-django-wrap --adapter ollama-generate --model <model> --host-label local-wrap --force
```
