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
- `endpoint-python-correctness`: endpoint-only measured repo-mutating
  `repo-task` pack. Version `0.2.0` has one tiny stdlib-only inventory Python
  repo fixture and one `fix-inventory-aggregation` measured case. The prompt
  asks the model to return only one fenced `diff` block, preferring a unified
  diff that fixes `inventory.py` but allowing a full-file replacement block for
  `inventory.py` with explicit `*** Begin File: inventory.py` and
  `*** End File` markers. The runner copies the repo fixture into
  `workspace/fix-inventory-aggregation/rep-001/`, applies the model patch
  inside that workspace, captures
  `patch/fix-inventory-aggregation/rep-001.diff`, and runs a stdlib
  `verify-script` that checks SKU normalization, quantity summing, blank-SKU
  handling, input immutability, strict reorder threshold behavior, and a hidden
  edge dataset with numeric-string quantities. The pack sets
  `defaults.warmup = 0`, `defaults.repetitions = 1`,
  `defaults.stream = false`, and case-local
  `scoring.mode = "verify-script"`. It is the generic endpoint-only
  correctness signal and does not require `external-agent`.
- `patch-from-failure-external-agent`: explicit external-agent variant of the
  same workload. Version `0.1.1` uses the same fixture and verifier as
  `patch-from-failure`, but the prompt tells the external agent to edit the
  prepared workspace directly instead of returning a fenced patch. The measured
  case declares `harness = { id = "external-agent", timeout_s = 900 }`. It
  exists for opt-in agent-shaped evidence and does not change the default
  fenced-patch pack.
- `python-regression-fix`: second bundled measured repo-mutating `repo-task`
  pack. Version `0.1.0` has one small stdlib-only Python repo fixture and one
  `fix-task-summary` measured case. The prompt asks the model to return only a
  fenced `diff` unified diff that fixes `task_summary.py`; the runner copies
  the repo fixture into `workspace/fix-task-summary/rep-001/`, applies the
  model patch inside that workspace, captures
  `patch/fix-task-summary/rep-001.diff`, and runs a stdlib `verify-script`
  that checks task summary counts, missing-owner handling, input immutability,
  and overdue-title filtering and ordering. The pack sets
  `defaults.warmup = 0`, `defaults.repetitions = 1`,
  `defaults.stream = false`, and case-local
  `scoring.mode = "verify-script"`.
- `python-regression-fix-external-agent`: explicit external-agent variant of
  the same workload. Version `0.1.1` uses the same fixture and verifier as
  `python-regression-fix`, but the prompt tells the external agent to edit the
  prepared workspace directly instead of returning a fenced patch. The measured
  case declares `harness = { id = "external-agent", timeout_s = 900 }`. It is
  separate from the default fenced-patch pack.
- `django-dashboard-regression-fix`: bundled measured repo-mutating
  `repo-task` pack with a compact multi-file stdlib dashboard-shaped fixture.
  Version `0.1.0` has one `fix-dashboard-regressions` measured case. The
  prompt asks the model to return only a fenced `diff` unified diff that fixes
  project visibility, archived filtering, row formatting, deterministic
  sorting, and input immutability across `dashboard/permissions.py`,
  `dashboard/formatting.py`, and `dashboard/views.py`; the runner copies the
  repo fixture into `workspace/fix-dashboard-regressions/rep-001/`, applies the
  model patch inside that workspace, captures
  `patch/fix-dashboard-regressions/rep-001.diff`, and runs a stdlib
  `verify-script` with named deterministic checks. The pack sets
  `defaults.warmup = 0`, `defaults.repetitions = 1`,
  `defaults.stream = false`, and case-local
  `scoring.mode = "verify-script"`. It is a stronger bundled fenced-patch
  signal than the tiny patch smoke pack, not broad production coding-agent
  proof.
- `mini-project-completion`: opt-in bundled measured repo-mutating `repo-task`
  pack with a tiny stdlib Python notes CLI project fixture. Version `0.1.0`
  has one `complete-notes-cli` measured case. The prompt asks the model to
  return only a fenced `diff` unified diff that completes parsing, tag
  normalization, tag summaries, tag filtering, and CLI output across
  `notes/store.py` and `notes/cli.py`; the runner copies the repo fixture into
  `workspace/complete-notes-cli/rep-001/`, applies the model patch inside that
  workspace, captures `patch/complete-notes-cli/rep-001.diff`, and runs a
  stdlib `verify-script` with visible and hidden execution checks. The pack
  sets `defaults.warmup = 0`, `defaults.repetitions = 1`,
  `defaults.stream = false`, and case-local
  `scoring.mode = "verify-script"`. It is the first small
  project-completion prototype and is not part of the default matrix.
- `django-dashboard-regression-fix-external-agent`: explicit external-agent
  variant of the same workload. Version `0.1.1` uses the same fixture and
  verifier as `django-dashboard-regression-fix`, but the prompt tells the
  external agent to edit the prepared workspace directly instead of returning a
  fenced patch. The measured case declares
  `harness = { id = "external-agent", timeout_s = 900 }`. It is separate from
  the default fenced-patch pack.
