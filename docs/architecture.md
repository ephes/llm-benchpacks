# Architecture

## Components

`benchpack` should be a small CLI with six internal concepts:

- **Pack**: versioned workload definition, including static fixture metadata
  when a pack declares pack-local fixture files or directories.
- **Case**: one request or task inside a pack, optionally linked to top-level
  fixtures by id. For chat cases, `Case.prompt` is the final prompt after any
  referenced file fixtures have been appended.
- **Adapter**: runtime-specific request/response bridge.
- **Collector**: hardware, timing, and process/GPU metrics.
- **Reporter**: JSONL artifacts plus human-readable summaries and small
  runner-owned sibling artifacts.
- **Compare/report utilities**: read-only reporting over existing `run.jsonl`
  result directories plus optional per-run `hardware.json` and
  `run-metadata.json` files.
- **Local registry tools**: SQLite-backed indexing plus compact public bundle
  creation/validation over existing result directories. They validate
  normalized rows, record compact metadata, and leave benchmark outputs as the
  canonical evidence.

Repo-task execution adds responsibilities around the existing concepts rather
than changing the adapter boundary:

- **Workspace preparer**: implemented runner-owned responsibility that copies
  one declared `kind = "repo"` directory fixture into a run-owned disposable
  workspace for each measured repo-task execution.
- **Task executor or agent harness**: runner-side component that applies model
  or agent actions inside the prepared workspace. The current CLI default
  applies the first fenced `diff` or `patch` block from model output as either
  a unified diff or an explicitly marked full-file replacement block. A
  repo-task case may now explicitly declare
  `harness = { id = "fenced-patch" }` to select that same public compatibility
  executor, or `harness = { id = "external-agent" }` to route the task phase to
  a runner-owned subprocess argv loaded from `BENCHPACK_EXTERNAL_AGENT_ARGV`;
  absence keeps the same fenced-patch default. `harness.timeout_s` is an
  optional case-local task phase timeout for subprocess-backed task executors. A minimal
  internal agent-session
  harness path also exists behind this boundary for runner-side callers and
  tests, without manifest or CLI selection. Its runner-side request carries the
  prepared workspace path, case metadata, model output text, the run output
  directory, measured
  repetition, deterministic task log paths, and validated workspace-relative
  helpers for listing regular files and directories, checking file existence,
  reading or writing UTF-8 text, and deleting files; richer future harnesses
  may add pack metadata and model/adapter/endpoint/default context needed for
  harness-owned model calls.
  The harness may inspect and mutate only the prepared workspace and may write
  only the existing task logs under the run output directory; it must preserve
  pack fixtures, prompts, verifier scripts, and source docs. The implemented
  public manifest harness ids are `fenced-patch` and `external-agent`; unknown
  ids and harness declarations on non-`repo-task` cases are rejected. The
  external-agent subprocess slice stays behind this same boundary: richer
  runner-owned context such as pack metadata, prompt text, run metadata, and
  model/adapter/endpoint/defaults is passed through an explicit generated JSON
  context file, not as adapter schema fields. That context also exposes an
  optional runner-owned model-call JSONL artifact path for harness-owned model
  calls, without requiring the file or adding it to `run.jsonl`; when present,
  only allowlisted safe telemetry fields are summarized. Full external
  coding-agent harness production integration, task environment, retention,
  richer status/reporting, and pack-level harness defaults remain future work.
- **Verifier**: deterministic checker for measured repo-task outcomes, currently
  implemented for `verify-script`.
- **Artifact recorder**: reporter-side responsibility for explicit repo-task
  artifacts such as workspace metadata, patch diffs, execution logs, verifier
  output, and final status.

## Proposed Layout

```text
benchpacks/
  smoke-chat/
  runtime-sweep/
  desktop-django-wrap/
  patch-from-failure/
  endpoint-python-correctness/
  python-regression-fix/
  django-dashboard-regression-fix/
src/
  benchpack/
    cli.py
    adapters/
      ollama_generate.py
      openai_chat.py
    packs.py
    results.py
    run_metadata.py
    compare.py
    report.py
    registry.py
    hardware.py
docs/
  specification.md
  architecture.md
  implementation-plan.md
  benchpack-format.md
  hardware-targets.md
  decisions.md
  spec-log.md
  run-log.md
results/
  .gitkeep
```

## Execution Flow

1. Load a benchmark pack and select cases.
2. Validate declared fixture metadata, pack-relative fixture paths, and any
   case-level fixture refs against the pack's top-level fixture ids. Referenced
   file fixtures are read as UTF-8 and appended to the loaded case prompt in
   `fixture_refs` order with stable delimiters. Referenced directory fixtures,
   including static repo snapshots used by chat cases, remain metadata-only and
   are not copied, executed, injected, mutated, or attached to adapter requests.
