# Specification

## Goal

Build a small, reproducible benchmark runner for comparing local LLM runtimes
against real workloads.

The runner should support local laptops and small rented GPU hosts. Apple Silicon
is an important target, but the design must not assume unified memory, MLX, or
macOS-only tooling.

## Core Questions

- Runtime comparison: how do Ollama, Ollama MLX, direct `mlx-lm`, `llama.cpp`,
  and OpenAI-compatible servers compare on the same prompt?
- Hardware comparison: how do Apple Silicon machines compare with small CUDA
  hosts such as Hetzner GEX44-class GPUs?
- Workload comparison: does a runtime that is fast on a short prompt remain good
  for coding-agent traffic with large prompts, tool schemas, file contents, and
  failing test output?
- Workflow comparison: does a model/runtime pair complete a task, or does it
  drift, produce malformed tool calls, ignore instructions, or time out?

## Non-Goals

- Do not become a broad academic benchmark framework like HELM or lm-eval.
- Do not chase every public leaderboard task.
- Do not require a cloud account for basic local benchmarking.
- Do not require Apple Silicon, CUDA, or Ollama specifically.
- Do not judge model quality only by another model unless the benchmark explicitly
  declares that scoring mode.

## Benchmark Packs

A benchmark pack is a versioned directory containing:

- `benchpack.toml`: metadata, prompt cases, runtime requirements, and scoring mode.
- `prompts/`: prompt templates or static request payloads.
- `fixtures/`: small source repos, repo snapshots, or generated context inputs.
- `verify/`: deterministic scoring scripts when the workload has a pass/fail result.
- `README.md`: human intent and expected interpretation.

Initial packs:

- `smoke-chat`: tiny single-turn endpoint check.
- `runtime-sweep`: fixed prompts at several context sizes for TTFT and throughput.
- `desktop-django-wrap`: first Phase 3 prompt-only coding-agent-shaped pack
  derived from the `desktop-django-starter` wrapping workflow. Version `0.1.5`
  asks for concise Django-in-Electron wrapping plans with prompt-file-backed
  static chat prompts, uses `defaults.stream = true`, `defaults.warmup = 0`,
  `defaults.repetitions = 1`, and `scoring.mode = "regex"`. The regex requires
  `DDS_WRAP_PLAN` on the first line followed by the fixed labels `Inspect:`,
  `Electron shell:`, `Django runtime:`, `Packaging:`, and `Verification:` in
  order. It includes a static synthetic context file fixture and a compact
  static synthetic Django repo snapshot fixture. Both cases reference both
  fixtures by id. The referenced file fixture is appended to the loaded case
  prompt with stable delimiters; the directory snapshot remains metadata-only
  and is not read into prompts. The runner does not execute fixtures, copy
  directories, mutate repositories, extract patches, create disposable
  worktrees, replay agent sessions, change adapter or result schemas, or run
  verifier scripts. It is not a repo-mutating wrapping task.
- `patch-from-failure`: first bundled measured repo-mutating `repo-task` pack.
  Version `0.1.0` has one tiny stdlib-only Python repo fixture and one
  `fix-greeting` measured case. The prompt asks the model to return only a
  fenced `diff` unified diff that fixes `greeter.py`; the runner copies the
  repo fixture into `workspace/fix-greeting/rep-001/`, applies the model patch
  inside that workspace, captures `patch/fix-greeting/rep-001.diff`, and runs a
  stdlib `verify-script` that requires `greet("Ada")` to return exactly
  `Hello, Ada!`. The pack sets `defaults.warmup = 0`,
  `defaults.repetitions = 1`, `defaults.stream = false`, and case-local
  `scoring.mode = "verify-script"`.
- `tool-json`: strict JSON and tool-call formatting checks.

The bundled `runtime-sweep` pack is versioned as `0.1.0` and contains
`short`, `medium`, and `long` chat cases with fixed inline prompts. It sets
`defaults.stream = true`, `defaults.warmup = 1`, `defaults.repetitions = 3`,
and `scoring.mode = "none"`. The pack is intended for repeated local runtime
measurement, not model-quality comparison.

## Repo-Task Contract