- `tool-json`: strict JSON and tool-call-shaped formatting checks. Version
  `0.1.0` has two non-streaming chat cases, `strict-object` and
  `tool-call-arguments`, that require raw JSON with no Markdown or prose and
  score with pack-local `json-schema` fixtures. It is endpoint-only formatting
  evidence and does not exercise native tool-call request or response fields.

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
`harness` selection for `repo-task` cases, runs the task phase through a narrow
internal executor boundary whose default CLI implementation applies model
output through a fenced unified-diff or explicit replacement-file contract, and
can explicitly route
`harness = { id = "external-agent" }` to a runner-owned subprocess argv with
an appended runner-owned JSON context file and optional case-local task timeout
support on that harness declaration, and exposes a deterministic optional
external-agent model-call JSONL artifact path through that context,
captures deterministic patch
artifacts from
source-vs-workspace directory snapshots, writes deterministic task stdout/stderr
log artifacts for that task phase, and executes `verify-script` scoring against
the prepared workspace with a manifest-configurable verifier timeout and a
fixed `300.0` second default when no timeout is declared. The effective
`verify-script` scoring table may also declare a verifier-only string-to-string
`environment` table, which is overlaid onto a copy of the runner environment for
the verifier subprocess. It does not support manifest task commands, repo-task
warmups, workspace cleanup/retention options, or task environments.
Measured repo-task
records include prepared workspace metadata, patch artifact paths, task log
artifact paths, verifier artifact paths, final repo-task verifier status, and
top-level `verify-script` scoring.

`desktop-django-wrap` remains a prompt-only `chat` pack. Its `kind = "repo"`
directory fixture is validated as metadata but is not copied, executed,
injected into prompts, mutated, turned into a worktree, used for patch
extraction, or passed to a verifier. `tool-json` is also a prompt-only `chat`
pack, using deterministic JSON-schema scoring over adapter output text only.

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

Public repo-task harness selection uses an explicit case-local table on
`repo-task` cases:

```toml
[[cases]]
id = "fix-repo"
kind = "repo-task"
harness = { id = "fenced-patch" }
```

`harness.id` names a runner-known public harness. `fenced-patch` routes to the
same fenced `diff`/`patch` executor used when `harness` is absent.
`external-agent` routes to the runner-side `ExternalProcessHarness` subprocess
path when the runner has configured a subprocess argv through
`BENCHPACK_EXTERNAL_AGENT_ARGV`. Harness selection must not be inferred from
model names, adapters, endpoints, fixture shape, verifier choice, host
environment, or pack id. Absence of the field does not infer an external
harness; the compatibility default remains the current fenced executor.

The loader rejects `harness` on non-`repo-task` cases, unknown ids, missing or
non-string `id` values, non-table `harness` values, and unexpected extra keys.
The supported keys are currently `id` and optional `timeout_s`. When present,
`harness.timeout_s` must be a positive TOML integer or float and bounds the
selected task harness/executor phase; booleans, strings, zero, negative values,
arrays, and tables are rejected. It is enforced for the subprocess-backed
fenced-patch and external-agent executors. For `fenced-patch`, unified diff
preflight first tries `git apply --check --recount` so otherwise valid model
diffs with inaccurate hunk line counts can be applied as complete hunks rather
than partially counted edits; if recount preflight rejects the diff, the runner
falls back to the standard `git apply --check` path for compatibility. The
actual apply command matches the successful preflight mode. The timeout budget
is applied independently to each subprocess call. A timeout during
`git apply --check` is a task outcome: the workspace is known unchanged, task
stderr records the timeout, patch capture still runs, and verifier execution
still follows patch capture. A timeout during the actual `git apply` after
successful preflight is a runner failure because the workspace may be partially
changed. For `external-agent`, a timeout is a task outcome when the runner
stops the external subprocess process group and task logs can be written.
Runner-side internal agent-session harness callables cannot be combined with
`task_timeout_s`,
because Python cannot safely preempt arbitrary in-process code.

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
harness defaults, repo-task warmups, and full production external coding-agent
integration remain explicit future slices. Patch capture still reflects the
post-task workspace, verifier execution still runs after patch capture, and
this narrow public selection adds no new `run.jsonl` row fields.

The first public external subprocess harness uses this manifest shape:

```toml
[[cases]]
id = "fix-repo"
kind = "repo-task"
harness = { id = "external-agent", timeout_s = 120 }
```

The subprocess argv is runner-owned, not manifest-owned. When any loaded case
uses `harness.id = "external-agent"`, `benchpack run` requires
`BENCHPACK_EXTERNAL_AGENT_ARGV` before it creates the run output directory or
makes adapter calls. The value must be a JSON array of non-empty strings without
NUL bytes, for example:

```sh
BENCHPACK_EXTERNAL_AGENT_ARGV='["/path/to/fake-agent.py"]'
```

The runner does not use shell parsing and does not accept a plain command
string. It appends `--workspace <prepared-workspace>`, `--case <case-id>`,
`--output-dir <run-output-dir>`, `--repetition <N>`, and
`--context <run-output-dir>/task/<case-id>/rep-NNN.context.json` to that argv,
runs the process without a shell in the prepared workspace, captures
stdout/stderr into the existing task logs, then captures the workspace patch
and runs any verifier. When `harness.timeout_s` is set, the external subprocess
runs in a POSIX process group/session so the runner can terminate the process
tree on timeout, wait a short bounded grace period, and escalate to a kill
signal if needed before writing timeout task logs. The normal adapter call
still happens before the repo-task task phase in this slice. The context also
names an optional harness-owned model-call log path at
`task/<case-id>/rep-NNN.model-calls.jsonl`; the runner still does not require
or pre-create that artifact, and it remains outside `run.jsonl`, but
allowlisted safe telemetry is summarized when the file exists.

