# runtime-sweep

Fixed prompt-size sweep for repeated local runtime measurement. This pack is for
measuring endpoint behavior across short, medium, and long input contexts; it is
not a model-quality benchmark.

Target metrics include TTFT, prefill tokens per second, decode tokens per
second, and total tokens per second when the selected adapter and endpoint can
report or derive them.

## Cases

- `short`: compact interactive request.
- `medium`: structured multi-paragraph operations note.
- `long`: larger synthetic benchmark brief.

The prompts are inline in `benchpack.toml` so the current runner can load the
pack without prompt-file support. They are synthetic and portable: no local
paths, external repositories, network access, Apple Silicon assumptions, or CUDA
assumptions.

## Runtime Defaults

The pack sets:

- `stream = true`
- `warmup = 1`
- `repetitions = 3`
- `max_tokens = 128`
- `scoring.mode = "none"`

Warmup rows are intentionally excluded from `run.jsonl` and `summary.md`.
Measured repetitions are written as separate rows so later tooling can aggregate
them without the runner hiding individual samples.

## Adapter Notes

`openai-chat` uses streaming TTFT for this pack. It sends
`stream_options.include_usage`, so the endpoint must accept that option if token
counts are expected from streaming responses. Endpoints that reject the option
are recorded as adapter errors rather than silently retried with different
request semantics.

`ollama-generate` uses Ollama native timing fields and ignores the OpenAI
streaming response shape.

Example commands:

```sh
uv run benchpack run runtime-sweep --adapter openai-chat --model <model> --endpoint http://localhost:11434/v1 --host-label local-runtime --force
uv run benchpack run runtime-sweep --adapter ollama-generate --model <model> --host-label local-runtime --force
```
