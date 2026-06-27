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
- [Model Target Catalog](docs/model-targets.md): preferred/current model
  targets, artifact-parity notes, and revisit cadence.
- [Apple Silicon M4/M5 Runbook](docs/apple-silicon-m4-m5-runbook.md): local
  M5 plus SSH-to-M4 run workflow, result pullback, and compare guidance.
- [Gemma 4 Tri-host Runbook](docs/gemma4-tri-host-runbook.md): M4, M5, and
  Hetzner planning workflow, strict-parity mode, authenticated dry-run
  matrices, and blocker checklist.
- [Qwen3.6 M4/M5 Benchmark Summary](docs/qwen36-m4-m5-benchmark-summary.md):
  compact 2026-05-05 MLX-vs-llama.cpp-vs-Ollama result summary.
- [Benchmark Research Backlog](docs/benchmark-research.md): research leads and
  next-work ordering for stronger coding-agent benchmarks.
- [Hosted Registry PRD](docs/registry-hosted-django-spec.md): dynamic hosted
  service direction for curated uploads, review, local web development, browse
  views, APIs, and project layout.
- [Registry Hosted Site Spec](docs/registry-hosted-site-spec.md): v1 static
  curated archive fallback scope for `benchmarks.staging.django-cast.com`.
- [Decisions](docs/decisions.md): durable design decisions.
- [Spec Log](docs/spec-log.md): dated changes to the spec and open design questions.
- [Run Log](docs/run-log.md): benchmark run history and result pointers.
- [DS4 Pi Django-Resume Wrap Benchmark](docs/ds4-pi-django-resume-wrap-benchmark.md):
  manual external-agent staged Electron wrap of `django-resume`, plus the
  2026-06-02 Ollama / llama.cpp / MLX / ds4 runtime comparison. The step-by-step
  demo runbook is a rendered Sphinx page in the `desktop-django-starter` repo at
  `docs/demo-local-model-wrap.md` (build with `just docs`).

## Usage