`repo-task` is the case kind for coding-agent-shaped workloads that must change
a repository and prove correctness with deterministic verification. The current
implementation is deliberately partial: the runner prepares disposable
workspaces for measured executions, parses an optional case-local public
`harness = { id = "fenced-patch" }` selection for `repo-task` cases, runs the
task phase through a narrow internal executor boundary whose default CLI
implementation applies model output through a fenced unified-diff contract with
optional case-local task timeout support on that harness declaration,
captures deterministic patch
artifacts from
source-vs-workspace directory snapshots, writes deterministic task stdout/stderr
log artifacts for that task phase, and executes `verify-script` scoring against
the prepared workspace with a manifest-configurable verifier timeout and a
fixed `300.0` second default when no timeout is declared. The effective
`verify-script` scoring table may also declare a verifier-only string-to-string
`environment` table, which is overlaid onto a copy of the runner environment for
the verifier subprocess. It does not yet expose or run a public external
coding-agent harness, support manifest task commands, support repo-task warmups,
expose workspace cleanup/retention options, or configure task environments.
Measured repo-task
records include prepared workspace metadata, patch artifact paths, task log
artifact paths, verifier artifact paths, final repo-task verifier status, and
top-level `verify-script` scoring.

`desktop-django-wrap` remains a prompt-only `chat` pack. Its `kind = "repo"`
directory fixture is validated as metadata but is not copied, executed,
injected into prompts, mutated, turned into a worktree, used for patch
extraction, or passed to a verifier.

An initial internal agent-session harness path now exists behind the same
repo-task executor boundary. It can be supplied only by runner-side code, such
as focused tests, and is not manifest or CLI selectable. Current CLI repo-task
runs continue to use the fenced model-output `diff`/`patch` executor by
default. The internal harness input includes the prepared workspace path, case
metadata, model output text, run output directory, measured repetition number,
deterministic task stdout/stderr log paths, and validated helpers for reading
and writing UTF-8 text below the prepared workspace, deleting workspace files,
listing workspace file and directory paths, and checking workspace file
existence. Future production harnesses may add pack metadata and
model/adapter/endpoint/default context as needed for harness-owned model calls.
Those inputs remain internal implementation details, not new manifest fields or
adapter request fields.

The internal harness path may inspect and mutate only the prepared workspace and
may write only the existing task stdout/stderr logs under the run output
directory. Harness workspace helpers reject unsafe relative paths, including
absolute paths and `..` escapes. `list_workspace_paths()` returns deterministic
sorted POSIX workspace-relative paths for regular files only, including files
created earlier in the same harness invocation. Symlinks to regular files are
listed only when their target resolves inside the prepared workspace.
`list_workspace_dirs()` returns deterministic sorted POSIX workspace-relative
directory paths, including nested directories and directories created earlier in
the same harness invocation, excluding the workspace root, files, and symlinks
including symlinks to directories.
`workspace_file_exists()` uses the same path boundary and returns true only for
existing regular files, including in-workspace symlinks to regular files;
missing paths and directories return false. `delete_workspace_file()` uses the
same path boundary, returns true after deleting an existing regular file or
in-workspace symlink-to-file workspace entry, returns false for missing paths
and directories, and leaves symlink targets intact when deleting a symlink
entry. Unsafe delete paths, including symlink escapes outside the prepared
workspace, and `OSError` delete failures are runner failures before task logs
are recorded. Failed helper reads, writes, unsafe existence checks, unsafe
deletes, or failed workspace file or directory listing are runner failures
before task logs are recorded. It must not mutate pack-owned fixtures, prompts,
verifier scripts, source docs, or other files under the pack. If a later
harness needs model calls, those calls are runner/harness concerns and must not
change the normal adapter request or result schemas by default. Task logs remain
`task/<case-id>/rep-NNN.stdout.log` and
`task/<case-id>/rep-NNN.stderr.log` unless a later result-schema slice changes
that deliberately. Patch capture still happens after task execution, so
`patch/<case-id>/rep-NNN.diff` represents the workspace after the
executor/harness phase. Verifier execution still happens after patch capture.
Runner failures, such as an unreadable workspace or unwritable task log, remain
distinct from task outcomes, such as a model or harness failing to produce a
useful change; this narrow implementation does not add task status fields to
express that distinction.