3. If any loaded case explicitly selects `harness.id = "external-agent"`, load
   and validate `BENCHPACK_EXTERNAL_AGENT_ARGV` as a JSON array of non-empty
   strings without NUL bytes before run output directory creation or adapter
   calls.
4. Load runtime adapter configuration.
5. Optionally load and validate a user-supplied runtime metadata JSON object
   when `--run-metadata` is provided. This is explicit user input, not runtime
   autodiscovery.
6. Capture host metadata.
7. For each non-repo-task case, run pack-requested warmup executions first.
   Packs with `repo-task` cases and `defaults.warmup > 0` are rejected before
   execution in this slice.
8. For `repo-task` measured executions only, validate that the case references
   exactly one `kind = "repo"` directory fixture, copy it to
   `workspace/<case-id>/rep-NNN/` under the run output directory. Repo-task
   warmups are rejected for now.
9. Execute the pack-requested measured repetitions, streaming when supported.
   Runner-level adapter compatibility options, such as the `openai-chat`
   streaming usage mode, are merged into a per-request defaults copy so the
   loaded pack defaults are not mutated.
10. Persist raw requests and responses for warmups and measured executions.
11. For measured `repo-task` executions only, invoke the internal task executor
   boundary. Current CLI runs use the default executor, or the same executor
   when the case explicitly declares `harness = { id = "fenced-patch" }`. That
   executor extracts the first fenced `diff` or `patch` block from model output,
   applies it as a unified diff or an explicit
   `*** Begin File: <repo-relative-path>` replacement block in the prepared
   workspace, and writes deterministic task stdout/stderr logs. Missing or
   unapplicable patches and invalid replacement blocks are logged and do not
   crash the benchmark row. If the case declares `harness.timeout_s`, the
   fenced executor passes that timeout to both `git apply --check` and
   `git apply` for unified diff blocks. A preflight timeout leaves the
   workspace unchanged and is logged as a task outcome; an apply timeout after
   preflight is a runner failure because partial mutation cannot be ruled out.
   When the case declares `harness = { id = "external-agent" }`, the CLI passes
   the preloaded runner-owned subprocess argv to `ExternalProcessHarness`, which
   writes `task/<case-id>/rep-NNN.context.json` as runner-owned harness input,
   exposes optional model-call telemetry at
   `task/<case-id>/rep-NNN.model-calls.jsonl` through that context, appends
   workspace, case, output directory, repetition, and context-path arguments,
   runs without a shell, captures existing task logs, and treats clean nonzero
   exits or process-group-cleaned timeouts as task outcomes.
   Runner-side code can
   supply an internal agent-session harness behind this same boundary without
   changing the adapter request shape or public result row shape by default, but
   direct internal harness callables reject `task_timeout_s`.
12. Apply implemented deterministic scoring for measured executions when the
   pack declares it. For measured `repo-task` executions with
   `scoring.mode = "verify-script"`, the runner executes the verifier after
   patch capture and before recording the result row, using any verifier-only
   environment overlay declared in the effective scoring table.
13. Normalize metrics, resources, and scoring into `run.jsonl` for measured
   executions. Measured repo-task records also include the prepared workspace
   metadata needed to locate the run-owned copy, the run-relative patch
   artifact path, task log artifact paths, verifier artifact paths, and final
   verifier status when `verify-script` is used.
14. Write `hardware.json`, optional `run-metadata.json`, and `summary.md`.
    `run-metadata.json` is intentionally a sibling artifact rather than a
    repeated per-row field so compare medians and row contracts remain focused
    on measured execution data.

Adapters still receive a loaded prompt and return the existing result envelope.
Workspace, patch paths, and user-supplied runtime metadata are not passed to
adapters.

## Repo-Task Flow

Current `repo-task` execution inserts workspace preparation after pack loading
and before each measured adapter execution:

1. The pack loader validates fixture declarations and refs only. It does not
   copy directories, choose workspace paths, execute verifiers, or mutate
   source fixtures.
2. The runner identifies the case's single primary `kind = "repo"` directory
   fixture and creates a fresh run-owned workspace under the output directory.
3. The workspace preparer rejects absolute symlinks and symlinks escaping the
   source repo fixture, then copies the source fixture into that workspace. The
   pack-owned fixture remains read-only by contract and must not be mutated.
4. The adapter continues to handle model/runtime calls. The adapter boundary
   remains unchanged; adapters do not receive workspace paths, learn pack
   fixture semantics, or write repository files directly.