An external harness receives runner-owned inputs, not broad manifest command
blobs: currently the appended prepared workspace path, case id, run output
directory, measured repetition number, and the explicit JSON context file. The
context JSON is versioned with `version = 1` and includes pack id/version/
description, case id/kind/loaded prompt/fixture refs/harness id and timeout,
prepared workspace path and source fixture metadata, run output directory,
repetition, task stdout/stderr paths, optional persisted `run-metadata.json`
path, optional model-call JSONL artifact path, selected adapter id/model/user
endpoint argument/effective defaults, and the pack fixture inventory with
manifest-declared relative fixture paths. It does not include raw adapter
request/response payloads, environment variables, credentials, or new result
row fields. Harness-owned model calls do not write normal adapter `raw/`
request/response artifacts unless a later result schema slice explicitly
defines how they are represented.

An external harness may inspect and mutate only the prepared workspace. It may
write the existing task stdout/stderr logs through the runner-owned capture path
under `task/<case-id>/rep-NNN.*.log` and may optionally write JSONL model-call
telemetry to the context-provided
`task/<case-id>/rep-NNN.model-calls.jsonl` path. The runner does not require,
pre-create, or add that file to `run.jsonl`. When the file exists, the runner
parses only the recommended safe telemetry shape for aggregate summaries in
`summary.md` and `benchpack report`; invalid or unsafe lines are counted but
their payloads are not reported. The recommended minimal JSONL line shape for
harness authors is one JSON object per harness-owned model call:

```json
{"schema_version":1,"sequence":1,"model":"test-model","ok":true}
```

Recommended core fields are `schema_version` as integer `1` for this
recommended shape, `sequence` as a positive integer call sequence within the
external-agent task phase, `model` as the model identifier when known, and `ok`
as a boolean success indicator. Useful optional fields include `started_at`,
`ended_at`, `duration_s`, `adapter`, `endpoint`, `response_format`,
`token_budget_field`, `finish_reason`, `prompt_tokens`, `output_tokens`,
`cached_prompt_tokens`, and a short `error` string when
`ok` is false. The summary allowlist is exactly those fields; unknown keys,
malformed JSON, wrong types, non-finite numbers, negative token counts, and
unsafe strings make a line invalid for summary purposes. Safe strings are
short strings without control characters or Unicode separator characters other
than plain spaces. `endpoint` is treated as a label, not a URL; values
containing URL schemes, query strings, or userinfo markers are invalid for
summaries. Summary output reports counts,
success/failure/error counts, unique model/adapter/endpoint labels, summed
duration, and summed token fields only. It does not report full prompts, full
responses, request bodies, headers, environment variables, API keys, bearer
tokens, credentials, or short error text. Richer harness-owned telemetry is
outside the runner-normalized contract until a later schema slice explicitly
defines it.

A deterministic local reference harness is available at
`examples/external-agent/reference-agent.py`. It demonstrates the public argv
and context handoff, validates core context fields against the appended
arguments, mutates only the prepared workspace, writes one recommended
model-call JSONL line to the context-provided path, and makes no live model
calls. It is example harness guidance only; it does not change runner parsing,
validation, result rows, summaries, reports, adapter raw artifacts, or
production agent integration.

A second deterministic example is available at
`examples/external-agent/model-call-agent.py`. It uses the same public argv and
context handoff, performs one tiny HTTP JSON request to an example-owned local
loopback endpoint supplied by `--model-call-url`, rejects credentials and query
strings in that URL, writes only the deterministic response content into the
prepared workspace, and writes one safe JSONL telemetry line to the
context-provided model-call path. The example does not call live model services
by itself and does not make the model-call log a runner schema.

A local live-evidence wrapper is available at
`examples/external-agent/codex-oss-agent.py`. It uses the same public argv and
context handoff, then runs `codex exec --oss --local-provider <provider>` in
the prepared workspace with `--sandbox workspace-write` and `--ephemeral`.
This wrapper is intended only when Codex CLI and the selected local provider
and model are already available locally, such as a local Ollama model; it is
not a cloud-backed or credential-injecting harness.

An authenticated OpenAI-compatible direct-edit wrapper is available at
`examples/external-agent/openai-direct-edit-agent.py`. It uses the same public
context handoff, calls a configured `/chat/completions` endpoint from the
operator machine, expects a JSON full-file replacement payload, and writes only
prompt-allowed workspace files. The wrapper defaults to a portable plain
non-streaming request, with explicit opt-in `--response-format json_object`
and `--response-format json_schema` modes for endpoints that support those
OpenAI-style structured-output request shapes. The JSON-schema mode constrains
the assistant payload to the direct-edit object shape and the prompt-derived
allowed path list. The wrapper validates the complete `files` array before it
writes any replacement content, rejects duplicate or disallowed paths, and
restores original file contents if an application write fails. The wrapper
defaults to `--max-tokens 4096` and sends that budget as the portable
`max_tokens` request field; operators may increase the budget and may opt into
`--token-budget-field max_completion_tokens` for endpoints or models that
require that newer OpenAI-style chat-completions field. These modes are wrapper
request options only; they do not change benchpack manifests, adapter schemas,
result rows, or default helper matrices.

Other richer harness artifacts must be explicitly named by a later
artifact/schema slice before they are allowed. It must not mutate pack-owned
fixtures, prompts, verifier scripts, source docs, `run-metadata.json`,
`hardware.json`, raw adapter artifacts, or any path outside the prepared
workspace and permitted run-output artifacts. The current contract does not
provide manifest task environment configuration, shell expansion, secret
injection, arbitrary shell commands, workspace retention, or cleanup controls.