Public repo-task harness selection is implemented only for the compatibility
executor. The public shape is an explicit case-local table on `repo-task`
cases:

```toml
[[cases]]
id = "fix-repo"
kind = "repo-task"
harness = { id = "fenced-patch" }
```

`harness.id` names a runner-known public harness. The only implemented public
id is currently `fenced-patch`, and it routes to the same fenced `diff`/`patch`
executor used when `harness` is absent. Future production external harnesses
will also be public repo-task harnesses selected by explicit case-local
`harness.id` values. They must not be inferred from model names, adapters,
endpoints, fixture shape, verifier choice, host environment, or pack id.
Absence of the field does not infer an external harness; the compatibility
default remains the current fenced executor.

The loader rejects `harness` on non-`repo-task` cases, unknown ids, missing or
non-string `id` values, non-table `harness` values, and unexpected extra keys.
The supported keys are currently `id` and optional `timeout_s`. When present,
`harness.timeout_s` must be a positive TOML integer or float and bounds the
selected task harness/executor phase; booleans, strings, zero, negative values,
arrays, and tables are rejected. It is currently enforced only for the
subprocess-backed fenced-patch executor. A timeout during `git apply --check`
is a task outcome: the workspace is known unchanged, task stderr records the
timeout, patch capture still runs, and verifier execution still follows patch
capture. A timeout during the actual `git apply` after successful preflight is
a runner failure because the workspace may be partially changed. Runner-side
internal agent-session harness callables cannot be combined with
`task_timeout_s`, because Python cannot safely preempt arbitrary in-process
code.

Public harness selection and task timeout support do not change adapter request
or adapter result schemas, existing raw request/response paths, existing
`run.jsonl` row shapes, or existing task log paths. Normal adapter
request/result schemas remain unchanged by default. If a future external
harness owns model calls, those calls are runner/harness concerns, not normal
adapter request fields. Task logs remain
`task/<case-id>/rep-NNN.stdout.log` and
`task/<case-id>/rep-NNN.stderr.log`. External harnesses may mutate only the
prepared workspace and write only allowed run-output artifacts. Pack-owned
fixtures, prompts, verifier scripts, source docs, and raw model artifacts
remain immutable or runner-owned as currently documented. Task environment
configuration, workspace retention, richer status/reporting, pack-level
harness defaults, repo-task warmups, and production external coding-agent
integration remain explicit future slices. Patch capture still reflects the
post-task workspace, verifier execution still runs after patch capture, and
this narrow public selection adds no new `run.jsonl` row fields.

Repo-task cases use `kind = "repo"` directory fixtures as immutable source
repository snapshots:

- Files and directories under `benchpacks/<pack>/fixtures/` are pack-owned
  source artifacts. The runner must never mutate source fixture paths.
- Existing path safety still applies: fixture paths are pack-relative, must
  resolve inside the pack after following symlinks, and must not depend on
  private local paths.
- Workspace preparation also audits symlinks inside the repo fixture. Absolute
  symlinks and relative symlinks whose target resolves outside the source repo
  fixture are rejected before copying. Internal relative symlinks may be
  preserved in the disposable workspace.
- A repo-task case must reference exactly one primary `kind = "repo"`
  directory fixture. That directory is the source for the disposable workspace.
- Referenced non-repo file fixtures remain prompt/context inputs unless a later
  explicit manifest field defines another role. Directory fixtures outside
  repo-task execution remain metadata-only.
- Referenced non-repo directory fixtures are rejected for repo-task cases until
  a later contract defines their role.

Repo-task measured execution prepares a run-owned disposable copy under the
output directory before the adapter call. Workspaces use the deterministic path
`workspace/<case-id>/rep-NNN/`, including `rep-001` when the pack has one
measured repetition. The workspace lives under the run result directory, not
under the pack directory. Each measured execution gets a fresh workspace and
the runner fails rather than merging if the destination already exists.
Repo-task warmups are rejected for now. If repo-task warmups are later allowed,
each warmup must also get its own disposable workspace and must not share
mutation state with measured executions. Cleanup and retention options remain
planned; keeping workspaces for debugging should be explicit, not accidental.