5. After the adapter call, the runner invokes the internal task executor
   boundary. The default CLI executor extracts the first fenced code block
   whose info string is exactly `diff` or `patch` from
   `AdapterResult.output_text`. The block body is treated as a unified diff or
   an explicitly path-marked full-file replacement and applied from the
   prepared workspace root. Non-matching fences are ignored. Missing blocks,
   rejected or unapplicable diffs, and invalid replacement blocks are
   deterministic task stderr outcomes, not runner crashes. `harness.timeout_s`,
   when present, bounds the fenced executor subprocess calls for unified diff
   application. A `git apply --check` timeout leaves the workspace unchanged and
   is logged in task stderr. A timeout during the actual `git apply` after
   preflight is a runner failure because the workspace state may be partial.
6. For `harness = { id = "external-agent" }`, the CLI routes the task phase to
   the runner-owned external subprocess harness. The argv comes from
   `BENCHPACK_EXTERNAL_AGENT_ARGV`, not from the manifest. The runner appends
   `--workspace`, `--case`, `--output-dir`, `--repetition`, and `--context`
   pointing at `task/<case-id>/rep-NNN.context.json`, runs without a shell in
   the prepared workspace, and captures stdout/stderr to the existing task
   logs. The context JSON includes pack/case metadata, the loaded prompt,
   fixture inventory, prepared workspace and task-log paths, optional
   `run-metadata.json` path, optional model-call JSONL path, and selected
   adapter/model/endpoint/defaults. If `openai-chat` auth is configured, those
   defaults may include the configured environment variable name, but never the
   bearer token value. When `harness.timeout_s` is set, the
   subprocess starts in a POSIX process group/session; on timeout, the runner
   terminates that process group, waits a short bounded grace period, escalates
   to a kill signal when needed, and then writes the existing task logs.
7. An internal agent-session harness can occupy the same runner-owned task
   phase when supplied by runner-side code. It receives the prepared workspace
   path, case metadata, model output text, output directory, repetition, and
   task log paths, plus validated workspace-relative helpers for listing
   regular files and directories, checking file existence, reading or writing
   UTF-8 text, and deleting files.
   File listings are deterministic sorted POSIX workspace-relative paths and
   observe files created earlier in the same harness invocation. Symlinks to
   regular files are listed only when their target resolves inside the prepared
   workspace. Directory listings are deterministic sorted POSIX
   workspace-relative paths, include nested directories, exclude the workspace
   root, files, and symlinks including symlinks to directories, and observe
   directories created earlier in the same harness invocation. Existence checks
   return true only for regular files, including in-workspace symlinks to
   regular files, and false for missing paths or directories. Delete checks use
   the same boundary, return true after deleting an existing regular file or
   in-workspace symlink-to-file workspace entry, return false for missing paths
   and directories, and unlink symlink entries without deleting their targets.
   Future harnesses may also receive pack metadata and
   model/adapter/endpoint/default context as needed. It may inspect and mutate
   only the prepared workspace and may write only the existing task logs under
   the run output directory. It must not mutate pack-owned fixtures, prompts,
   verifier scripts, source docs, or adapter/result schemas by default. The
   task log paths in step 7 remain stable for future harnesses unless a later
   result-schema slice changes them deliberately. Harness failures that prevent
   the runner from writing required artifacts, including unsafe or unreadable
   workspace helper paths, unsafe deletes, delete `OSError`s, or failed
   workspace listing, remain runner failures;
   ordinary task outcomes should be captured through the existing task logs
   until a later status-reporting slice proves a new row field is necessary.
   Direct internal harness callables cannot be combined with task timeout,
   because in-process Python callables cannot be safely preempted.
8. The task phase writes `task/<case-id>/rep-NNN.stdout.log` and
   `task/<case-id>/rep-NNN.stderr.log` artifacts. Successful application writes
   a short stdout message and leaves stderr empty; no-patch or failed-apply
   outcomes leave the workspace unchanged and explain the outcome in stderr.
   External-agent subprocess output is captured verbatim through these same
   stdout/stderr task logs.
9. After task executor completion, the runner compares the immutable
   source fixture to the prepared workspace with a deterministic directory
   snapshot diff and writes `patch/<case-id>/rep-NNN.diff` beside `raw/`. Empty
   changes still create an empty patch file.
10. For measured repo-task executions with `scoring.mode = "verify-script"`, the
   verifier consumes the prepared workspace, case metadata, pack metadata,
   source fixture id, patch artifact path, and requested output path as
   command-line arguments. It returns deterministic status through its process
   exit code and may write structured JSON. The runner enforces the effective
   `verify-script` scoring timeout, defaulting to `300.0` seconds when
   `scoring.timeout_s` is absent. If the effective scoring table declares
   `environment`, the runner overlays those string entries onto a copy of the
   runner environment for the verifier subprocess; when it is absent, the
   subprocess inherits the environment as before. The runner captures verifier
   stdout/stderr as explicit artifacts and corrects or creates the structured
   JSON so `exit_code` and `passed` match the process result or timeout
   outcome.
11. The reporter records normalized workspace metadata, `patch.path`, `task`,
   `verify`, `repo_task`, and top-level `scoring` for measured repo-task
   `verify-script` rows.