`harness.timeout_s` remains the case-local task-phase timeout. It is separate
from adapter request timeouts, verifier `scoring.timeout_s`, and any future
whole-run timeout. This keeps runner failures, such as unsafe paths or
unwritable logs, distinct from task outcomes, such as the external harness
timing out, exiting nonzero, making no useful change, or leaving verifier
failures for deterministic scoring.

The surrounding ordering is fixed unless a later specification slice
deliberately changes it: prepare the workspace, execute the selected task
harness, capture `patch/<case-id>/rep-NNN.diff` from source fixture versus
post-task workspace, run any `verify-script`, then write the result record. The
existing task logs and verifier status are sufficient for this public slice; no
new row fields are required until a real external harness proves that richer
status or reporting is necessary.

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
- `task/<case-id>/rep-NNN.context.json`, runner-owned external-agent context
  input for public `external-agent` executions only
- `task/<case-id>/rep-NNN.model-calls.jsonl`, optional external-agent
  harness-owned model-call telemetry path exposed only through the context
- `verify/<case-id>/rep-NNN.json`, structured verifier output
- `verify/<case-id>/rep-NNN.stdout.log`, verifier stdout
- `verify/<case-id>/rep-NNN.stderr.log`, verifier stderr

The current default task executor, also selected explicitly by
`harness = { id = "fenced-patch" }`, extracts the first fenced code block whose
info string is exactly `diff` or `patch` from the adapter output. That block
content is treated as a unified diff and applied inside the prepared workspace
after the adapter call and before patch capture. As a narrow fallback for
endpoint-only repo-task packs, the same fenced block may instead contain a
full-file replacement whose first content line is exactly
`*** Begin File: <repo-relative-path>` and whose final marker line is exactly
`*** End File`; trailing whitespace on the end marker is tolerated. The runner
writes only that explicit repo-relative UTF-8 file with LF-canonicalized line
endings, after applying the same workspace path boundary checks used by harness
helpers. Non-matching fenced blocks are ignored. If no matching block exists,
or if the diff/replacement block is empty, unsafe, invalid, or cannot be
applied cleanly, the runner leaves the workspace unchanged, writes a
deterministic message to task stderr, and still records the measured row. For
unified diff blocks only, a timeout during `git apply --check` also leaves the
workspace unchanged as a task outcome. If timeout occurs during the actual
`git apply` after successful preflight, the runner fails rather than recording
a possibly partial workspace as a task outcome. On success, task stdout records
a short deterministic success message and task stderr remains empty. This
remains the default behavior for current CLI repo-task runs.
The separate internal harness path is not a public executor selection system
and does not add new row fields. Runner-side callers and tests may also supply
an internal external-process harness request through `run_repo_task_executor`.
That path accepts an explicit argv sequence from runner-owned code, appends
bounded context arguments for the prepared workspace, case id, output
directory, repetition, and optional context JSON path, runs without a shell in
the prepared workspace,
captures stdout/stderr to the existing task log paths, and preserves patch
capture and verifier ordering. A clean nonzero subprocess exit and a timeout
where the runner stops the external subprocess process group and closes logs
are task outcomes represented through the existing logs and downstream verifier
result. Unsafe
argv shape, missing executable, invalid workspace/output paths, incompatible
harness combinations, or unwritable required logs remain runner failures. The
public `external-agent` CLI path now routes to this subprocess executor with an
argv loaded from `BENCHPACK_EXTERNAL_AGENT_ARGV` plus `--context <path>` to the
runner-owned JSON context file; it does not add CLI flags, manifest commands,
adapter fields, raw artifacts, or `run.jsonl` fields.

Future executor implementations, including production external harnesses and
richer agent-session harnesses,
must preserve the same surrounding order and boundaries unless a later
specification slice deliberately changes them: workspace preparation first,
task execution inside the prepared workspace second, patch capture third,
verifier execution fourth, and reporter record last. Task environment
configuration, repo-task warmups, workspace retention options, richer task
status/reporting, pack-level harness defaults, and production external
coding-agent integration remain planned follow-ups rather than current support.

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

Existing `contains`, `regex`, and `json-schema` scoring modes score prompt
output. `json-schema` parses raw adapter output text as JSON and validates it
against a pack-local schema subset; malformed JSON or shape mismatches are
ordinary scoring failures. `verify-script` is implemented only for measured
`repo-task` executions: exit code `0` means pass, nonzero means fail, timeout
means fail with a null verifier exit code, and the verifier receives the
prepared workspace plus declared case/run metadata as command-line inputs. The
runner always writes the deterministic verifier JSON/stdout/stderr artifact
paths for a measured verifier attempt. On timeout, stdout/stderr logs are still
created, captured partial output is preserved when Python exposes it, and the
structured verifier JSON is created or corrected with `exit_code: null`,
`passed: false`, `timed_out: true`, and the actual configured `timeout_s`
value. If `scoring.timeout_s` is absent from the effective `verify-script`
scoring table, the verifier timeout remains `300.0` seconds. If
`scoring.environment` is absent
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

`openai-chat` can optionally authenticate to OpenAI-compatible endpoints with a
bearer token read from an explicitly named environment variable. The CLI option
is `--openai-api-key-env <ENV_NAME>`. When supplied, the adapter reads
`ENV_NAME` at request time and sends `Authorization: Bearer <value>` on both
streaming and non-streaming HTTP requests. When omitted, no Authorization
header is sent, and the runner does not implicitly read `OPENAI_API_KEY` or any
other default secret variable. If the option is supplied but the named
environment variable is missing or empty, the adapter fails deterministically
with an error that names only the environment variable. Raw request artifacts
remain the JSON request body only; they do not include headers. Result rows,
summaries, reports, run metadata, task logs, and external-agent context must
not contain bearer token values. External-agent context may contain the
configured environment variable name as part of adapter defaults, never the
resolved token value.