Mutation and verification are isolated to the run-owned workspace and output
directory. Pack contracts must not require implicit network access or private
host paths. Repo-task execution must not write outside the run output directory
and prepared workspace.

Current repo-task artifacts include:

- the disposable `workspace/` contents while retained locally
- `patch/<case-id>/rep-NNN.diff`, captured from workspace changes after the
  task executor phase
- `task/<case-id>/rep-NNN.stdout.log`, task stdout for the task executor phase
- `task/<case-id>/rep-NNN.stderr.log`, task stderr for the task executor phase
- `verify/<case-id>/rep-NNN.json`, structured verifier output
- `verify/<case-id>/rep-NNN.stdout.log`, verifier stdout
- `verify/<case-id>/rep-NNN.stderr.log`, verifier stderr

The current default task executor, also selected explicitly by
`harness = { id = "fenced-patch" }`, extracts the first fenced code block whose
info string is exactly `diff` or `patch` from the adapter output. That block
content is treated as a unified diff and applied inside the prepared workspace
after the adapter call and before patch capture. Non-matching fenced blocks are
ignored. If no matching block exists, or if the diff is empty, unsafe, cannot
be applied cleanly, or times out during `git apply --check`, the runner leaves
the workspace unchanged, writes a deterministic message to task stderr, and
still records the measured row. If timeout occurs during the actual
`git apply` after successful preflight, the runner fails rather than recording
a possibly partial workspace as a task outcome. On success, task stdout records
a short deterministic success message and task stderr remains empty. This
remains the behavior for current CLI repo-task runs.
The separate internal harness path is not a public executor selection system
and does not add new row fields.

Future executor implementations, including production external harnesses and
richer agent-session harnesses,
must preserve the same surrounding order and boundaries unless a later
specification slice deliberately changes them: workspace preparation first,
task execution inside the prepared workspace second, patch capture third,
verifier execution fourth, and reporter record last. Task environment
configuration, repo-task warmups, workspace retention options, richer task
status/reporting, pack-level harness defaults, and larger bundled repo-task
conversion remain planned follow-ups rather than current support.

Raw model request/response artifacts under `raw/` stay conceptually separate
from repo-task workspace and verifier artifacts. Measured repo-task
`run.jsonl` rows record prepared workspace metadata:
`workspace.path`, `workspace.source_fixture_id`, and `workspace.source_path`.
`workspace.path` is relative to the run output directory, and
`workspace.source_path` is the manifest-declared fixture path rather than an
absolute resolved path. They also record `patch.path`, a run-relative path to
the deterministic diff artifact under `patch/<case-id>/rep-NNN.diff`, including
`rep-001` for single-repetition packs. Empty workspace changes still produce an
empty patch file and a `patch.path` entry. They also record `task.stdout_path`
and `task.stderr_path`, run-relative paths to
`task/<case-id>/rep-NNN.stdout.log` and
`task/<case-id>/rep-NNN.stderr.log`, including `rep-001` for
single-repetition packs. For measured repo-task rows using
`scoring.mode = "verify-script"`, records also include `verify.path`,
`verify.stdout_path`, `verify.stderr_path`, `repo_task.status`, and
`repo_task.verify_exit_code`. `repo_task.status` is `"passed"` when the
verifier exit code is `0` and `"failed"` when it is nonzero or when the
verifier times out. `repo_task.verify_exit_code` records the integer process
exit code, or `null` when no exit code exists because the verifier timed out.
Top-level `scoring` is `{"mode": "verify-script", "passed": <bool>}` from that
verifier outcome. Curated result commits may include small summaries,
`hardware.json`, and compact `run.jsonl` rows, plus small intentional artifacts
such as patch diffs or `verify.json` when they are needed to explain a result.
Full disposable workspaces and large execution logs should normally stay local
or ignored.