12. Cleanup is still planned. Retaining `workspace/` for debugging should be an
   explicit option; otherwise large workspaces and logs should stay out of
   curated commits.

Repo-task artifacts live beside, not inside, `raw/`. The `raw/` directory
remains for model request/response payloads. Current repo-task artifacts are
`workspace/`, `patch/<case-id>/rep-NNN.diff`,
`task/<case-id>/rep-NNN.{stdout.log,stderr.log}`, public external-agent
`task/<case-id>/rep-NNN.context.json` context inputs, optional public
external-agent `task/<case-id>/rep-NNN.model-calls.jsonl` model-call logs, and
`verify/<case-id>/rep-NNN.{json,stdout.log,stderr.log}`. Task logs now describe
the executor-owned task phase: the default fenced unified-diff or explicit
replacement-file extraction/application phase for default CLI runs, the public
external-agent subprocess phase, or an internal harness phase when runner-side
code supplies one. A later full agent harness may replace or extend that phase
without changing the adapter or reporter boundaries.

Public harness selection is a manifest-format concern, not an adapter concern.
The implemented public shape is an explicit `harness = { id = "..." }` table on
`repo-task` cases, optionally with `timeout_s`:
`harness = { id = "fenced-patch", timeout_s = 5 }` or
`harness = { id = "external-agent", timeout_s = 120 }`. `fenced-patch`
preserves the current compatibility behavior by routing to the existing fenced
`diff`/`patch` executor. When the field is absent, the same fenced executor
remains the default. `external-agent` routes to a runner-owned subprocess argv
loaded from `BENCHPACK_EXTERNAL_AGENT_ARGV`. Selection is not inferred from
model names, adapters, endpoints, fixture shape, verifier choice, host
environment, or pack id. Unknown ids are rejected by the manifest loader and
again at the task-executor boundary if they somehow reach it.

This selection leaves adapter request/result schemas, raw request/response
paths, task log paths, patch capture after the task phase, verifier execution
after patch capture, and existing measured row shapes unchanged. Normal adapter
schemas remain unchanged by default; the generated external-agent context file
is harness input and is not duplicated into `run.jsonl`; the optional
model-call JSONL path exposed through that context is not required,
pre-created, or added to `run.jsonl`. When present, allowlisted safe telemetry
is summarized in `summary.md` and `benchpack report`. Harness-owned model
calls are runner/harness concerns rather than normal adapter request fields.
The recommended JSONL line shape starts with
`{"schema_version":1,"sequence":1,"model":"test-model","ok":true}`, but the
runner validates only safe summary fields from that file. External harnesses
may mutate only the prepared workspace and write only allowed run-output
artifacts.
Pack-owned fixtures, prompts, verifier scripts, source docs, and raw model
artifacts remain immutable or runner-owned. Task
environment, retention, richer task status/reporting, pack-level harness
defaults, full production external coding-agent integration, and repo-task warmups
remain separate future design and implementation slices.

The external-agent invocation is still a runner-side task phase, not a manifest
command runner. The public subprocess argv receives explicit runner-owned
arguments for prepared workspace, case id, output directory, repetition, and
`--context <path>`. That JSON context is versioned and contains pack metadata,
loaded prompt text, fixture/source-repo metadata, selected harness options,
optional run metadata path, selected model, adapter id, endpoint argument,
defaults, compatibility options, and an optional
`task/<case-id>/rep-NNN.model-calls.jsonl` path as explicit harness input. That
optional JSONL file is a harness-owned artifact when written; it is not
required, pre-created, or added to `run.jsonl`. The runner validates only the
recommended safe telemetry fields for aggregate summaries and counts invalid
or unsafe lines without echoing their payloads. The recommended JSONL shape
uses one object per model call with `schema_version`, `sequence`, `model`, and
`ok` as the minimal fields and optional timing/token/error fields when safe.
The default shape should not contain full prompts, full responses, request
bodies, headers, environment variables, API keys, bearer tokens, or
credentials. Those calls do not become
normal adapter calls, do not change adapter envelopes, do not add `run.jsonl`
fields, and do not write normal `raw/` artifacts unless a later schema slice
defines that mapping.

External harness process failures divide the same way as current task execution.
Unsafe paths, unwritable required logs, inability to stop a subprocess process
group, or failure to preserve the workspace/output boundary are runner failures.
A harness that exits nonzero, times out after the runner has stopped its
process group and closed logs, or
leaves a workspace that fails verification is a task outcome represented by the
existing task logs, patch artifact, verifier artifacts, `repo_task` verifier
status, and top-level scoring. `harness.timeout_s` remains a task-phase timeout,
not a verifier timeout and not an adapter request timeout.