## CLI

The runner exposes subcommands for executing packs, comparing existing result
directories, rendering read-only Markdown reports from existing results, and
building a local SQLite index over existing result artifacts.

### `benchpack run`

```text
benchpack run <pack> --adapter <adapter> --model <model>
                     [--endpoint <url>]
                     [--out <dir>]
                     [--host-label <label>]
                     [--run-metadata <json-file>]
                     [--openai-stream-usage {include,omit}]
                     [--openai-api-key-env <ENV_NAME>]
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
- `--openai-api-key-env` controls only `openai-chat` HTTP authentication. When
  supplied, the adapter reads the bearer token from the named environment
  variable and sends `Authorization: Bearer <token>` on each request. The
  option is explicit and opt-in; the runner does not automatically read
  `OPENAI_API_KEY`. The environment variable name may appear in adapter
  defaults and external-agent context, but the token value must not be written
  to raw request/response artifacts, result rows, summaries, task logs,
  run metadata, reports, or committed documentation.
- `--out` overrides the output directory. The default is
  `results/<YYYY-MM-DD>-<host-label>/`.
- `--host-label` overrides the auto-derived host label used in the default
  `--out` path.
- `--run-metadata` points at a user-supplied JSON object. When supplied, the
  runner validates it before creating or replacing the output directory and
  writes the normalized object to `run-metadata.json` beside the result.
  Intended fields are structured runtime, model, and operating-condition notes,
  not autodiscovered facts.

### `scripts/benchpack-tmux-matrix`

The repository also ships a narrow operational helper that renders or launches
sequential tmux windows around existing `benchpack run` commands. Its default
matrix remains `smoke-chat`, `runtime-sweep`, `desktop-django-wrap`, and
`patch-from-failure`; named pack sets and positional packs are explicit
operator choices. The helper requires `--adapter`, `--host-label-prefix`, and
`--run-metadata`, passes through optional endpoint, streaming usage,
authenticated endpoint environment-variable name, and `--force`, and does not
change pack semantics, result schemas, metadata schemas, server lifecycle, SSH,
artifact pullback, or reporting behavior.

The helper supports an opt-in `--preset qwen36-27b-strict-gguf` for the
validated Qwen3.6 27B strict-GGUF lane. When omitted, that preset supplies
`--model qwen36-27b-q4km` and
`--endpoint http://127.0.0.1:18082/v1`; explicit `--model` or `--endpoint`
arguments override those defaults. The preset is scoped to the exact
`Qwen3.6-27B-Q4_K_M.gguf` `llama-server --reasoning off` workflow and does not
add `endpoint-python-correctness` to the default four-pack matrix.

The recommended `--run-metadata` shape is permissive and optional by field:

```json
{
  "runtime": {
    "name": "llama-server",
    "version": "9010",
    "command": "llama-server --model ...",
    "options": {
      "ctx_size": 4096,
      "gpu_layers": "auto"
    }
  },
  "model": {
    "id": "qwen2.5-0.5b-instruct-q4_k_m",
    "source": "local-gguf",
    "quantization": "Q4_K_M",
    "sha256": "..."
  },
  "operating_conditions": {
    "power": "not captured",
    "thermal": "not captured",
    "background_load": "no intentional throttling setup"
  },
  "notes": "optional short note"
}
```

Validation is deliberately small: the metadata file must exist, parse as JSON,
and have a JSON object at the root. If present, `runtime`, `model`, and
`operating_conditions` must be JSON objects, and `notes` must be a string.
Missing fields are allowed. The runner does not infer runtime version, server
command, model checksum, quantization, context size, cache settings, power
state, thermal state, or background load.

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

### `benchpack report`

```text
benchpack report <result-dir> [<result-dir> ...]
benchpack report --set <manifest.toml>
```

`benchpack report` reads existing result directories and writes only Markdown to
stdout. Each input must be a directory containing `run.jsonl`; when
`hardware.json` is present beside it, the report includes host identity fields
such as `hostname`, `chip`, `hardware_model`, `hardware_model_name`,
`hardware_model_identifier`, `ram_mb`, `os`, and `gpus`. Missing
`hardware.json` is tolerated and reported explicitly. When
`run-metadata.json` is present, the report includes a concise table for the
user-supplied runtime, model, operating-condition, and notes fields. Missing
`run-metadata.json` is tolerated and reported explicitly; malformed metadata
fails with a clear error. When external-agent model-call JSONL artifacts exist
under `task/<case-id>/rep-NNN.model-calls.jsonl`, the report includes aggregate
safe telemetry summaries. Missing model-call logs are tolerated. Malformed or
unsafe JSONL lines are counted as invalid without echoing their payloads. When
repo-task rows include `repo_task`, the report includes compact
`Repo-Task Outcome Summary` and `Repo-Task Outcomes` tables derived from
existing row fields and patch artifacts. The summary section counts rows by
report-only outcome label across the full report set and per individual run.
The detail table shows case, repetition,
`repo_task.status`, verifier exit code, scoring result, patch byte count when
the patch artifact is available under the result directory, and a report-only
outcome label such as `passed`, `failed-no-mutation`,
`failed-source-mutation`, `failed-non-source-mutation`, or
`failed-unknown-mutation`. The source/non-source split is derived from patch
artifact paths only; generated/cache artifacts such as `__pycache__` and
`.pytest_cache` do not count as source mutations. This is a read-only summary
and does not add fields to `run.jsonl`.