Existing `contains` and `regex` scoring modes score prompt output.
`verify-script` is implemented only for measured `repo-task` executions: exit
code `0` means pass, nonzero means fail, timeout means fail with a null verifier
exit code, and the verifier receives the prepared workspace plus declared
case/run metadata as command-line inputs. The runner always writes the
deterministic verifier JSON/stdout/stderr artifact paths for a measured
verifier attempt. On timeout, stdout/stderr logs are still created, captured
partial output is preserved when Python exposes it, and the structured verifier
JSON is created or corrected with `exit_code: null`, `passed: false`,
`timed_out: true`, and the actual configured `timeout_s` value. If
`scoring.timeout_s` is absent from the effective `verify-script` scoring table,
the verifier timeout remains `300.0` seconds. If `scoring.environment` is absent
from the effective `verify-script` scoring table, verifier subprocesses inherit
the current runner environment. If it is present, its string keys and string
values are overlaid onto a copy of that environment for the verifier only.
Timeout and environment configuration are not repeated as normal top-level
`run.jsonl` fields, and environment values are not written to `run.jsonl` unless
the verifier script itself emits them in its own JSON or logs. Non-repo-task
cases that request `verify-script` fail clearly instead of falling back to
prompt-output scoring.

## Runtime Adapters

Adapters should hide request differences while preserving backend-specific metrics
where they are useful.

Required first:

- `openai-chat`: OpenAI-compatible `/v1/chat/completions`.
- `ollama-generate`: Ollama `/api/generate`, using native duration fields.

Likely next:

- `mlx-lm-cli`: direct `mlx_lm.generate` or a small Python wrapper, only if
  `mlx_lm.server` validation shows the OpenAI-compatible adapter is
  insufficient; see D-010 in `docs/decisions.md`.
- `llama-completion`: llama.cpp `/completion` for prompt-completion metrics.
- `agent-proxy`: record/replay for real coding-agent sessions.

## Metrics

Every run should record:

- wall-clock start/end/duration
- runtime adapter and endpoint
- model name and quantization label if known
- prompt bytes and estimated or reported prompt tokens
- cached prompt tokens when the backend reports prompt-cache hits
- generated bytes and estimated or reported output tokens
- time to first token when streaming is available
- prompt/prefill tokens per second when reported or measurable
- decode tokens per second
- total tokens per second
- process memory and GPU memory when available
- exit status and error payloads
- scoring result for deterministic packs

For `openai-chat`, `timing.ttft_s`, `timing.prefill_tps`, and
`timing.decode_tps` are populated when the pack sets `defaults.stream = true`
and the endpoint returns streaming chunks. TTFT is measured from request send to
the first non-empty `delta.content` chunk. `prefill_tps` is approximated as
reported prompt tokens divided by TTFT; `decode_tps` is approximated as reported
output tokens divided by post-TTFT wall time. These rates include transport and
server scheduling overhead because OpenAI-compatible streaming APIs do not
expose native prefill/decode durations.

The `openai-chat` streaming path requests `stream_options.include_usage` so
token counts can be captured when the server supports OpenAI's streaming usage
chunk. Some OpenAI-compatible local servers may reject that option; those runs
are recorded as adapter errors rather than silently retrying with different
request semantics unless the user explicitly selects the compatibility mode
described below. With `--openai-stream-usage omit`, streamed output and
`timing.ttft_s` are still measured from content chunks, but `tokens.prompt`,
`tokens.output`, `tokens.cached_prompt`, `timing.prefill_tps`, and
`timing.decode_tps` remain null when the endpoint does not report usage.

When OpenAI-compatible usage includes
`usage.prompt_tokens_details.cached_tokens`, `openai-chat` normalizes that count
as `tokens.cached_prompt` for both streaming and non-streaming responses.
Adapters and backends that do not report an equivalent value write
`tokens.cached_prompt = null`. The field records reported prompt-cache hits; it
does not by itself prove that two compared runs used equivalent cache state.

## CLI

The runner exposes subcommands for executing packs and comparing existing result
directories.

### `benchpack run`

```text
benchpack run <pack> --adapter <adapter> --model <model>
                     [--endpoint <url>]
                     [--out <dir>]
                     [--host-label <label>]
                     [--openai-stream-usage {include,omit}]
                     [--force]
```