Measured repo-task `verify-script` result rows contain workspace metadata,
patch artifact metadata, task log metadata, verifier artifact metadata, final
repo-task verifier status, and `verify-script` scoring. Repo-task rows using
prompt-output scoring still omit `verify` and `repo_task`, and current chat
cases do not use this flow. Verifier environment configuration stays on the
execution side of the boundary: it is not added to adapter requests, normalized
result rows, or reporter-owned repo-task objects.

`summary.md` and `benchpack report` derive a report-only repo-task outcome
table from those existing fields plus the patch artifact size. The table makes
empty workspace diffs and mutation-visible failures visible without changing
the `run.jsonl` schema. The current labels are `passed`,
`failed-no-mutation`, `failed-with-mutation`, and
`failed-unknown-mutation`.

## Result Record Envelope

Each line of `run.jsonl` is a result record. The record is the union of three
contributions — adapter, collector, and reporter — with a clear split of
responsibility so that adapter code never needs to read the pack manifest,
sample host resources, or compute derived metrics.

### Adapter return payload

The runtime adapter returns only fields the backend can supply directly:

- `adapter`, `endpoint`, `model`, `ok`
- `timing.wall_s`, `timing.ttft_s`, `timing.prefill_tps`, `timing.decode_tps`
- `tokens.prompt`, `tokens.output`, `tokens.cached_prompt`
- `raw.request_path`, `raw.response_path`
- optional `backend` table for backend-specific fields the adapter wants to
  preserve verbatim

`tokens.cached_prompt` is the backend-reported count of prompt tokens served
from prompt cache when the adapter can identify an equivalent field. It is
`null` when unavailable. The initial source is OpenAI-compatible
`usage.prompt_tokens_details.cached_tokens`; Ollama native timing fields are not
treated as cache counts.

`endpoint` is the resolved URL the adapter actually called (after appending
`/v1/chat/completions`, `/api/generate`, etc. to the user's `--endpoint`
argument).  It is recorded so result records remain unambiguous when the same
adapter/model points at different local servers.

Transport-only adapter configuration is not part of the adapter result
payload. For example, `openai-chat` may receive an explicit auth environment
variable name through adapter defaults and send a bearer token in HTTP headers,
but the resolved token value is not written to `run.jsonl`, raw request bodies,
summaries, task logs, run metadata, reports, or external-agent context.

### Collector sample

The collector samples host and process resources during the run. All fields
are best-effort: missing values are written as `null` rather than blocking the
run.

- `resources.memory_mb` — peak RSS of the runtime process when observable
- `resources.gpu_memory_mb` — peak GPU memory in MB when a GPU is present
- optional `resources.backend` for backend-specific samples (powermetrics on
  macOS, `nvidia-smi` on Linux)

### Reporter additions

The reporter wraps the adapter payload and collector sample before writing them
to `run.jsonl`:

- `pack.id`, `pack.version` — copied from the loaded manifest
- `case` — the case id from the manifest
- `repetition` — a 1-based integer only when the pack requests more than one
  measured repetition
- `workspace` — present only for measured `repo-task` records, with
  `path`, `source_fixture_id`, and `source_path`
- `patch` — present only for measured `repo-task` records, with `path`
- `task` — present only for measured `repo-task` records, with `stdout_path`
  and `stderr_path`
- `verify` — present only for measured `repo-task` records using
  `verify-script`, with `path`, `stdout_path`, and `stderr_path`
- `repo_task` — present only for measured `repo-task` records using
  `verify-script`, with `status` and `verify_exit_code`
- `timing.total_tps` — derived as `tokens.output / timing.wall_s`
- `scoring` — the result of the configured scoring mode (see
  `docs/benchpack-format.md`); `null` when mode is `none` or absent. Current
  executable modes are `contains` substring checks and `regex` checks using
  Python `re.search` with the pack-provided pattern. For measured repo-task
  `verify-script` rows, the runner sets scoring from the verifier exit code.

Adapters do not produce or read these fields. The reporter is also where pack
id/version get attached for cross-run comparison.

Warmup executions are runner/reporter concerns. They call the same adapter and
write raw artifacts under `raw/`, but they do not produce result records and are
not scored.

User-supplied run metadata is a sibling artifact, not a record contribution.
When provided, the runner writes `run-metadata.json` beside `hardware.json`.
The object may describe runtime/server name and version, server command,
runtime options, model id/source/quantization/checksum, and operating
conditions such as power, thermal, and background load. It is not passed to
adapters and is not duplicated into measured rows.

The repo-task `workspace` object is deliberately narrow:
`workspace.path` is relative to the run output directory and uses
`workspace/<case-id>/rep-NNN`; `workspace.source_fixture_id` is the referenced
repo fixture id; and `workspace.source_path` is the pack manifest fixture path.
Chat records do not include `workspace`, even when they reference repo
directory fixtures as metadata.