The optional `--set <manifest.toml>` mode loads a source TOML report-set
manifest and expands it to the same existing result-directory inputs before the
normal report loader runs. `--set` and positional result directories are
mutually exclusive, and the command requires exactly one input source: either
one or more positional result directories or one report-set manifest. The
manifest shape is intentionally narrow:

```toml
version = 1
result_dirs = [
  "results/<date>-m5-max-runtime",
  "results/<date>-m4-max-runtime",
]
```

`version` is optional; when present it must be integer `1`. `result_dirs` is
required and must be a non-empty list of non-empty strings. Relative
`result_dirs` entries resolve relative to the manifest file's parent directory;
absolute paths are accepted only as normal result-directory inputs and remain
the user's responsibility. Malformed TOML or invalid schema fails with a clear
report error and no traceback. Missing `run.jsonl` in an expanded directory
continues to fail through the existing result loader.

The report is meant to be pasted into run notes or used as a comparison-report
skeleton. It summarizes:

- input result directories and row counts
- pack id/version values
- adapter, model, and endpoint values from normalized rows
- user-supplied runtime/model/operating metadata when `run-metadata.json`
  exists
- external-agent model-call summary counts, success/failure/error counts,
  unique model/adapter/endpoint/request-shape/finish labels, summed duration,
  and summed token fields when optional model-call logs exist
- repo-task outcome summaries when `repo_task` rows exist, including patch byte
  counts and no-mutation versus mutation-visible failure labels
- row and `ok` counts by run/case
- scoring pass, fail, and unscored counts by run/case
- the same median wall time, TTFT, prefill TPS, decode TPS, total TPS, output
  tokens, prompt tokens, cached prompt tokens, cache rows, warnings, and
  `prefill parity` statuses used by `benchpack compare`

The report command is read-only: it does not execute packs, collect hardware,
load adapters, read `raw/`, write result artifacts, mutate result directories,
copy result files, schedule tmux sessions, perform SSH, manage remote hosts, or
change `benchpack compare` behavior. Report-set manifests are only an input
expansion step. The command may parse optional `run-metadata.json` for display,
but compare remains independent of that artifact. Its comparison section reuses
the compare summarization and parity helpers so report medians and statuses do
not silently diverge from `benchpack compare`.

### `benchpack registry import`

```text
benchpack registry import --db <sqlite-db> <result-dir> [<result-dir> ...]
```

`benchpack registry import` creates or updates a local SQLite index over
existing result directories. It is an indexing workflow, not a new benchmark
artifact authority: `results/<date>-<host-label>/`, `run.jsonl`,
`hardware.json`, `run-metadata.json`, pack manifests, and intentionally retained
artifacts remain the canonical evidence.

Each input must be a result directory containing a non-empty `run.jsonl`. The
importer validates that every row is a JSON object with the normalized runner
fields needed for indexing: pack id/version, case id, adapter, endpoint, model,
boolean `ok`, `timing` object, `tokens` object, optional positive integer
`repetition`, optional scoring object with boolean `passed`, and optional
`repo_task` verifier status. Optional `hardware.json` must be a JSON object
when present. Optional `run-metadata.json` uses the same permissive validation
as `benchpack run --run-metadata` and `benchpack report`.

The SQLite schema version is `2`, recorded in `PRAGMA user_version` and a
`registry_meta` row. The schema stores:

- one `runs` row per canonical result-directory path, with import time,
  `run.jsonl` SHA-256, row count, compact JSON lists of pack ids/versions,
  adapters, models, and endpoints, optional hardware and run-metadata JSON, and
  selected host/runtime/model metadata columns for filtering;
- one `result_rows` row per `run.jsonl` record, with normalized pack/case,
  repetition, adapter/model/endpoint, `ok`, timing metrics, token metrics,
  scoring mode/pass state, repo-task verifier status, and a compact
  sort-keyed JSON re-encoding of the normalized row.
- one `result_case_stats` row per imported run/pack-version/case, with row
  counts, ok counts, prompt-token coverage and median, cached-prompt-token
  coverage and median, and prefill-TPS coverage and median.

Schema version `2` also promotes registry-facing comparability anchors from
optional `run-metadata.json` into nullable `runs` columns: `comparison_mode`,
`comparison_boundary`, host label and repo commit, runtime endpoint and
options, model artifact repo/file/revision/checksum, quantization, and
operating-condition notes for power, thermal state, and background load. These
fields are indexing aids for future comparison views. They do not change
`run.jsonl`, infer parity that was not recorded, or replace compare's
case-level prompt/cache parity checks. Empty strings in these optional string
anchors are indexed as absent (`NULL`), matching the registry's nullable-field
semantics for missing metadata.

The `runs.host_hostname` and `runs.host_platform` filter columns come from
`hardware.json`. The run-label and repo-commit host filters come from
`run-metadata.json` (`host.label`, `host.repo_commit`, or the legacy
`repo.commit` fallback) because they describe the benchmark campaign rather
than the machine probe.

Re-importing the same result directory updates the `runs` row and replaces its
indexed `result_rows` and `result_case_stats`. This keeps the database aligned
with the current artifact contents without appending duplicate rows.

The command writes only the requested SQLite database. It does not mutate result
directories, write report artifacts, copy raw payloads, inspect `raw/`,
workspace, task, patch, verify, or model-call artifacts, execute packs, contact
endpoints, collect hardware, run compare/report, perform SSH, or create a public
submission bundle. The local registry may store the canonical local result
directory path for idempotent re-imports; public bundle/export privacy rules
are handled by the separate bundle command below.

