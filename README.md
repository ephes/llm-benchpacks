# llm-benchpacks

Portable benchmark packs for local LLM runtimes and coding-agent workloads.

This repository is for answering practical questions such as:

- Is direct `mlx-lm` faster than Ollama's MLX path on the same Mac?
- How does `llama-server` compare to `mlx_lm.server` on the same prompt shape?
- Which model/runtime combination is usable for a real coding-agent workflow?
- Do small hosted GPUs, such as Hetzner's RTX 4000 SFF Ada machines, behave differently enough that we need separate recommendations?

The project should measure both raw inference behavior and workload behavior. Raw
tokens/sec is useful, but coding agents also depend on time to first token,
prefill speed, prompt-cache reuse, long-context stability, tool-call formatting,
and whether the final repository changes pass verification.

## Documentation

- [Specification](docs/specification.md): product scope, benchmark model, metrics, and MVP.
- [Architecture](docs/architecture.md): proposed runner, adapters, packs, and result schema.
- [Implementation Plan](docs/implementation-plan.md): phased path from minimal runner to remote GPU comparisons.
- [Benchpack Format](docs/benchpack-format.md): initial manifest sketch.
- [Hardware Targets](docs/hardware-targets.md): initial machines and runtime assumptions.
- [Apple Silicon M4/M5 Runbook](docs/apple-silicon-m4-m5-runbook.md): local
  M5 plus SSH-to-M4 run workflow, result pullback, and compare guidance.
- [Qwen3.6 M4/M5 Benchmark Summary](docs/qwen36-m4-m5-benchmark-summary.md):
  compact 2026-05-05 MLX-vs-llama.cpp-vs-Ollama result summary.
- [Decisions](docs/decisions.md): durable design decisions.
- [Spec Log](docs/spec-log.md): dated changes to the spec and open design questions.
- [Run Log](docs/run-log.md): benchmark run history and result pointers.

## Usage