The repo-task `patch` object is also deliberately narrow: `patch.path` is
relative to the run output directory and uses `patch/<case-id>/rep-NNN.diff`.
The patch file is written for every measured repo-task execution, including
no-change executions where the file is empty. Chat records do not include
`patch`, even when they reference repo directory fixtures as metadata.

The repo-task `task` object is deliberately narrow:
`task.stdout_path` and `task.stderr_path` are relative to the run output
directory and use `task/<case-id>/rep-NNN.stdout.log` and
`task/<case-id>/rep-NNN.stderr.log`. The log files are written for every
measured repo-task execution. They record only the current internal executor
phase: fenced unified-diff or explicit replacement-file application for current
CLI runs, or an internal harness phase when supplied by runner-side code. Chat
records do not include `task`, even when they reference repo directory fixtures
as metadata.

The repo-task `verify` object is deliberately narrow: `verify.path`,
`verify.stdout_path`, and `verify.stderr_path` are relative to the run output
directory and use `verify/<case-id>/rep-NNN.json`,
`verify/<case-id>/rep-NNN.stdout.log`, and
`verify/<case-id>/rep-NNN.stderr.log`. Chat records do not include `verify`.

The repo-task `repo_task` object is deliberately narrow:
`repo_task.status` is `"passed"` when the verifier exit code is `0` and
`"failed"` for any nonzero exit code or verifier timeout.
`repo_task.verify_exit_code` records the integer process exit code, or `null`
when the verifier timed out and no exit code exists. Chat records do not
include `repo_task`.

### Combined record

```json
{
  "pack": { "id": "smoke-chat", "version": "0.1.0" },
  "case": "capital",
  "adapter": "ollama-generate",
  "endpoint": "http://localhost:11434/api/generate",
  "model": "qwen3-coder",
  "ok": true,
  "timing": {
    "wall_s": 4.21,
    "ttft_s": 0.48,
    "prefill_tps": 950.0,
    "decode_tps": 42.0,
    "total_tps": 45.6
  },
  "tokens": { "prompt": 32768, "output": 192, "cached_prompt": null },
  "resources": {
    "memory_mb": 6234,
    "gpu_memory_mb": 14820
  },
  "scoring": {
    "mode": "contains",
    "passed": true
  },
  "raw": {
    "request_path": "raw/case-001.request.json",
    "response_path": "raw/case-001.response.json"
  }
}
```

## Hardware Metadata

Host metadata should be best-effort and never block a run unless the user requests
strict mode.

On macOS:

- `sysctl`, including CPU, memory, and hardware model identifiers when
  available
- `system_profiler SPHardwareDataType` for Apple chip/model fallback metadata
- `system_profiler SPDisplaysDataType` for GPU model names
- `powermetrics` only when explicitly enabled

On Linux:

- `lscpu`
- `free`
- `nvidia-smi` when available
- `/etc/os-release`

## Compare Flow

`benchpack compare` is intentionally outside the execution flow. It does not
load adapters, collect hardware, execute packs, write result artifacts, or read
ignored `raw/` files. It reads each input directory's `run.jsonl`, preserves the
record dictionaries as loaded, groups by case and input run, and renders a
stdout-only table of median wall time, TTFT, decode TPS, total TPS, and output
tokens. It also reports median numeric `tokens.prompt`, median numeric
`tokens.cached_prompt`, and cache metadata coverage, expressed as numeric
cached-token rows over total rows, for each case/run group. It computes median
numeric `timing.prefill_tps` but renders that median only when the case-level
`prefill parity` status is `comparable`.

The compare utility warns when pack ids or versions differ. The `prefill_tps
med` column is gated because prefill comparisons require explicit prompt-cache
parity: non-comparable cases render `—` even when `timing.prefill_tps` values
exist in `run.jsonl`. New rows may carry `tokens.prompt` and
`tokens.cached_prompt`, but old rows may lack one or both fields and missing
values do not prove parity. Cache warnings are derived only from normalized
`run.jsonl` rows: compare warns when cache metadata is incomplete for a case,
when prompt-token medians differ across compared runs for a case with complete
numeric `tokens.prompt` coverage, and when complete cached prompt-token medians
differ. Prompt-token coverage is used as a warning gate but is not rendered as a
separate coverage column. It also computes one case-level `prefill parity`
status from the same summaries and repeats it on every run row for that case.
The status priority is `missing-case`, `prompt-missing`, `prompt-diff`,
`cache-missing`, `cache-diff`, then `comparable`, so cache parity is considered
only after case and prompt parity hold. Missing case/run groups suppress
prompt-token and cached-token median mismatch warnings for that case. Compare
does not read `raw/` files or infer prompt/cache state from timing or prompt
shape.

## Report Flow