### `benchpack registry duplicates`

```text
benchpack registry duplicates --db <sqlite-db>
```

`benchpack registry duplicates` is a read-only inspection command over an
existing schema version `2` registry. It groups imported `runs` rows by the
registry-stored `run_jsonl_sha256` value and prints only groups where more than one
run has identical `run.jsonl` contents. Each duplicate entry includes the
registry run id, label, row count, import time, and indexed result-directory
identity. If no duplicates are present, the command prints a compact
no-duplicates message and exits successfully.

This is duplicate visibility, not automatic moderation or deletion. It does not
mutate the database, mutate result directories, compare raw artifacts, inspect
omitted bundle artifacts, infer semantic equivalence for different `run.jsonl`
contents, or contact endpoints. Re-importing the same result directory still
updates that directory's single registry row rather than creating a duplicate.

### `benchpack registry query`

```text
benchpack registry query --db <sqlite-db> [--run-id <id> ...]
benchpack registry query --db <sqlite-db> [--label <label> ...]
benchpack registry query --db <sqlite-db> [--pack <id>] [--case <id>] [--adapter <id>] [--model <id>]
benchpack registry query --db <sqlite-db> [--host-label <label>] [--runtime <name>] [--quantization <value>]
benchpack registry query --db <sqlite-db> [--ok true|false] [--scoring-passed true|false] [--limit <n>]
```

`benchpack registry query` is a read-only JSON query over an existing schema
version `2` registry. With no selectors, it searches every imported run ordered
by registry id and row index. `--run-id` and `--label` mirror the registry
report selectors and are mutually exclusive. Additional filters match indexed
normalized fields exactly: pack id, case id, adapter id, model id, host label,
runtime name, model quantization, adapter `ok` state, and deterministic
`scoring.passed` state. `--limit` bounds the number of result rows returned.

The command emits a JSON array. Each item contains compact run identity fields,
the normalized result-row fields used by reports (`pack`, `case`, repetition,
adapter/model/endpoint, timing, tokens, scoring, and repo-task verifier state),
and selected host/comparison/runtime/model metadata that was indexed from
`hardware.json` and `run-metadata.json`.

This is a local machine-readable query API over compact SQLite rows, not an
artifact reader or hosted service. It does not require source result
directories to exist, mutate the database, read `raw/`, workspaces, task logs,
verifier artifacts, patch files, or model-call logs, contact endpoints, infer
missing metadata, or create hosted upload/review state.

### `benchpack registry report`

```text
benchpack registry report --db <sqlite-db> [--run-id <id> ...]
benchpack registry report --db <sqlite-db> [--label <label> ...]
```

`benchpack registry report` renders the existing Markdown report shape from
indexed SQLite rows. With no filters, it reports every imported run ordered by
registry id. `--run-id` may be repeated to select specific run ids, and
`--label` may be repeated to select runs by registry label; the two selector
types are mutually exclusive.

The command reads schema version `2` registry data: `result_rows.raw_json`
provides normalized result records, and `runs.hardware_json` plus
`runs.run_metadata_json` provide report-facing host and user-supplied runtime
metadata when they were indexed. It reuses the normal report renderer, so row
counts, scoring counts, median wall time, TTFT, prefill TPS, decode TPS, total
TPS, token medians, cache rows, warnings, and `prefill parity` status follow
the same rules as `benchpack report` and `benchpack compare`.

The registry report is intentionally a snapshot report over indexed compact
data, not an artifact reader. It does not require the canonical result
directories to exist, and it does not read `raw/`, workspaces, task logs,
verifier artifacts, patch files, or model-call logs. Because those artifact
files are not in the SQLite registry, external-agent model-call summaries are
omitted from registry-backed reports and repo-task patch byte counts render as
unknown. Use directory-backed `benchpack report` when artifact-backed
model-call or patch-size summaries are required.

### `benchpack registry site`

```text
benchpack registry site --db <sqlite-db> --out <site-dir> [--force]
benchpack registry site --db <sqlite-db> --out <site-dir> [--run-id <id> ...]
benchpack registry site --db <sqlite-db> --out <site-dir> [--label <label> ...]
```

`benchpack registry site` creates a static read-only snapshot from indexed
SQLite registry rows. With no selectors, it includes every imported run ordered
by registry id. `--run-id` and `--label` mirror the registry report selectors
and are mutually exclusive.

The output directory contains:

- `index.html`, a local browser view with dense run tables, a comparison matrix
  of per-run/per-case median latency, throughput, token, and scoring fields,
  case-metric coverage tables, browser-side filters for pack, case, host,
  runtime, model, quantization, and table type, and an embedded copy of the
  generated Markdown report;
- `report.md`, the same registry-backed Markdown report produced through the
  existing report renderer;
- `snapshot.json`, a machine-readable static snapshot with schema version `1`,
  the registry schema version, generation time, source database name, compact
  run metadata, comparison-matrix rows, case-metric rows, and the report path.
  Comparison-matrix and case-metric entries include the registry `run_id` so
  consumers can join them back to `runs` even when run labels collide.
  Case-metric entries also include compact host, runtime, and model metadata
  copied from the indexed run row so static review tools can apply the same
  filters without opening the SQLite database. This is an additive extension;
  `snapshot.json` `schema_version` remains `1` because no existing field shape
  changed.