- `<pack>` is either a path to a pack directory containing `benchpack.toml`
  or a pack name resolved under `benchpacks/<name>/`.
- `--adapter` selects a registered adapter (`openai-chat`, `ollama-generate`).
- `--model` is passed verbatim to the adapter.
- `--endpoint` is the runtime URL. Adapters resolve a base URL against their
  conventional path (e.g. `/v1/chat/completions`, `/api/generate`); the
  resolved URL is recorded in each result record as `endpoint`.
- `--openai-stream-usage` controls only `openai-chat` streaming request bodies.
  The default `include` sends `stream_options: {"include_usage": true}` when
  the pack requests streaming. `omit` still sends `"stream": true` but leaves
  out the `stream_options` key for endpoints that reject OpenAI streaming usage
  options. The option does not change non-streaming `openai-chat` requests.
- `--out` overrides the output directory. The default is
  `results/<YYYY-MM-DD>-<host-label>/`.
- `--host-label` overrides the auto-derived host label used in the default
  `--out` path.

### Pack-driven repetitions and warmup

`benchpack run` executes the ordered cases from the pack manifest. Each case may
run more than once based on `[defaults]` in `benchpack.toml`:

- `defaults.warmup` is the number of unrecorded warmup executions per case.
  It defaults to `0` and must be a non-negative integer.
- `defaults.repetitions` is the number of measured executions per case. It
  defaults to `1` and must be a positive integer.

For each case, warmup executions run first with the same adapter, model,
endpoint, prompt, and request defaults as measured executions. Warmups write raw
request/response files for debugging, but they are not scored and do not appear
in `run.jsonl` or `summary.md`.

Measured repetitions run after warmup and each measured execution appends one
record to `run.jsonl`. When `repetitions > 1`, each measured record includes a
top-level reporter-owned `repetition` field with a 1-based integer. Single
repetition packs keep the previous record shape and do not include
`repetition`.

### Output directory collision

The runner refuses to write into an output directory that already contains a
`run.jsonl`. This prevents two runs sharing the same `<date>-<host-label>`
from interleaving result rows or overwriting each other's `raw/` files.

- Pass `--force` to delete the existing directory before the new run starts.
- Or pass `--out <dir>` to write somewhere distinct.

`run.jsonl` itself is append-only within a single run: the reporter appends
one record per measured execution as it executes.

### `benchpack compare`

```text
benchpack compare <result-dir> <result-dir> [<result-dir> ...]
```

`benchpack compare` reads existing result directories and writes only a textual
comparison to stdout. Each argument must be a directory containing `run.jsonl`;
passing a `run.jsonl` file directly is not supported in the first compare
slice.

The command exits nonzero with a clear message when fewer than two inputs are
provided, an input is not a result directory, `run.jsonl` is missing, the file
contains no JSON records, or a JSONL row cannot be parsed as a JSON object.

The initial summary is intentionally small and deterministic:

- Inputs are identified by directory basename and path.
- Records are grouped by case and input run.
- Case order follows first appearance across the compared rows.
- `rows` counts measured records and `ok` counts rows with `ok = true`.
- `wall_s`, `ttft_s`, `decode_tps`, `total_tps`, and `tokens.output` are
  summarized with `statistics.median`.
- `timing.prefill_tps` is summarized with `statistics.median` but displayed as
  `prefill_tps med` only when the case-level `prefill parity` status is
  `comparable`; all other statuses render `—` for that column.
- `tokens.prompt` is summarized with `statistics.median` when numeric samples
  are present so cache interpretation is visible beside generated-token counts.
- `tokens.cached_prompt` is summarized with `statistics.median` when numeric
  samples are present, and `cache rows` displays numeric cached-token rows over
  total rows for the case/run group.
- `prefill parity` displays a deterministic case-level prompt/cache
  comparability status repeated on each run row for that case.
- Null, non-numeric, and non-finite metric values are ignored; a metric with no
  numeric samples is displayed as `—`.
- Differing `pack.id` or `pack.version` values produce a warning because
  cross-pack comparisons are not reliable.