`benchpack report` is also outside the execution flow. It reads existing result
directories, loads `run.jsonl` through the same loader as compare, optionally
reads sibling `hardware.json`, `run-metadata.json`, and optional external-agent
model-call JSONL artifacts under `task/`, and writes Markdown to stdout only.
Missing `hardware.json`, `run-metadata.json`, or model-call logs is tolerated
because older or pulled-back compare inputs may contain only `run.jsonl`.

When invoked with `--set <manifest.toml>`, the report command first loads a
small source TOML report-set manifest with `version = 1` and `result_dirs =
[...]`, resolves relative entries against the manifest file's parent directory,
and passes those paths to the same result-directory loader used by positional
report inputs. This is only a read-only input expansion step. The manifest
loader does not execute packs, start runtimes, contact remote hosts, copy
results, write report artifacts, inspect `raw/`, or alter compare/report
summarization.

The report renderer is intended for run-log and comparison-note assembly. It
summarizes input paths, pack id/version, adapter/model/endpoint values, hardware
identity when available, user-supplied runtime/model/operating metadata when
available, external-agent model-call aggregate telemetry when optional logs are
present, repo-task outcome summaries when `repo_task` rows exist, row and `ok`
counts, and scoring pass/fail/unscored counts. Malformed `run-metadata.json`
fails clearly because the report is being asked to interpret that artifact.
Malformed or unsafe model-call JSONL lines are counted as invalid and their
payloads are not echoed. Repo-task outcome summaries resolve patch artifact
paths only under the result directory and treat missing or unsafe patch paths as
unknown mutation state. Its compare-median section reuses the compare
summarization, prompt/cache warning, and prefill-parity helpers so the report
cannot silently disagree with `benchpack compare` on median values, cache rows,
warnings, or `prefill parity` status. It does not load adapters,
collect hardware, execute packs, read `raw/`, write result artifacts, mutate
result directories, or alter
the result schema. Compare remains independent of `run-metadata.json`.

## Registry Import Flow

`benchpack registry import --db <sqlite> <result-dir>...` is outside the
benchmark execution flow and outside report generation. It loads existing
result directories through the same `run.jsonl` loader used by compare/report,
then applies a stricter indexing validation over normalized row fields before
writing SQLite rows. Optional `hardware.json` and `run-metadata.json` are read
only when present; malformed optional metadata fails clearly because the
registry is being asked to index it.

The local registry is currently schema version `2`. The `runs` table stores one
row per canonical result directory path, import timestamp, row count,
`run.jsonl` SHA-256, compact JSON lists for pack ids/versions, adapters,
models, and endpoints, optional hardware/run-metadata JSON, and selected host,
runtime, model, and comparability-anchor metadata columns. Those anchors come
only from explicit `run-metadata.json` fields such as `comparison_mode`,
runtime options, model artifact repo/file/revision/checksum, quantization, host
repo commit, and operating-condition notes; the registry does not infer
artifact parity or cache parity from missing metadata. Host identity columns
are split by source: `host_hostname` and `host_platform` come from
`hardware.json`, while run-label and repo-commit host filters come from
`run-metadata.json`. The `result_rows` table stores one row per
measured `run.jsonl` record with normalized pack/case/repetition, adapter,
model, endpoint, `ok`, timing metrics, token metrics, scoring state, repo-task
verifier status, and compact sort-keyed JSON re-encoding of the normalized row.
The `result_case_stats` table stores one row per run/pack-version/case with
row counts, ok counts, prompt-token coverage and median, cached-prompt-token
coverage and median, and prefill-TPS coverage and median. Re-importing the
same result directory updates the run row and replaces its child rows and case
stats.

The importer writes only the configured SQLite database. It does not execute
packs, load adapters, start runtimes, collect hardware, contact endpoints, read
`raw/`, inspect workspace/task/patch/verify/model-call artifacts, write result
artifacts, mutate result directories, generate reports, perform SSH, or create
public submission bundles.

`benchpack registry report --db <sqlite>` is a read-only report path over that
SQLite snapshot. It reconstructs `ResultRun` inputs from `result_rows.raw_json`
and the stored `runs.hardware_json` / `runs.run_metadata_json` columns, then
passes them through the same report and compare summarization helpers used by
directory-backed `benchpack report`. This keeps median, cache-warning, and
`prefill parity` semantics aligned without requiring the original result
directories to exist. Optional `--run-id` and `--label` selectors only choose
which imported runs to render; they do not mutate the database or source
artifacts. Since the registry does not store patch bytes or model-call log
contents, registry-backed reports omit external-agent model-call summaries and
show repo-task patch byte counts as unknown unless a normal directory-backed
report is used.

