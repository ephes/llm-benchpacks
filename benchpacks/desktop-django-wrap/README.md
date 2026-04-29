# desktop-django-wrap

Prompt-only first Phase 3 workload for coding-agent-shaped Django/Electron
wrapping behavior. It approximates the planning surface of wrapping an existing
server-rendered Django app in an Electron desktop shell, but it does not execute
an agent, mutate a target repository, execute fixtures, extract patches, or run
verification scripts.

Pack version: `0.1.1`.

## Cases

- `wrap-plan-small`: compact task brief for a short wrapping outline.
- `wrap-plan-context`: slightly richer synthetic project context.

Both prompts live in pack-local files under `prompts/`, referenced from
`benchpack.toml` with `prompt_file`. They are synthetic and portable: no local
paths, private repository checkout, network access, Apple Silicon assumptions,
CUDA assumptions, or endpoint-specific behavior.

## Fixtures

The pack declares one static fixture:

- `synthetic-django-app`: a portable context file at
  `fixtures/synthetic-django-app.md` describing a compact synthetic Django app
  shape for future wrap work.

The current prompts do not consume this fixture yet. It is loaded only as
manifest metadata and validated as a pack-local path; the runner does not copy
it, execute it, create a disposable repository from it, or inject its contents
into adapter requests.

## Runtime Defaults

The pack sets:

- `stream = true`
- `warmup = 0`
- `repetitions = 1`
- `temperature = 0`
- `max_tokens = 384`
- `scoring.mode = "contains"`
- `scoring.expected = "DDS_WRAP_PLAN"`

Streaming is enabled deliberately so OpenAI-compatible adapters can measure
time to first token on a coding-agent-shaped prompt. The pack has no warmup and
one measured repetition because this first Phase 3 slice is a portable workload
surface, not a statistical runtime sweep.

The scoring check is only a deterministic sanity check that the model followed
the requested output shape. Passing `DDS_WRAP_PLAN` containment does not mean
the model can complete a real repository wrap.

## Example Commands

```sh
uv run benchpack run desktop-django-wrap --adapter openai-chat --model <model> --endpoint http://localhost:11434/v1 --host-label local-wrap --force
uv run benchpack run desktop-django-wrap --adapter ollama-generate --model <model> --host-label local-wrap --force
```