The Phase 1 runner is in `src/benchpack/`, managed with [`uv`](https://docs.astral.sh/uv/):

```sh
uv sync
uv run benchpack run smoke-chat --adapter ollama-generate --model qwen3-coder:latest
uv run benchpack run smoke-chat --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1
uv run benchpack run runtime-sweep --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-runtime --force
uv run benchpack run runtime-sweep --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-runtime --run-metadata metadata/runtime.json --force
uv run benchpack run runtime-sweep --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --openai-stream-usage omit --host-label local-runtime --force
# Set BENCHPACK_REMOTE_OPENAI_TOKEN locally from your secret store first; do not commit secrets.
uv run benchpack run smoke-chat --adapter openai-chat --model '<model>' --endpoint '<remote-openai-compatible-v1-url>' --openai-api-key-env BENCHPACK_REMOTE_OPENAI_TOKEN --host-label remote-smoke
uv run benchpack run desktop-django-wrap --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-wrap --force
uv run benchpack run patch-from-failure --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-patch --force
uv run benchpack run endpoint-python-correctness --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-endpoint-correctness --force
uv run benchpack run python-regression-fix --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-python-regression --force
uv run benchpack run django-dashboard-regression-fix --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-dashboard-regression --force
uv run benchpack run mini-project-completion --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-mini-project --force
uv run benchpack run tool-json --adapter openai-chat --model qwen3-coder:latest --endpoint http://localhost:11434/v1 --host-label local-json-format --force
uv run benchpack compare results/2026-04-28-mlx-lm-runtime results/2026-04-29-llama-server-runtime
uv run benchpack report results/2026-04-28-mlx-lm-runtime results/2026-04-29-llama-server-runtime
uv run benchpack registry import --db registry/llm-benchpacks.sqlite results/2026-04-28-mlx-lm-runtime results/2026-04-29-llama-server-runtime
uv run benchpack registry report --db registry/llm-benchpacks.sqlite --label 2026-04-28-mlx-lm-runtime --label 2026-04-29-llama-server-runtime
uv run benchpack registry duplicates --db registry/llm-benchpacks.sqlite
uv run benchpack registry query --db registry/llm-benchpacks.sqlite --pack runtime-sweep --runtime llama-server --quantization Q4_K_M
uv run benchpack registry site --db registry/llm-benchpacks.sqlite --out registry/site
uv run benchpack registry bundle create --out bundles/example --provenance self-reported results/2026-04-28-mlx-lm-runtime
uv run benchpack registry bundle validate bundles/example
uv run benchpack registry bundle import --db registry/llm-benchpacks.sqlite bundles/example
```

Repo-task packs may explicitly select `harness = { id = "external-agent" }`.
That public harness uses runner-owned subprocess configuration rather than a
manifest command: set `BENCHPACK_EXTERNAL_AGENT_ARGV` to a JSON array of argv
strings before running the pack. The runner appends workspace/case/output
arguments plus `--context <path>` to a runner-owned JSON context file under
`task/<case-id>/rep-NNN.context.json`, runs without a shell, and writes through
the existing task logs. When `harness.timeout_s` is set, timeout cleanup stops
the external subprocess process group with a bounded terminate-then-kill policy
before the runner writes timeout task logs. The context file includes pack/case
metadata, the loaded prompt, fixture metadata, prepared workspace path, task
log paths, run metadata path when supplied, an optional harness-owned
model-call JSONL path at
`task/<case-id>/rep-NNN.model-calls.jsonl`, and the selected adapter/model/
endpoint/defaults. It is harness input only and is not duplicated into
`run.jsonl`; the runner exposes the model-call path but does not require or
pre-create that file. When the optional model-call JSONL file exists,
`summary.md` and `benchpack report` summarize only allowlisted safe telemetry
fields and keep the file path and full payloads out of `run.jsonl`. Harness
authors who write the optional model-call JSONL file should prefer one object
per call with a minimal line such as
`{"schema_version":1,"sequence":1,"model":"test-model","ok":true}` and should
avoid putting full prompts, full responses, request bodies, headers,
environment variables, API keys, bearer tokens, or credentials in the default
telemetry shape. Optional safe labels may include `response_format`,
`token_budget_field`, and `finish_reason` so direct-edit runs can show whether
JSON mode, structured outputs, or truncation-sensitive completion behavior was
in play without storing payloads.
See
[`examples/external-agent/reference-agent.py`](examples/external-agent/reference-agent.py)
for a deterministic local reference harness that validates the public context
handoff, mutates only the prepared workspace, and writes that optional JSONL
line without making live model calls. The sibling
[`examples/external-agent/model-call-agent.py`](examples/external-agent/model-call-agent.py)
example adds one deterministic local HTTP request to a fake/recorded endpoint
and records only safe model-call telemetry while keeping the runner boundary
unchanged.

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
`--force` unless explicitly requested. `--openai-api-key-env <ENV_NAME>` is an
optional pass-through for authenticated `openai-chat` endpoints; the helper
renders the environment variable name in generated commands but does not read
the token value. Launch mode checks that the metadata file exists before
creating tmux windows. It does not change benchmark semantics; after runs
finish, use `benchpack report` on the result directories.

For the validated Qwen3.6 27B strict-GGUF lane, the helper has an explicit
opt-in preset that supplies the known-good model alias and loopback endpoint
when they are omitted:

```sh
scripts/benchpack-tmux-matrix \
  --dry-run \
  --preset qwen36-27b-strict-gguf \
  --session-name 'bench-qwen36-27b-strict-<stamp>' \
  --adapter openai-chat \
  --host-label-prefix 'm5-max-qwen36-27b-strict-<stamp>' \
  --run-metadata metadata/m5-qwen36-27b-strict.json
```

The preset defaults to `--model qwen36-27b-q4km` and
`--endpoint http://127.0.0.1:18082/v1`, and still expands to only the default
four-pack matrix unless positional packs or `--pack-set` are supplied.
Combining the preset with `--pack-set` is supported when a run intentionally
uses the strict-lane model and endpoint with a non-default pack set.
Operators must start the matching `llama-server --reasoning off` process and
prepare metadata separately. This preset is scoped to the exact
`Qwen3.6-27B-Q4_K_M.gguf` strict lane and does not promote
`endpoint-python-correctness`, Ollama, MLX, public API, or external-agent
workflows into default helper behavior. Explicit `--model` or `--endpoint`
values override the preset defaults; the dry run shows the resolved command.

For the hard from-scratch Django/Electron wrapping benchmark that uses the
`desktop-django-starter` skill prompt and verifies a real generated Electron
app, use the neutral one-shot helper in this repository instead of the legacy
`.bench-qwen36` scratch directory in `desktop-django-starter`:

```sh
scripts/run-agent-wrap-oneshot \
  --dry-run \
  --label gpt55-codex-yolo-django-resume-030-none \
  --runner codex-yolo \
  --model gpt-5.5 \
  --reasoning-effort none

scripts/run-agent-wrap-oneshot \
  --label gpt55-codex-yolo-django-resume-030-none \
  --runner codex-yolo \
  --model gpt-5.5 \
  --reasoning-effort none

scripts/run-agent-wrap-oneshot \
  --label opus48-claude-yolo-django-resume-030-low \
  --runner claude-yolo \
  --model opus \
  --claude-effort low
```

The helper clones the configured source repo into a disposable target, runs one
unattended agent session against the original wrap prompt, captures the
model-authored diff before verification mutates the clone, then runs
`npm --prefix electron install`, Electron Node tests, and packaged smoke. New
artifacts default to `results/agent-wrap-oneshot/<label>/`, which remains
ignored like other generated benchmark output. Historical
`desktop-django-starter/.bench-qwen36/` artifacts are retained in place for
continuity only; avoid reusing those legacy labels for new runs unless the
comparison plan explicitly needs name continuity. Pass `--force` only when
intentionally replacing an existing generated target/result pair for the same
label. Supported hosted-agent runners are `codex-yolo`, `claude-yolo`, and
`pi`; direct Codex uses `--reasoning-effort`, where `none` is the no-reasoning
lane and `low` is separate. Claude Code uses `--claude-effort` because the CLI
exposes effort levels, not a literal thinking-off switch.

The curated normalized one-shot rows live in
`data/agent-wrap-oneshot-results.json` and import into the local SQLite
registry with:

```sh
uv run benchpack registry agent-wrap import \
  --db registry/llm-benchpacks.sqlite \
  data/agent-wrap-oneshot-results.json

uv run benchpack registry agent-wrap query \
  --db registry/llm-benchpacks.sqlite \
  --harness codex-yolo \
  --model gpt-5.5 \
  --status pass
```

`just registry-site` imports that curated dataset into `agent_wrap_runs` before
rendering the SQLite-backed static site, so the browser table and
`snapshot.json` can filter/query normalized result, harness, provider, model,
and thinking-mode fields from the database. `docs/run-log.md` remains the
narrative source for benchmark context and caveats.

For optional exploratory repo-task evidence, select the coding-task pack set
explicitly instead of changing the default four-pack matrix:

```sh
scripts/benchpack-tmux-matrix \
  --dry-run \
  --pack-set coding-tasks \
  --session-name 'bench-coding-tasks-<stamp>' \
  --adapter openai-chat \
  --model '<model>' \
  --endpoint '<endpoint>' \
  --host-label-prefix 'm5-max-coding-tasks-<stamp>' \
  --run-metadata metadata/example.json
```

`--pack-set coding-tasks` expands to `patch-from-failure`,
`python-regression-fix`, and `django-dashboard-regression-fix`, in that order.
This is a convenience matrix for inspecting current fenced-patch repo-task
evidence; it is optional exploratory signal, not part of the default matrix and
not broad production external-agent proof. Positional custom packs still work,
but they cannot be combined with `--pack-set`.

For opt-in direct-edit external-agent evidence, use the separate
`coding-tasks-external-agent` pack set with `BENCHPACK_EXTERNAL_AGENT_ARGV`
configured in the operator environment:

```sh
BENCHPACK_EXTERNAL_AGENT_ARGV='["/path/to/agent"]' \
scripts/benchpack-tmux-matrix \
  --dry-run \
  --pack-set coding-tasks-external-agent \
  --session-name 'bench-coding-agent-<stamp>' \
  --adapter openai-chat \
  --model '<model>' \
  --endpoint '<endpoint>' \
  --host-label-prefix 'm5-max-coding-agent-<stamp>' \
  --run-metadata metadata/example.json
```

That set expands to `patch-from-failure-external-agent`,
`python-regression-fix-external-agent`, and
`django-dashboard-regression-fix-external-agent`. Those packs keep the same
fixtures and deterministic verifiers as the fenced-patch packs, but their
prompts tell the external agent to edit the prepared workspace directly. The
runner still performs the normal pre-task adapter call, captures the workspace
patch after the external-agent task phase, and runs deterministic verifiers.
This set is explicit opt-in evidence and is not part of the default matrix.
See
[`examples/external-agent/openai-direct-edit-agent.py`](examples/external-agent/openai-direct-edit-agent.py)
for an opt-in live wrapper that calls an authenticated OpenAI-compatible chat
endpoint from the operator machine and applies JSON full-file replacement edits
only to prompt-allowed paths. It defaults to a plain non-streaming chat
completion request; pass `--response-format json_object` only when the endpoint
supports OpenAI-style JSON-object response formatting for the harness-owned
task call, or `--response-format json_schema` when the endpoint supports
OpenAI-style structured outputs with `response_format.type = "json_schema"`.
The JSON-schema mode constrains the task response to the full-file replacement
shape and the prompt-derived allowed path list. The wrapper validates the full
`files` array before writing any replacement content, rejects duplicate or
disallowed paths, and restores original file contents if a write fails during
application. The wrapper defaults to `--max-tokens 4096`; increase that value
for larger direct-edit tasks, and add `--token-budget-field
max_completion_tokens` only for endpoints or models that require that newer
OpenAI-style chat-completions field instead of the more portable `max_tokens`.
An empty `files` array remains a valid no-op wrapper response, with
deterministic verification deciding whether the benchmark passes. For Hetzner
service runs, load
`BENCHPACK_HETZNER_OPENAI_TOKEN`
locally and use the public
`https://llm.django-cast.com/v1` path; do not require Codex, Claude, Ollama, or
this repository to be installed on the server.

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

For authenticated OpenAI-compatible endpoints, pass
`--openai-api-key-env <ENV_NAME>`. The adapter reads the bearer token from that
environment variable only when the option is supplied, sends
`Authorization: Bearer <token>` on `openai-chat` requests, and stores only the
environment variable name in adapter defaults or external-agent context. It
does not implicitly read `OPENAI_API_KEY`. Do not put API keys, bearer tokens,
or endpoint credentials in tracked docs, run metadata, task logs, model-call
logs, or committed result artifacts.

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
adapter/model/endpoint, optional external-agent model-call telemetry summaries,
repo-task outcome summaries with aggregate and per-run outcome counts when
`repo_task` rows exist, row and `ok` counts, scoring pass/fail/unscored counts,
and the same
compare medians, cache rows, warnings, and `prefill parity` statuses used by
`benchpack compare`. Repo-task outcome summaries are report-only and
distinguish empty workspace diffs, source-file mutations, generated/non-source
only mutations, and unknown patch-artifact state without changing `run.jsonl`.
It is intended for
assembling run notes and M4/M5 comparison reports without copying medians from
several compare outputs by hand. For repeated report assembly,
`benchpack report --set <manifest.toml>` accepts a tiny TOML report-set
manifest and expands it to the
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

`benchpack registry import --db <sqlite> <result-dir>...` creates or updates a
local SQLite index over existing result directories. It validates `run.jsonl`,
optionally reads `hardware.json` and `run-metadata.json`, stores compact run and
row metadata plus normalized timing/token/scoring fields, indexes explicit
comparability anchors from run metadata such as comparison mode, model artifact
revision/checksum, runtime options, and operating-condition notes, and stores
per-case prompt/cache coverage medians for later comparison views. It leaves
benchmark outputs untouched. The result directory remains canonical evidence;
the registry is a local search/index aid, not a submission bundle or
replacement artifact format.

`benchpack registry report --db <sqlite>` renders the same Markdown report
shape from indexed registry rows, with optional `--run-id <id>` or
`--label <label>` filters. It uses the rows plus stored hardware and
run-metadata JSON in SQLite, so median, warning, cache-row, and
`prefill parity` output can be reproduced from a registry snapshot even when
the original result directories are not present. Artifact-only sections stay
bounded: external-agent model-call summaries are omitted, and repo-task patch
byte counts render as unknown unless a normal directory-backed report is used.

`benchpack registry query --db <sqlite>` is a read-only JSON query over the
same normalized registry rows. It supports `--run-id` or `--label` selection
plus indexed filters such as `--pack`, `--case`, `--adapter`, `--model`,
`--host-label`, `--runtime`, `--quantization`, `--ok true|false`,
`--scoring-passed true|false`, and `--limit`. The output is a JSON array of
compact run/result-row objects from SQLite only; it does not read source result
directories, raw payloads, workspaces, task logs, verifier artifacts, patch
files, or model-call logs.

`benchpack registry site --db <sqlite> --out <site-dir>` writes a local static
snapshot with dense run tables, a comparison matrix of per-run/per-case median
latency, throughput, token, and scoring fields from indexed rows, case-metric
coverage tables, browser-side filters for pack, case, host, runtime, model,
and quantization, the generated `report.md`, and a machine-readable
`snapshot.json` containing the same compact run, comparison, and case-metric
data. The export uses SQLite only; source result directories and large
artifacts are not required.

For local browsing, `just site` is the shortest path. It renders the default
`registry/site` export from `registry/llm-benchpacks.sqlite`; when that database
is missing, it first imports every local `results/*` directory that contains a
`run.jsonl`.

The preferred hosted direction is now a Django registry service, documented in
[`docs/registry-hosted-django-spec.md`](docs/registry-hosted-django-spec.md).
That service should support curated bundle ingestion, validation, operator
review, registered-user submission, transactional email, public browse pages,
and read-only APIs while still keeping raw artifacts out of public storage. The
hosted app should live cleanly in this repo beside the existing runner package,
expose a local Django dev server, and start with SQLite-backed app state.
Deployment mechanics should use the same responsibility split as other
services: product code here, reusable deployment logic in `ops-library`, and
private staging configuration plus email-provider secrets in `ops-control`.
`homepage` and `nyxmon` are references for those mechanics only. The static
export remains a local/offline review path and possible temporary read-only
fallback.

For the temporary static staging archive, the local Justfile mirrors the
homepage-style delegation pattern while keeping the generated artifact boundary
explicit:

```sh
just deploy-staging
```

That recipe first checks `BENCHMARKS_SITE_OUT` (defaulting to `registry/site`)
for a complete generated static site: `index.html`, `report.md`, and
`snapshot.json`. If those files exist, it delegates that directory to
`../ops-control` with `BENCHMARKS_STATIC_SITE_SOURCE` set explicitly and does
not require a registry database. The fallback requires the companion
`ops-control` checkout to provide a `deploy-benchmarks-static` recipe; if that
recipe is absent, the shortcut fails before generating or deploying with an
explicit ops-control preflight message. If the generated site is absent or
incomplete and `BENCHMARKS_REGISTRY_DB` exists (defaulting to
`registry/llm-benchpacks.sqlite`), it runs `benchpack registry site` and then
delegates the generated output. If neither a complete generated site nor the
registry DB exists, it exits with the curation/import commands needed to create
one. Use `just site` or `just registry-site` for local generation with automatic
bootstrap from local `results/*/run.jsonl` directories, or
`just deploy-staging-existing` when you want the existing-site-only path to fail
instead of regenerating from SQLite.

`benchpack registry bundle create --out <bundle-dir> <result-dir>...` creates a
compact public-sharing bundle from existing result directories. The bundle
copies `run.jsonl`, optional `hardware.json`, optional `run-metadata.json`,
patch files needed for repo-task outcome summaries, and safe model-call JSONL
logs only when every line uses the documented allowlisted telemetry shape. It
omits raw payloads, workspaces, task logs, verifier artifacts, and unsafe
model-call logs by default while recording hashes for omitted files when they
are available. Use `--provenance self-reported`, `operator-curated`, or
`independently-reproduced` to label the bundle, and run
`benchpack registry bundle validate <bundle-dir>` before sharing. To index a
received compact bundle offline, run
`benchpack registry bundle import --db <sqlite> <bundle-dir>...`; it validates
each bundle before writing SQLite rows and imports only the bundled compact run
directories.

Bundled packs:

- `smoke-chat`: non-streaming single-case endpoint smoke test.
- `runtime-sweep`: streaming short/medium/long runtime measurement pack with one
  warmup and three measured repetitions per case.
- `tool-json`: non-streaming two-case chat pack for strict JSON and
  tool-call-shaped formatting checks. It requires raw JSON with no Markdown or
  prose and scores with pack-local `json-schema` fixtures. This is formatting
  evidence only; it does not exercise native tool-call request or response
  fields.
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
  `diff` block, applies that unified diff inside a run-owned workspace using
  the recount-capable `git apply` path, captures
  `patch/fix-greeting/rep-001.diff`, and uses a stdlib `verify-script` to
  check that `greet("Ada")` returns exactly `Hello, Ada!`.
- `endpoint-python-correctness`: non-streaming single-case `repo-task` pack
  for endpoint-only coding correctness. It uses the normal chat adapter path,
  prefers a fenced unified diff against a tiny inventory Python fixture, allows
  an explicit path-marked full-file replacement block for `inventory.py` as a
  fallback, and scores only through deterministic workspace mutation plus
  stdlib `verify-script` checks, including an edge dataset not shown directly
  in the prompt. It does not require `external-agent`. The first local M5
  `qwen3-coder:latest` Ollama run reached the adapter but failed against pack
  version `0.1.0` because the model emitted replacement-file content rather
  than an applicable unified diff; version `0.2.0` adds the explicit
  replacement block format. Later Qwen3.6 27B strict-GGUF preflights passed
  the `0.2.0` pack on M5, M4, and Hetzner after the recount-capable fenced
  diff apply path landed. Matrix promotion remains an explicit policy choice,
  not a missing validation step for that exact lane.
- `python-regression-fix`: non-streaming single-case `repo-task` pack with a
  small stdlib Python task-summary repo fixture. The case asks for a fenced
  unified diff to fix owner/status summary behavior, overdue-title filtering
  and ordering, and input immutability; verification remains deterministic and
  stdlib-only. This is a narrow fenced-patch repo-task signal, not production
  external agent-harness coverage.
- `django-dashboard-regression-fix`: non-streaming single-case `repo-task` pack
  with a compact multi-file stdlib dashboard-shaped fixture. The case asks for
  a fenced unified diff to fix project visibility, archived filtering, row
  formatting, deterministic sorting, and input immutability across
  `dashboard/permissions.py`, `dashboard/formatting.py`, and
  `dashboard/views.py`; verification remains deterministic and stdlib-only.
  This is a stronger bundled fenced-patch repo-task signal than the tiny patch
  smoke pack, not broad production coding-agent proof.
- `mini-project-completion`: non-streaming single-case `repo-task` pack with a
  tiny stdlib Python notes CLI project fixture. The case asks for a fenced
  unified diff to complete parsing, tag summaries, tag filtering, and CLI
  output across `notes/store.py` and `notes/cli.py`; verification remains
  deterministic and stdlib-only with visible and hidden execution checks. This
  is an opt-in project-completion prototype, not a default matrix pack.
- `patch-from-failure-external-agent`, `python-regression-fix-external-agent`,
  and `django-dashboard-regression-fix-external-agent`: opt-in direct-edit
  external-agent variants of the bundled repo-task fixtures. They select
  `harness = { id = "external-agent", timeout_s = 900 }`, instruct the external
  agent to edit the prepared workspace directly, then rely on normal workspace
  patch capture and deterministic verifiers. They are not default matrix packs.

Manual external benchmarks:

- `ds4-pi-django-resume-wrap`: real repo-mutating Desktop Django wrap benchmark
  for `django-resume` using Pi backed by local DS4 / DeepSeek V4 Flash. This is
  documented in `docs/ds4-pi-django-resume-wrap-benchmark.md` because the
  current `benchpack run` repo-task executor copies pack-owned fixtures and
  does not yet model an arbitrary pre-existing `~/workspaces` lab worktree as a
  first-class measured fixture.

## Initial Shape

The first implementation stays small:

1. A CLI that can run one benchmark pack against one endpoint.
2. An OpenAI-compatible adapter for `mlx_lm.server`, `llama-server`, vLLM, LM Studio, and similar servers.
3. An Ollama-native adapter for `/api/generate` so we retain Ollama's native timing fields.
4. Smoke, runtime-sweep, and JSON-formatting benchmarks, plus Phase 3
   coding-agent-shaped packs:
   the prompt-only `desktop-django-wrap` starter pack and measured
   repo-mutating fenced unified-diff packs such as `patch-from-failure`,
   `python-regression-fix`, and `django-dashboard-regression-fix`, plus
   `endpoint-python-correctness`, which also allows an explicit replacement
   block fallback, and the opt-in project-completion prototype
   `mini-project-completion`, and the endpoint-only `tool-json` formatting
   pack.
   `desktop-django-wrap` still treats directory
   fixtures as metadata-only; repo-task packs copy their repo fixtures into
   run-owned workspaces, apply the model edit there, and verify the result.
5. JSONL result artifacts plus a small Markdown summary.

The repository is private while the spec and first runner are still unstable.