`benchpack registry site --db <sqlite> --out <site-dir>` is the first static
view over a local registry snapshot. It uses the same indexed compact rows as
registry-backed reports, writes only `index.html` and `report.md`, and can use
the same optional `--run-id` or `--label` selectors. The generated `index.html`
contains local run and case-metric tables plus an embedded copy of the Markdown
report; `report.md` is produced by the existing report renderer. The site
export does not require source result directories, read raw/workspace/task/
verify artifacts, inspect patch or model-call files, mutate the database, or
contact endpoints. Existing output paths are refused unless `--force` is
explicit.

`benchpack registry bundle create --out <bundle-dir> <result-dir>...` is a
separate export path over existing result directories, not over the SQLite
database. It copies only compact report-facing files into a new directory:
`run.jsonl`, optional `hardware.json`, optional `run-metadata.json`, referenced
patch diffs, and safe model-call JSONL logs when every non-empty line matches
the allowlisted telemetry shape. Raw payloads, workspaces, normal task logs,
verifier artifacts, and unsafe model-call logs are omitted by default; file
omissions include hashes and byte counts when the omitted artifact is an
existing regular file below the source result directory. Bundle manifests store
bundle-relative paths and source directory names, not canonical local absolute
paths. Bundle output paths must be disjoint from source result directories so
`--force` cannot delete source evidence. `benchpack registry bundle validate
<bundle-dir>` verifies the manifest, file hashes, row and metadata shape,
absence of unlisted files, expected role/path shapes, UTF-8 decodability for
copied compact artifacts, and a conservative secret scan entirely offline.
Authenticated upload review, deeper secret scanning, object storage for large
artifacts, and comparison-explorer views remain later components.

`benchpack registry bundle import --db <sqlite> <bundle-dir>...` is the local
offline ingestion path for received compact bundles. It validates every bundle
with the same manifest, file-hash, role/path, row, optional metadata, unlisted
file, UTF-8, and conservative secret-scan checks before opening SQLite. When
all inputs validate, it imports the bundled `runs/run-NNN-<label>/` directories
through the same registry indexing path used for source result directories.
The imported registry label comes from the bundle manifest's original run
label; the idempotency key remains the bundled compact run directory path. The
command does not mutate bundle contents, require source result directories,
read omitted raw/workspace/task/verify artifacts, contact endpoints, or create
hosted review state.

## Operational Helper Flow

`scripts/benchpack-tmux-matrix` is an operator convenience wrapper, not a new
runner component. It assembles existing `uv run benchpack run ...` invocations
for a pack matrix, injects the same user-supplied `--run-metadata` file into
each command, optionally passes through the `--openai-api-key-env` environment
variable name for authenticated `openai-chat` endpoints, and optionally starts
one tmux session with deterministic pack windows. It does not read token
values. The tmux windows are gated so the benchmark commands run sequentially
instead of contending for one local runtime. Failures are propagated through a
tmux session environment marker so already-created downstream windows wake up
and report that they were skipped rather than waiting indefinitely. Its dry-run
path prints the assembled `benchpack run` and tmux commands without launching
tmux or contacting an endpoint.

The helper's default pack list remains the standard four-pack matrix. Named
pack sets are explicit operator shortcuts, currently including
`--pack-set coding-tasks` for `patch-from-failure`, `python-regression-fix`,
and `django-dashboard-regression-fix`, and
`--pack-set coding-tasks-external-agent` for the three explicit external-agent
variants of those workloads. The external-agent set is a separate opt-in path;
it does not change the default four-pack matrix or the fenced-patch
`coding-tasks` expansion. In launch mode, that external-agent set requires
`BENCHPACK_EXTERNAL_AGENT_ARGV` in the helper process environment and injects
that value into the tmux windows because an already-running tmux server may not
inherit newly exported environment variables. Dry runs name the requirement but
do not print the value. Named pack sets cannot be combined with positional
custom packs.

The helper preserves the existing execution boundary: `benchpack run` still
loads packs, adapters, hardware metadata, run metadata, and result writers.
The helper does not probe runtimes, discover model paths, inspect servers,
write results directly, read generated payloads, run compare/report, or change
adapter, result, pack, compare, or report semantics. It also does not pass
`--force` unless the operator explicitly requests that flag. In launch mode it
checks that the supplied metadata file exists before creating tmux windows.

## Spec And Log Management

The repository should use lightweight, reviewable text files rather than a heavy
project-management system:

- `docs/specification.md` is the current contract.
- `docs/decisions.md` records durable architectural decisions.
- `docs/spec-log.md` records dated spec changes and open questions.
- `docs/run-log.md` records curated benchmark runs with links to result folders.
- `results/*` is generated and ignored by default, except for the tracked
  `results/.gitkeep`. Curated `summary.md`, `hardware.json`, small
  `run-metadata.json`, and small `run.jsonl` files under `results/` may be
  committed only when intentionally force-added for a run-log entry.

This keeps the spec close to the code while avoiding generated-result churn in
normal commits.