The Phase 1 runner is in `src/benchpack/`, managed with [`uv`](https://docs.astral.sh/uv/):

```sh
uv sync
uv run benchpack run smoke-chat --adapter ollama-generate --model qwen3-coder:latest
uv run benchpack run smoke-chat --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1
uv run benchpack run runtime-sweep --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-runtime --force
uv run benchpack run runtime-sweep --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-runtime --run-metadata metadata/runtime.json --force
uv run benchpack run runtime-sweep --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --openai-stream-usage omit --host-label local-runtime --force
uv run benchpack run desktop-django-wrap --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-wrap --force
uv run benchpack run patch-from-failure --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-patch --force
uv run benchpack run python-regression-fix --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-python-regression --force
uv run benchpack compare results/2026-04-28-mlx-lm-runtime results/2026-04-29-llama-server-runtime
uv run benchpack report results/2026-04-28-mlx-lm-runtime results/2026-04-29-llama-server-runtime
```

Repo-task packs may explicitly select `harness = { id = "external-agent" }`.
That public harness uses runner-owned subprocess configuration rather than a
manifest command: set `BENCHPACK_EXTERNAL_AGENT_ARGV` to a JSON array of argv
strings before running the pack. The runner appends workspace/case/output
arguments plus `--context <path>` to a runner-owned JSON context file under
`task/<case-id>/rep-NNN.context.json`, runs without a shell, and writes through
the existing task logs. The context file includes pack/case metadata, the loaded
prompt, fixture metadata, prepared workspace path, task log paths, run metadata
path when supplied, an optional harness-owned model-call JSONL path at
`task/<case-id>/rep-NNN.model-calls.jsonl`, and the selected adapter/model/
endpoint/defaults. It is harness input only and is not duplicated into
`run.jsonl`; the runner exposes the model-call path but does not require or
parse that file. Harness authors who write the optional model-call JSONL file
should prefer one object per call with a minimal line such as
`{"schema_version":1,"sequence":1,"model":"test-model","ok":true}` and should
avoid putting full prompts, full responses, request bodies, headers,
environment variables, API keys, bearer tokens, or credentials in the default
telemetry shape.
See
[`examples/external-agent/reference-agent.py`](examples/external-agent/reference-agent.py)
for a deterministic local reference harness that validates the public context
handoff, mutates only the prepared workspace, and writes that optional JSONL
line without making live model calls.

For long metadata-backed matrix runs, `scripts/benchpack-tmux-matrix` wraps the
existing `benchpack run` command in one tmux session with deterministic pack
windows. Pack commands run sequentially inside tmux so they do not contend for
the same local runtime; if one pack fails, later windows wake up and report
that they were skipped. Inspect the dry run before launching real benchmarks:

```sh
scripts/benchpack-tmux-matrix \
  --dry-run \
  --session-name 'bench-m5-llama-<stamp>' \
  --adapter openai-chat \
  --model '<model>' \
  --endpoint '<endpoint>' \
  --host-label-prefix 'm5-max-llama-<stamp>' \
  --run-metadata metadata/m5-llama-server.json
```

The helper defaults to `smoke-chat`, `runtime-sweep`, `desktop-django-wrap`,
and `patch-from-failure`, passes `--run-metadata` to every pack run, and omits
`--force` unless explicitly requested. Launch mode checks that the metadata
file exists before creating tmux windows. It does not change benchmark
semantics; after runs finish, use `benchpack report` on the result directories.

Each `benchpack run` invocation writes `results/<date>-<host-label>/` containing
`run.jsonl`, `summary.md`, `hardware.json`, and `raw/`. When
`--run-metadata <json-file>` is supplied, the runner also validates that JSON
object and writes it beside the result as `run-metadata.json` for runtime,
model, and operating-condition notes such as server command, runtime version,
quantization, checksum, context/cache options, power, thermal, and background
load. See
[`docs/specification.md`](docs/specification.md) for the full CLI shape and
collision rules, and `uv run pytest` for the test suite.

For `openai-chat` streaming runs, `--openai-stream-usage include` is the
default and sends `stream_options.include_usage` so supporting endpoints can
return token usage chunks. Use `--openai-stream-usage omit` for
OpenAI-compatible local servers that reject that option; streamed output and
TTFT remain available, while usage-derived token counts and token-rate fields
stay null unless the server still reports usage.

`benchpack compare` is read-only and compares existing result directories that
contain `run.jsonl`. It prints per-case medians for wall time, TTFT, decode TPS,
total TPS, output tokens, prompt tokens, backend-reported cached prompt tokens,
and prefill TPS gated on prefill parity. The `prefill_tps med` column renders a
numeric median only when that case's `prefill parity` status is `comparable`;
otherwise it renders `—`. Compare also prints cache metadata coverage as
numeric cached-token rows over total rows for each case/run group and a
case-level `prefill parity` status repeated on each run row. The status is one
of `missing-case`, `prompt-missing`, `prompt-diff`, `cache-missing`,
`cache-diff`, or `comparable`, in that priority order. Compare warns when
metadata is incomplete, complete prompt-token medians differ, or complete
cached-token medians differ. Prompt-token coverage is used to decide whether a
prompt mismatch warning is meaningful, but the table does not add a second
coverage column. Old rows may lack `tokens.prompt`, `tokens.cached_prompt`, or
`timing.prefill_tps`, and missing values do not establish parity or prefill
speed.

`benchpack report` is also read-only and emits a pasteable Markdown report from
existing result directories. It reads `run.jsonl`, optional `hardware.json`, and
optional `run-metadata.json`, then summarizes inputs, pack id/version, host
identity when available, user-supplied runtime/model/operating metadata,
adapter/model/endpoint, row and `ok` counts, scoring pass/fail/unscored counts,
and the same compare medians, cache rows, warnings, and `prefill parity`
statuses used by `benchpack compare`. It is intended for assembling run notes
and M4/M5 comparison reports without copying medians from several compare
outputs by hand. For repeated report assembly, `benchpack report --set
<manifest.toml>` accepts a tiny TOML report-set manifest and expands it to the
same existing result-directory inputs:

```toml
version = 1
result_dirs = [
  "results/<date>-m5-max-runtime",
  "results/<date>-m4-max-runtime",
]
```

Relative `result_dirs` entries resolve relative to the manifest file. The
manifest is source-only and read-only: it does not schedule runs, start
servers, copy artifacts, or write report files.

Bundled packs:

- `smoke-chat`: non-streaming single-case endpoint smoke test.
- `runtime-sweep`: streaming short/medium/long runtime measurement pack with one
  warmup and three measured repetitions per case.
- `desktop-django-wrap`: streaming prompt-only first Phase 3 coding-agent-shaped
  workload with pack-local prompt files that asks for Django-in-Electron
  wrapping plans, uses regex scoring to require `DDS_WRAP_PLAN` plus fixed
  short-answer labels in order, and declares two pack-local synthetic fixtures
  for wrap planning: one context file and one compact static Django repo
  snapshot directory. Both cases reference both fixtures by id. The file
  fixture is appended to the loaded prompt with stable delimiters, while the
  directory fixture remains metadata-only and is not copied, executed,
  injected, or used to mutate a repository. This is not yet a repo-mutating
  wrap benchmark.
- `patch-from-failure`: non-streaming single-case `repo-task` pack with one
  tiny Python repo fixture. The case asks the model to return only a fenced
  `diff` block, applies that unified diff inside a run-owned workspace, captures
  `patch/fix-greeting/rep-001.diff`, and uses a stdlib `verify-script` to check
  that `greet("Ada")` returns exactly `Hello, Ada!`.
- `python-regression-fix`: non-streaming single-case `repo-task` pack with a
  small stdlib Python task-summary repo fixture. The case asks for a fenced
  unified diff to fix owner/status summary behavior, overdue-title filtering
  and ordering, and input immutability; verification remains deterministic and
  stdlib-only. This is a narrow fenced-patch repo-task signal, not production
  external agent-harness coverage.

## Initial Shape

The first implementation stays small:

1. A CLI that can run one benchmark pack against one endpoint.
2. An OpenAI-compatible adapter for `mlx_lm.server`, `llama-server`, vLLM, LM Studio, and similar servers.
3. An Ollama-native adapter for `/api/generate` so we retain Ollama's native timing fields.
4. Smoke and runtime-sweep benchmarks, plus Phase 3 coding-agent-shaped packs:
   the prompt-only `desktop-django-wrap` starter pack and measured
   repo-mutating fenced unified-diff packs such as `patch-from-failure` and
   `python-regression-fix`. `desktop-django-wrap` still treats directory
   fixtures as metadata-only; repo-task packs copy their repo fixtures into
   run-owned workspaces, apply the model diff there, and verify the result.
5. JSONL result artifacts plus a small Markdown summary.

The repository is private while the spec and first runner are still unstable.