- Incomplete cache metadata produces a per-case warning when any compared
  case/run group has measured rows without numeric `tokens.cached_prompt`.
- When all compared runs for a case have measured rows and every row in those
  case/run groups has a numeric `tokens.prompt` value, but the resulting
  `tokens.prompt` medians differ, compare warns that cache parity is not
  comparable across different prompts.
- When all compared runs for a case have complete cache metadata but cached
  prompt-token medians differ, compare warns that prefill speed should not be
  compared.
- When a compared input has no rows for a case that appears in another input,
  compare displays `0/0` cache coverage for that missing case/run group and
  suppresses prompt-token and cached-token median mismatch warnings for that
  case.

The `prefill parity` status uses the following priority order:

1. `missing-case`: at least one compared run has zero rows for the case.
2. `prompt-missing`: a non-empty case/run group has rows without numeric
   `tokens.prompt`.
3. `prompt-diff`: prompt metadata is complete, but prompt-token medians differ.
4. `cache-missing`: prompt parity holds, but a non-empty case/run group lacks
   complete numeric `tokens.cached_prompt`.
5. `cache-diff`: prompt and cache metadata are complete, but cached
   prompt-token medians differ.
6. `comparable`: every compared run has rows, complete numeric prompt/cache
   token metadata, matching prompt medians, and matching cached prompt medians.

`prefill_tps med` is a gated speed column, not independent parity evidence. It
uses only normalized `run.jsonl` `timing.prefill_tps` values that pass the
shared numeric metric filter, and it remains `—` when parity is
`missing-case`, `prompt-missing`, `prompt-diff`, `cache-missing`, or
`cache-diff`, even if timing values exist. New normalized rows can include
`tokens.prompt` and `tokens.cached_prompt`, but older rows may lack one or both
fields and missing values are not parity evidence. The table shows cache
metadata coverage because missing cached-token metadata is a common parity
blocker; prompt-token coverage is used internally for prompt mismatch warnings
but is not rendered as a separate column. Compare uses only normalized
`run.jsonl` fields for prompt/cache reporting and does not infer prompt or
cache state from prompt length, raw artifacts, timing fields, or backend-specific
durations.
The 2026-04-29 `llama-server` runtime-sweep rows were warm-cache rows. Compare
output must not be interpreted as cross-server cold prefill speed unless cache
parity is established separately.

## Result Artifacts

Results are easy to inspect and follow a fixed layout per run:

```text
results/
  2026-04-26-m5-mbp-64gb/
    run.jsonl
    summary.md
    hardware.json
    raw/
      case-001.request.json
      case-001.response.json
```

`hardware.json` is the per-run host metadata file described in
`docs/hardware-targets.md`. `summary.md` and `hardware.json` are committable;
`raw/` is generated and ignored by default.

Raw request/response names preserve the legacy shape when a pack has exactly one
measured repetition:

```text
raw/<case>.request.json
raw/<case>.response.json
```

When `defaults.repetitions > 1`, measured executions use stable 1-based
suffixes to avoid overwrites:

```text
raw/<case>.rep-001.request.json
raw/<case>.rep-001.response.json
raw/<case>.rep-002.request.json
raw/<case>.rep-002.response.json
```

Warmup executions use separate names that cannot collide with measured runs:

```text
raw/<case>.warmup-001.request.json
raw/<case>.warmup-001.response.json
```

`summary.md` contains one row per measured record. For repeated cases the case
cell is displayed as `<case>#<repetition>` so rows remain distinguishable without
changing the summary table columns. Single-repetition summaries keep the legacy
case label.

Large generated artifacts should stay out of git by default. Curated
`summary.md`, `hardware.json`, and small `run.jsonl` files may be committed.

## MVP

The first useful version is complete when it can:

1. Run `smoke-chat` against an OpenAI-compatible endpoint.
2. Run `smoke-chat` against Ollama via `/api/generate`.
3. Run a prompt-only coding-agent-shaped case derived from
   `desktop-django-starter`.
4. Write raw request/response artifacts and a summary table.
5. Record hardware and runtime metadata.
6. Run on macOS and a Linux CUDA host without changing benchmark pack contents.