The static site reads schema version `2` registry data only. It uses compact
`runs`, `result_rows`, and `result_case_stats` data and does not require source
result directories to exist. It does not read raw payloads,
workspaces, task logs, verifier artifacts, patch files, or model-call logs; it
does not mutate the database or source results; and it does not contact
endpoints. Existing output directories are refused unless `--force` is
provided.

### `benchpack registry bundle`

```text
benchpack registry bundle create --out <bundle-dir> [--provenance <label>] [--force] <result-dir> [<result-dir> ...]
benchpack registry bundle validate <bundle-dir>
benchpack registry bundle import --db <sqlite-db> <bundle-dir> [<bundle-dir> ...]
```

`benchpack registry bundle create` builds a compact directory bundle for
offline public sharing. It reads and validates the supplied result directories
with the same row and optional metadata checks used by registry import, then
writes a new bundle directory containing `benchpack-bundle.json` plus one
`runs/run-NNN-<label>/` directory per input. The bundle manifest schema version
is `1`. The output path must be disjoint from all source result directories:
the runner rejects both "bundle inside source" and "source inside bundle"
layouts before honoring `--force`.

The copied files are limited to compact report-facing artifacts:

- `run.jsonl`;
- optional `hardware.json`;
- optional `run-metadata.json`;
- referenced `patch/.../*.diff` files, so repo-task outcome summaries can
  still distinguish empty and non-empty workspace diffs;
- optional `task/.../*.model-calls.jsonl` files only when every non-empty line
  uses the documented allowlisted safe model-call telemetry shape.

The bundle omits raw request/response payloads, workspaces, normal task logs,
verifier artifacts, and unsafe model-call logs by default. When an omitted
artifact is an existing regular file safely below the result directory, the
manifest records its relative path, omission reason, byte count, and SHA-256.
Workspace directories are omitted without reading their contents. The manifest
does not store canonical local absolute result-directory paths; it stores only
the input directory name as a source label, bundle-relative file paths, file
sizes, hashes, row counts, and the `run.jsonl` hash.

`--provenance` must be one of `self-reported`, `operator-curated`, or
`independently-reproduced`; the default is `self-reported`. The label is
informational but mandatory in the manifest so public review and website
staging can distinguish untrusted self-reports from curated or independently
reproduced evidence.

Bundle creation performs a conservative text secret scan over files it is about
to copy and over the generated manifest. It fails before leaving a partial
bundle when obvious bearer tokens, secret-looking JSON fields, credentialed
URLs, tokenized query strings, or non-UTF-8 text in copied compact artifacts are
detected. This is not a complete public upload trust policy; authenticated
upload, deeper secret scanning, moderation, and object-storage handling remain
later work.

`benchpack registry bundle validate` checks the manifest offline, verifies all
listed file hashes and sizes, revalidates bundled `run.jsonl` rows and optional
metadata, rejects unlisted files, rejects bundled `raw/`, `workspace/`, or
`verify/` files, and applies the same conservative decode and secret scan. It
does not contact endpoints, run packs, import SQLite, mutate benchmark result
directories, or require network access.

`benchpack registry bundle import --db <sqlite-db> <bundle-dir>...` validates
each compact bundle with the same offline manifest, hash, secret-scan, row, and
metadata checks before opening the SQLite database. After all bundle inputs
validate, it imports the bundled `runs/run-NNN-<label>/` directories through
the normal registry indexing path. Registry labels come from the bundle
manifest's original run labels, while the registry identity key is the bundled
run directory path. The command writes only the requested SQLite database. It
does not contact endpoints, run packs, mutate bundle contents, require source
result directories, read omitted raw/workspace/task/verify artifacts, or create
hosted submission state.

## Result Artifacts

Results are easy to inspect and follow a fixed layout per run:

```text
results/
  2026-04-26-m5-mbp-64gb/
    run.jsonl
    summary.md
    hardware.json
    run-metadata.json
    raw/
      case-001.request.json
      case-001.response.json
```

`hardware.json` is the per-run host metadata file described in
`docs/hardware-targets.md`. `run-metadata.json` is present only when
`benchpack run --run-metadata <json-file>` was supplied. It is a small,
human-readable, user-supplied metadata artifact for runtime/server, model, and
operating-condition notes that the runner does not autodiscover. `summary.md`
includes a compact runtime metadata section when the artifact is supplied.
`summary.md`, `hardware.json`, and intentional small `run-metadata.json` files
are committable; `raw/` is generated and ignored by default.

The common `hardware.json` shape includes `hostname`, `platform`, `os`,
`kernel`, `cpu_model`, `cpu_count`, `ram_mb`, and `gpus`. Platform-specific
fields are optional and nullable when unavailable. On Darwin, current optional
fields include `chip`, `hardware_model`, `hardware_model_name`, and
`hardware_model_identifier`; these are host metadata only and do not add runtime
adapter fields or `run.jsonl` row fields.

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
case label. When repo-task rows include `repo_task`, `summary.md` also includes
the same report-only `Repo-Task Outcomes` table used by `benchpack report`.

Generated result directories are ignored by default. Curated `summary.md`,
`hardware.json`, `run-metadata.json`, and small `run.jsonl` files may be
committed only when intentionally force-added for a run-log entry.

## MVP

The first useful version is complete when it can:

1. Run `smoke-chat` against an OpenAI-compatible endpoint.
2. Run `smoke-chat` against Ollama via `/api/generate`.
3. Run a prompt-only coding-agent-shaped case derived from
   `desktop-django-starter`.
4. Write raw request/response artifacts and a summary table.
5. Record hardware and runtime metadata.
6. Run on macOS and a Linux CUDA host without changing benchmark pack contents.
