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
- **Reporter**: JSONL artifacts plus human-readable summaries.
- **Compare utility**: read-only reporting over existing `run.jsonl` result
  directories.

Repo-task execution adds responsibilities around the existing concepts rather
than changing the adapter boundary:

- **Workspace preparer**: implemented runner-owned responsibility that copies
  one declared `kind = "repo"` directory fixture into a run-owned disposable
  workspace for each measured repo-task execution.
- **Task executor or agent harness**: runner-side component that applies model
  or agent actions inside the prepared workspace. The current CLI default
  applies only the first fenced `diff` or `patch` block from model output as a
  unified diff. A minimal internal agent-session harness path also exists
  behind this boundary for runner-side callers and tests, without manifest or
  CLI selection. Its runner-side request carries the prepared workspace path,
  case metadata, model output text, the run output directory, measured
  repetition, deterministic task log paths, and validated workspace-relative
  UTF-8 text read/write helpers; richer future harnesses may add pack metadata
  and model/adapter/endpoint/default context needed for harness-owned model
  calls. The harness may inspect and mutate only the prepared workspace and may
  write only the existing task logs under the run output directory; it must
  preserve pack fixtures, prompts, verifier scripts, and source docs. Harness
  selection and configuration are not manifest or CLI surfaces yet.
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
src/
  benchpack/
    cli.py
    adapters/
      ollama_generate.py
      openai_chat.py
    packs.py
    results.py
    compare.py
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
3. Load runtime adapter configuration.
4. Capture host metadata.
5. For each non-repo-task case, run pack-requested warmup executions first.
   Packs with `repo-task` cases and `defaults.warmup > 0` are rejected before
   execution in this slice.
6. For `repo-task` measured executions only, validate that the case references
   exactly one `kind = "repo"` directory fixture, copy it to
   `workspace/<case-id>/rep-NNN/` under the run output directory. Repo-task
   warmups are rejected for now.
7. Execute the pack-requested measured repetitions, streaming when supported.
   Runner-level adapter compatibility options, such as the `openai-chat`
   streaming usage mode, are merged into a per-request defaults copy so the
   loaded pack defaults are not mutated.
8. Persist raw requests and responses for warmups and measured executions.
9. For measured `repo-task` executions only, invoke the internal task executor
   boundary. Current CLI runs use the default executor, which extracts the
   first fenced `diff` or `patch` block from model output, applies it as a
   unified diff in the prepared workspace, and writes deterministic task
   stdout/stderr logs. Missing or unapplicable patches are logged and do not
   crash the benchmark row. Runner-side code can supply an internal
   agent-session harness behind this same boundary without changing the adapter
   request shape or public result row shape by default.
10. Apply implemented deterministic scoring for measured executions when the
   pack declares it. For measured `repo-task` executions with
   `scoring.mode = "verify-script"`, the runner executes the verifier after
   patch capture and before recording the result row, using any verifier-only
   environment overlay declared in the effective scoring table.
11. Normalize metrics, resources, and scoring into `run.jsonl` for measured
   executions. Measured repo-task records also include the prepared workspace
   metadata needed to locate the run-owned copy, the run-relative patch
   artifact path, task log artifact paths, verifier artifact paths, and final
   verifier status when `verify-script` is used.
12. Write `summary.md`.

Adapters still receive a loaded prompt and return the existing result envelope.
Workspace and patch paths are not passed to adapters.

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
   `AdapterResult.output_text`. The block body is treated as a unified diff and
   applied from the prepared workspace root. Non-matching fences are ignored.
   Missing blocks and rejected or unapplicable diffs are deterministic task
   stderr outcomes, not runner crashes.
6. An internal agent-session harness can occupy the same runner-owned task
   phase when supplied by runner-side code. It receives the prepared workspace
   path, case metadata, model output text, output directory, repetition, and
   task log paths, plus validated workspace-relative UTF-8 text read/write
   helpers. Future harnesses may also receive pack metadata and
   model/adapter/endpoint/default context as needed. It may inspect and mutate
   only the prepared workspace and may write only the existing task logs under
   the run output directory. It must not mutate pack-owned fixtures, prompts,
   verifier scripts, source docs, or adapter/result schemas by default. The task
   log paths in step 7 remain stable for future harnesses unless a later
   result-schema slice changes them deliberately. Harness failures that prevent
   the runner from writing required artifacts, including unsafe or unreadable
   workspace helper paths, remain runner failures; ordinary task outcomes should
   be captured through the existing task logs until a later status-reporting
   slice proves a new row field is necessary.
7. The task phase writes `task/<case-id>/rep-NNN.stdout.log` and
   `task/<case-id>/rep-NNN.stderr.log` artifacts. Successful application writes
   a short stdout message and leaves stderr empty; no-patch or failed-apply
   outcomes leave the workspace unchanged and explain the outcome in stderr.
8. After task executor completion, the runner compares the immutable
   source fixture to the prepared workspace with a deterministic directory
   snapshot diff and writes `patch/<case-id>/rep-NNN.diff` beside `raw/`. Empty
   changes still create an empty patch file.
9. For measured repo-task executions with `scoring.mode = "verify-script"`, the
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
10. The reporter records normalized workspace metadata, `patch.path`, `task`,
   `verify`, `repo_task`, and top-level `scoring` for measured repo-task
   `verify-script` rows.
11. Cleanup is still planned. Retaining `workspace/` for debugging should be an
   explicit option; otherwise large workspaces and logs should stay out of
   curated commits.

Repo-task artifacts live beside, not inside, `raw/`. The `raw/` directory
remains for model request/response payloads. Current repo-task artifacts are
`workspace/`, `patch/<case-id>/rep-NNN.diff`,
`task/<case-id>/rep-NNN.{stdout.log,stderr.log}`, and
`verify/<case-id>/rep-NNN.{json,stdout.log,stderr.log}`. Task logs now describe
the executor-owned task phase: the default fenced unified-diff
extraction/application phase for current CLI runs, or an internal harness phase
when runner-side code supplies one. A later full agent harness may replace or
extend that phase without changing the adapter or reporter boundaries.

Measured repo-task `verify-script` result rows contain workspace metadata,
patch artifact metadata, task log metadata, verifier artifact metadata, final
repo-task verifier status, and `verify-script` scoring. Repo-task rows using
prompt-output scoring still omit `verify` and `repo_task`, and current chat
cases do not use this flow. Verifier environment configuration stays on the
execution side of the boundary: it is not added to adapter requests, normalized
result rows, or reporter-owned repo-task objects.

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
phase: fenced unified-diff patch application for current CLI runs, or an
internal harness phase when supplied by runner-side code. Chat records do not
include `task`, even when they reference repo directory fixtures as metadata.

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

- `sysctl`
- `system_profiler`
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

## Spec And Log Management

The repository should use lightweight, reviewable text files rather than a heavy
project-management system:

- `docs/specification.md` is the current contract.
- `docs/decisions.md` records durable architectural decisions.
- `docs/spec-log.md` records dated spec changes and open questions.
- `docs/run-log.md` records curated benchmark runs with links to result folders.
- `results/*/raw/` is generated and ignored by default; curated `summary.md`,
  `hardware.json`, and small `run.jsonl` files under `results/` may be
  committed.

This keeps the spec close to the code while avoiding generated-result churn in
normal commits.
