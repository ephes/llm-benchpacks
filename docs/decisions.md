# Decisions

## D-001: Separate Repository

Keep the benchmark runner in its own repository instead of adding it to
`desktop-django-starter`.

Reason: runtime adapters, hardware profiles, model artifacts, and benchmark
results will churn independently from the Django/Electron starter.

## D-002: Benchmark Packs Are Source

Benchmark packs are versioned source artifacts, not ad hoc command snippets.

Reason: the same workload should be replayable across runtimes, hardware, and
dates. Versioning packs makes result comparisons meaningful.

## D-003: OpenAI-Compatible Adapter First, Native Adapters Where Useful

Support OpenAI-compatible `/v1/chat/completions` early because many runtimes
expose it. Also support native Ollama because it reports useful timing fields.

Reason: forcing all runtimes through one lowest-common-denominator API would hide
important backend metrics.

## D-004: Deterministic Scoring Preferred

Prefer deterministic scoring such as tests passing, schema validity, or exact
artifact checks. Allow LLM-as-judge only when a pack explicitly declares it.

Reason: local model comparisons are noisy enough without making scoring opaque.

## D-005: Hardware Profiles Are First-Class

Every run records hardware and runtime metadata.

Reason: local inference numbers are meaningless without the exact host, memory,
driver, runtime, quantization, and context assumptions.

## D-006: Generated Results Stay Mostly Local

Raw results are generated artifacts. Commit curated summaries and logs, not every
large response file.

Reason: benchmark runs can produce noisy or large artifacts. The repo should stay
usable as source.

## D-007: Python With uv

The first implementation is a Python package managed with `uv`.

Reason: most local LLM tooling (`mlx-lm`, llama.cpp Python bindings, Ollama
clients, vLLM) has first-class Python support, and `uv` gives reproducible
dependency resolution and fast environment setup without committing to a
heavier packaging system this early.

## D-008: TOML For Pack Manifests

Benchpack manifests are TOML files (`benchpack.toml`).

Reason: TOML is human-editable, supports the table and array-of-tables shape that
packs need (cases, scoring), and matches the Python tooling already used by `uv`
and `pyproject.toml`.

## D-009: Pack-Owned Warmup And Repetition Counts

Measured repetition count and warmup count live in pack manifest defaults as
`defaults.repetitions` and `defaults.warmup`, not CLI flags.

Reason: repeated runtime measurements are part of the benchmark workload
contract. Keeping counts in the pack makes runs comparable across hosts and
avoids ad hoc invocation differences. Warmups are excluded from `run.jsonl`,
scoring, and summaries because they are preparation work, not benchmark samples.

## D-010: Validate MLX Through Its OpenAI-Compatible Server First

Use `mlx_lm.server` with the existing `openai-chat` adapter before adding a
dedicated `mlx-lm` CLI or Python adapter.

Reason: `mlx_lm.server` exposes an OpenAI-compatible chat surface, which is the
same runtime boundary already used for `llama-server`, vLLM, LM Studio, and
similar servers. Proving or disproving compatibility there keeps the adapter
surface smaller. Add a dedicated MLX adapter only if server-path validation
shows that the OpenAI-compatible path cannot provide the measurements the
project needs.

## D-011: Compare Existing Result Artifacts First

Make the first comparison command read existing result directories containing
`run.jsonl` instead of executing benchmarks or reading generated `raw/`
artifacts.

Reason: `run.jsonl` is the stable result contract from prior slices. A
read-only compare command gives useful Phase 2 summaries without expanding the
adapter surface, mutating result directories, or depending on ignored raw
payloads. `prefill_tps` must stay hidden or gated until normalized results carry
enough prompt-cache metadata to establish cache parity.

## D-012: Cached Prompt Tokens Live Under `tokens.cached_prompt`

Normalize backend-reported cached prompt-token counts as
`tokens.cached_prompt` in new `run.jsonl` records.

Reason: cached prompt tokens are a token-count property directly tied to
`tokens.prompt` and prefill interpretation. Keeping a single nullable field
under `tokens` makes missing backend support explicit without introducing a
larger cache object before there are multiple normalized cache fields.

## D-013: Compare Prompt/Cache Parity From Normalized Token Medians

`benchpack compare` reports median `tokens.prompt` beside median
`tokens.cached_prompt` and warns when prompt-token medians differ for a case
only when every compared row in that case has a numeric `tokens.prompt` value.
It also reports a deterministic case-level `prefill parity` status with the
priority `missing-case`, `prompt-missing`, `prompt-diff`, `cache-missing`,
`cache-diff`, then `comparable`. Cached-token parity is interpreted only
relative to comparable prompt token counts. The compare table may display
`prefill_tps med`, but only for cases whose `prefill parity` status is
`comparable`; every non-comparable status renders `—` even when timing values
exist in `run.jsonl`.

Reason: cached prompt-token counts are not meaningful in isolation when compared
runs used different prompt token counts. Keeping the rule in compare, based only
on normalized `run.jsonl` token fields, preserves old artifact compatibility
while avoiding prompt/cache inference from ignored raw payloads or timing
fields. Gating prefill speed on the explicit parity status prevents warm-cache,
cold-prefill, and different-prompt timings from being presented as comparable
speed evidence.

## D-014: OpenAI Streaming Usage Compatibility Is Explicit

`benchpack run` exposes `--openai-stream-usage {include,omit}` for
`openai-chat` streaming requests. The default `include` keeps sending
`stream_options.include_usage` so endpoints that support OpenAI streaming usage
chunks can populate token counts and token-rate fields. The `omit` mode still
sends streamed chat completions but leaves out `stream_options`, preserving
streamed output and TTFT for local servers that reject the usage option.

Reason: silently retrying without `stream_options.include_usage` can execute a
benchmark prompt twice and change timing or cache semantics. Making the
request-shape change explicit keeps compatibility visible while preserving null
usage-derived metrics when the endpoint does not report usage.

## D-015: Start Phase 3 With A Prompt-Only Wrap Pack

The first Phase 3 coding-agent-shaped workload is the bundled
`desktop-django-wrap` pack: static chat prompts ask for concise plans to adapt
a server-rendered Django app to run inside Electron. It started with
deterministic scoring limited to a `contains` check for `DDS_WRAP_PLAN`; D-020
records the later narrow tightening to regex-scored fixed labels.

Reason: this gave the runner a portable initial workload surface shaped like
the real `desktop-django-starter` wrap task without adding repo mutation,
agent-session orchestration, patch extraction, verifier scripts, or new scoring
engines before those contracts were ready.

## D-016: Prompt Files Resolve Inside The Pack

Case-level `prompt_file` entries are pack-relative static text files whose
contents are loaded into `Case.prompt` during manifest loading. The loader
rejects absolute paths and any resolved path, including a symlink target, that
escapes the pack directory.

Reason: prompt files are source artifacts that must remain portable across
local laptops, Linux CUDA hosts, and OpenAI-compatible local servers. Loading
file contents into `Case.prompt` keeps adapter request shapes and result records
unchanged while preventing manifests from depending on private local paths.

## D-017: Fixtures Start As Top-Level Pack Metadata

Fixture declarations live as top-level `[[fixtures]]` entries with an id, kind,
pack-relative path, and optional description. The loader validates that fixture
kind values are non-empty strings and fixture paths are relative, exist, point
to a file or directory, do not resolve to the pack directory itself, and remain
inside the pack directory after resolving traversal and symlinks. Loaded `Pack`
objects expose fixture metadata. Later file-fixture prompt assembly is covered
by D-019; fixture declarations themselves still do not imply adapter, scoring,
result record, or repository execution behavior.

Reason: Phase 3 needs a portable source contract for future repo-shaped
workloads before repo-task execution exists. Keeping fixtures as pack-owned
source artifacts establishes path safety without coupling the format to
disposable worktrees, patch extraction, verifier scripts, or repo mutation
before those contracts are ready.

## D-018: Cases Reference Fixtures By Id Only

Case-level `fixture_refs` entries are optional lists of fixture ids declared in
the same pack's top-level `[[fixtures]]` inventory. The loader validates that
refs are strings, match the existing id grammar, are unique within a case, and
point to existing fixture ids. Loaded `Case` objects expose fixture id strings
rather than `Fixture` objects.

Reason: Phase 3 needs to express which static inputs belong to which cases
before execution semantics exist. Id-only refs keep the source contract explicit
without adding repo copying, disposable worktrees, adapter request changes,
result schema changes, verifier scripts, patch extraction, or repository
mutation.

## D-019: Referenced File Fixtures Assemble Into Prompts

When a chat case references a file fixture with `fixture_refs`, the loader reads
that fixture as UTF-8 and appends it to the loaded base prompt in the exact
`fixture_refs` order. The appended text is wrapped in stable plain-text
delimiters that name the fixture id, kind, and pack-relative path. Directory
fixture refs remain valid metadata-only refs and are not read, copied,
executed, or injected into prompts.

Reason: Phase 3 needs deterministic file context in model inputs before
repo-task execution exists. Appending file fixtures keeps the adapter API and
result schema unchanged because adapters still receive a single `Case.prompt`,
while leaving directory snapshots for a future disposable-worktree contract.

## D-020: Regex-Score The Prompt-Only Wrap Output Skeleton

Tighten `desktop-django-wrap` from marker-only `contains` scoring to executable
`regex` scoring over a short fixed output skeleton: `DDS_WRAP_PLAN` first,
followed by `Inspect:`, `Electron shell:`, `Django runtime:`, `Packaging:`, and
`Verification:` in order.

Reason: the prompt-only Phase 3 pack still must not execute, copy, or mutate a
repository, but a single marker check is too weak for short output comparison.
Regex scoring is already part of the manifest vocabulary, so implementing it is
the narrowest deterministic improvement without adding repo-task semantics,
verifier scripts, adapter changes, or result schema changes.

## D-021: Repo-Task Mutation Uses Run-Owned Disposable Workspaces

`repo-task` cases treat pack-owned `kind = "repo"` directory fixtures as
immutable source snapshots. The runner copies exactly one primary repo fixture
into a fresh workspace under the run output directory for each measured
execution before any mutation, rejecting absolute symlinks and symlinks that
resolve outside the source repo fixture before copying. Repository writes, task
execution, patch capture, and verification happen only inside that disposable
workspace and the run output directory. Source fixtures under
`benchpacks/<pack>/fixtures/` are never mutated. Repo-task artifacts such as
workspace metadata, patch diffs, task stdout/stderr logs, verifier output, and
final status are explicit result artifacts separate from raw model
request/response payloads. Measured rows record the prepared workspace metadata
as run-relative path plus source fixture id and manifest-declared source path,
and record the deterministic patch artifact path as
`patch/<case-id>/rep-NNN.diff`. Measured rows also record deterministic task
stdout/stderr log artifact paths as `task/<case-id>/rep-NNN.stdout.log` and
`task/<case-id>/rep-NNN.stderr.log`. The current task phase runs through a
narrow internal task-executor boundary. Current CLI repo-task runs use the
fenced model-output patch bridge by default: it extracts the first fenced
`diff` or `patch` block from adapter output, applies a unified diff or explicit
path-marked replacement block only inside the prepared workspace, and writes
deterministic task stdout/stderr describing success, missing patch content,
unsafe paths, or failed application.
A minimal internal agent-session harness path also exists behind the same
boundary for runner-side callers and tests, without manifest or CLI selection.
Measured rows using
`verify-script` record verifier artifact paths as
`verify/<case-id>/rep-NNN.json`,
`verify/<case-id>/rep-NNN.stdout.log`, and
`verify/<case-id>/rep-NNN.stderr.log`, plus `repo_task.status`,
`repo_task.verify_exit_code`, and top-level `verify-script` scoring from the
verifier process exit code. Verifier subprocesses use the timeout from the
effective `verify-script` scoring table, defaulting to `300.0` seconds when
`scoring.timeout_s` is absent; timeouts keep the same artifact paths, record
`repo_task.status = "failed"`, record `repo_task.verify_exit_code = null`, and
write authoritative timeout metadata into the verifier JSON. Verifier
subprocesses may also receive a manifest-configurable environment overlay from
the effective `verify-script` scoring table's optional `environment` field. The
runner preserves inherited environment behavior when it is absent; when present,
it copies the current runner environment, overlays the manifest string keys and
values, and passes that copy only to the verifier subprocess without adding
environment values to result rows. Production task execution through a full
agent-session harness remains planned; executor choice is not a manifest or CLI
surface.

Reason: repo mutation needs a stronger safety boundary than prompt-only chat
cases. Copying pack-owned fixtures into run-owned workspaces keeps benchmark
source portable and reviewable, prevents accidental fixture corruption, makes
cleanup behavior testable, and gives later verifier, patch, and agent-session
slices a clear artifact contract before implementation hard-codes execution
semantics.

## D-022: Agent-Session Harness Stays Behind The Executor Boundary First

Agent-session harness work uses D-021's internal repo-task executor boundary
and keeps executor choice out of the manifest and CLI. The first narrow
internal harness path is runner-side only: it can receive the prepared
workspace path, case metadata, model output text, the run output directory,
measured repetition, deterministic task log paths, and validated
workspace-relative helpers for listing regular files and directories, checking
file existence, reading or writing UTF-8 text, and deleting files. File
listings are deterministic sorted POSIX workspace-relative paths and include
files created earlier in the same harness invocation. Symlinks to regular files
are listed only when their target resolves inside the prepared workspace.
Directory listings are deterministic sorted POSIX workspace-relative paths,
include nested directories and directories created earlier in the same harness
invocation, and exclude the workspace root, files, and symlinks including
symlinks to directories. Existence checks return true only for existing regular
files, including in-workspace symlinks to regular files. File deletes use the
same path boundary, return true after deleting an existing regular file or
in-workspace symlink-to-file workspace entry, return false for missing paths
and directories, and unlink symlink entries without deleting their targets.
Unsafe delete paths and delete `OSError`s are runner failures before task logs
are written. Future production
harnesses may add pack metadata and model/adapter/endpoint/default context as
needed for harness-owned model calls. The harness may inspect and mutate only
the prepared workspace and may write only the existing task logs under the run
output directory. It must not mutate pack-owned fixtures, prompts, verifier
scripts, source docs, or public adapter/result schemas by default. Task logs,
patch capture after task execution, verifier execution after patch capture, and
existing workspace, patch, task, verify, repo_task, and scoring row shapes stay
unchanged until a later implementation proves a narrower schema change is
necessary.

Reason: the executor boundary now exists, but harness selection, task
environment, task timeout, retention, and richer status semantics are still
unsettled. Keeping the first harness internal lets implementation validate the
runner responsibilities without expanding the public pack format or result
schema prematurely.

## D-023: Public Repo-Task Harness Selection Must Be Explicit

Public repo-task harness selection uses an explicit case-local manifest table,
shaped as `harness = { id = "..." }` on `repo-task` cases. `fenced-patch`
routes to the existing fenced model-output `diff`/`patch` executor, and
`external-agent` routes to a runner-owned subprocess argv per D-026. When the
field is absent, current compatibility behavior remains the same fenced
executor. Selection must not be
inferred from model names, adapters, endpoints, fixture shape, verifier choice,
host environment, or pack id. The manifest loader rejects `harness` on
non-`repo-task` cases, unknown ids, missing or non-string ids, non-table
`harness` values, and unsupported keys beyond the currently implemented `id`
and `timeout_s`. Public harness selection does not change
normal adapter request/result schemas, raw request/response paths, result row
shapes, or task log artifact paths. Task logs remain
`task/<case-id>/rep-NNN.stdout.log` and
`task/<case-id>/rep-NNN.stderr.log`. Patch capture still happens after the
selected task phase, verifier execution still happens after patch capture,
repo-task warmups remain rejected, and this narrow implementation adds no
result row fields. Full production external coding-agent integration, task
environment, workspace retention, richer status/reporting, and pack-level
harness defaults remain future work.

Reason: public harness selection crosses manifest compatibility, executor
dispatch, task logs, status reporting, timeout and environment policy,
workspace retention, and external coding-agent integration. The first public
ids prove the boundary while preserving current result compatibility until
adjacent contracts are designed and tested.

## D-024: External Harness Contract Is Public And Task Timeouts Stay Narrow

Future production external repo-task harnesses are public harnesses selected by
explicit case-local `harness.id` values. The runner must not infer an external
harness from model names, adapters, endpoints, fixture shape, verifier choice,
host environment, or pack id. The implemented public ids are now
`fenced-patch` and `external-agent`; D-026 records the runner-owned argv policy
for the first public external subprocess slice. Normal adapter request/result
schemas stay unchanged by default; if future harnesses own model calls, those
calls are runner/harness concerns rather than normal adapter request fields.
External harnesses may mutate only the prepared workspace and write only allowed
run-output artifacts.
Pack-owned fixtures, prompts, verifier scripts, source docs, and raw model
artifacts remain immutable or runner-owned. Existing task stdout/stderr paths,
raw paths, result row shapes, patch capture after task execution, verifier
execution after patch capture, repo-task warmup rejection, and source fixture
immutability remain unchanged.

Task timeout support is deliberately narrow and lives on the case-local harness
table as `harness.timeout_s`. It must be a positive TOML integer or float and
is accepted only for `repo-task` harness declarations. It bounds
subprocess-backed task executors: for `fenced-patch`, the `git apply --check`
and `git apply` calls. The fenced executor tries the `--recount` apply path
first so otherwise valid model-generated diffs with inaccurate hunk counts are
applied as complete hunks, then falls back to standard `git apply` behavior
when recount preflight rejects a diff; for `external-agent`, the configured
subprocess process group.
A fenced-patch preflight timeout is a task outcome because the workspace is
known unchanged: the runner writes deterministic task stderr and continues to
patch capture and verification. A timeout during actual patch application after
successful preflight is a runner failure because partial workspace mutation
cannot be ruled out. Internal in-process agent-session harness callables reject
`task_timeout_s` because Python cannot safely preempt arbitrary callable
execution. This slice adds no manifest task commands, task environment support,
workspace retention options, pack-level harness defaults, or new adapter/result
fields.

Reason: production external harness integration needs bounded execution before
it is safe to run, but the external harness process, model-call, environment,
retention, and status-reporting policies are still future work. Keeping timeout
case-local and tied to the selected harness avoids broad task configuration
while preserving existing artifacts and result compatibility.

## D-025: Runtime Metadata Is User-Supplied Sibling Artifact

Runtime, model, and operating-condition metadata for a benchmark run is captured
through explicit user input, `benchpack run --run-metadata <json-file>`, and
persisted as `run-metadata.json` beside `hardware.json`. The file is a
permissive JSON object: known optional sections such as `runtime`, `model`, and
`operating_conditions` are objects when present, and `notes` is a string when
present. The reporter may include the artifact in `summary.md` and
`benchpack report`, but the metadata is not duplicated into each `run.jsonl`
row. `benchpack compare` remains independent of this artifact.

Reason: server command, runtime version, model checksum, quantization, context
and cache options, power state, thermal state, and background load are
environment-specific across Ollama, MLX, llama.cpp, OpenAI-compatible local
servers, and CUDA hosts. Capturing them as user-supplied metadata reduces
manual run-log prose without introducing unreliable runtime autodiscovery,
adapter schema changes, benchmark semantic changes, or median/parity behavior
changes.

## D-026: Public external-agent Uses Runner-Owned JSON Argv

The first public `external-agent` repo-task harness is selected explicitly with
`harness = { id = "external-agent" }` on `repo-task` cases, but its subprocess
argv is runner-owned configuration, not manifest syntax. `benchpack run` reads
`BENCHPACK_EXTERNAL_AGENT_ARGV` only when the loaded pack contains an
`external-agent` case. The value must be a JSON array of non-empty strings
without NUL bytes; plain command strings and shell parsing are rejected. The CLI
routes public `external-agent` cases to `ExternalProcessHarness`, which appends
the prepared workspace, case id, output directory, and repetition arguments,
runs without a shell, and writes through the existing task stdout/stderr log
artifacts. Missing or malformed argv fails before output directory creation and
before adapter calls. D-027 extends this invocation with a runner-owned
`--context <path>` JSON input while keeping the argv source and shell-free
execution policy unchanged.

Reason: accepting the public harness id is useful only if the runner can execute
a real subprocess, but manifest command blobs, task environments, shell
expansion, secrets handling, and CLI task-command flags would widen the source
contract too early. A single runner-owned JSON argv keeps execution explicit,
testable, shell-free, and outside adapter/result schemas while preserving
current patch capture, verifier ordering, task log paths, and `run.jsonl`
shape.

## D-027: External-agent Context Is Runner-Owned JSON Input

Public `external-agent` subprocesses receive `--context <path>` in addition to
the existing workspace, case, output directory, and repetition arguments. The
path points to a deterministic runner-generated JSON file under
`task/<case-id>/rep-NNN.context.json` in the run output directory. The context
is versioned from the start with `version = 1` and carries only explicit
non-secret runner context: pack id/version/description, case id/kind/loaded
prompt/fixture refs/harness id and timeout, prepared workspace path and source
fixture metadata, run output directory, repetition, task stdout/stderr paths,
optional persisted `run-metadata.json` path, selected adapter id/model/user
endpoint argument/effective defaults, and pack fixture inventory using
manifest-declared relative fixture paths.

The context file is harness input, not result data. It is not duplicated into
`run.jsonl`, does not change adapter request/result schemas, does not add
normal adapter `raw/` artifacts for harness-owned calls, and does not expose
environment variables or credentials.

Reason: real external agents need more than scalar argv values to act on a
repo-task, but adding manifest command syntax, task environment tables, secret
injection, or result schema fields would widen the public contract too early.
A runner-owned JSON input file keeps the handoff explicit, inspectable,
language-neutral, shell-free, and compatible with the existing task artifact
layout.

## D-028: External-agent Model-Call Log Path Is Optional Harness Artifact

Public `external-agent` subprocess contexts expose
`run.model_call_log_path`, a deterministic absolute path under the run output
directory at `task/<case-id>/rep-NNN.model-calls.jsonl`. External harnesses
that own model calls may write JSONL telemetry there. The runner owns and
exposes the path but does not require the file to exist, pre-create it,
validate its JSONL schema, parse it into summaries or reports, add it to
`run.jsonl`, or mirror harness-owned calls into normal adapter `raw/`
request/response artifacts.

The recommended, non-enforced JSONL line shape is one JSON object per
harness-owned model call, with this minimal core:

```json
{"schema_version":1,"sequence":1,"model":"test-model","ok":true}
```

`schema_version` is currently integer `1`, `sequence` is the positive call
sequence within the external-agent task phase, `model` is the model identifier
when known, and `ok` indicates whether the call completed successfully.
Harnesses may add safe optional timing, adapter/endpoint label, token count, or
short error fields. The recommended default shape should not include full
prompts, full responses, request bodies, headers, environment variables, API
keys, bearer tokens, or credentials.

Reason: real external agents need a stable place to put model-call telemetry
without changing normal adapter, raw artifact, result, compare, or report
contracts. Keeping the file under the existing task artifact area makes the
handoff deterministic and inspectable while preserving optionality for fake
agents and early integrations. Recommending a tiny object shape gives harness
authors a portable starting point without committing the runner to validation,
normalization, summaries, or result schema fields before real harnesses prove
what should be standardized.

## D-029: Local Result Registry Starts As SQLite Artifact Index

The first result-registry implementation is a local SQLite index created by
`benchpack registry import --db <sqlite> <result-dir>...`. Existing result
directories remain canonical evidence. The importer validates normalized
`run.jsonl` rows plus optional `hardware.json` and `run-metadata.json`, records
the current schema version, and stores compact run, row, and case-stat metadata
for local querying.
It writes only the requested SQLite database and does not mutate benchmark
outputs, read `raw/`, inspect workspaces or task artifacts, generate reports,
contact endpoints, or create public submission bundles.

SQLite is the initial storage backend for offline indexing. Re-importing the
same result directory updates the run row and replaces its child rows, using the
canonical local result directory path as the identity key. The first schema
stores enough normalized fields for local filtering over pack/version, case,
adapter, model, endpoint, host/runtime/model metadata, timing/token metrics,
scoring, and repo-task verifier state. Schema version `2` adds nullable
comparability anchors from explicit run metadata plus per-run/case prompt/cache
coverage medians so future views can show artifact/runtime mode, pack version,
prompt-token, and cache-token caveats without parsing every source artifact.
Schema version `3` adds `agent_wrap_runs` for curated hard one-shot
Django/Electron wrapping rows whose comparison metadata is useful but whose
historical artifacts do not all arrive as ordinary `run.jsonl` benchpack
results. Those rows are imported idempotently by stable label and queried from
SQLite by status, harness, provider, model, and thinking level.
The first registry-backed report slice adds
`benchpack registry report --db <sqlite>`, which reconstructs report inputs
from indexed `raw_json` rows plus stored hardware and run-metadata JSON. It
reuses the existing report renderer for medians, warnings, cache rows, and
`prefill parity`, while omitting artifact-only model-call summaries and treating
patch byte counts as unknown when only registry data is available.
The first static local site slice adds
`benchpack registry site --db <sqlite> --out <site-dir>`, which writes
`index.html` and `report.md` from indexed compact registry rows. It reuses
registry report selection and rendering, adds dense run and case-metric tables
from `runs` and `result_case_stats`, and remains read-only over the database
and source artifacts. Public upload, deeper secret scanning, object storage for
large artifacts, hosted databases, and richer comparison-explorer views remain
later explicit slices.
The first received-bundle ingestion slice adds
`benchpack registry bundle import --db <sqlite> <bundle-dir>...`, which
validates compact public bundles offline before writing SQLite rows, then
indexes the bundled compact run directories through the same registry import
path while preserving original run labels from the bundle manifest.
The first local query slice adds
`benchpack registry query --db <sqlite>`, which returns JSON arrays from
normalized `runs` and `result_rows` columns with exact indexed filters. It is
read-only, does not require source result directories or artifact files, and
does not create hosted API, upload, review, or leaderboard policy.

Reason: a local registry is useful for searching and grouping accumulated
benchmark artifacts, but replacing the artifact-first workflow would weaken
provenance too early. SQLite keeps the first index portable and testable without
introducing hosted infrastructure, submission trust policy, or broad privacy
surface before import semantics are stable.

## D-030: Public Result Bundles Are Compact, Directory-Based, And Validated Offline

The first public-sharing export is a directory bundle created by
`benchpack registry bundle create --out <bundle-dir> <result-dir>...` and
validated by `benchpack registry bundle validate <bundle-dir>`. The bundle
copies only compact report-facing artifacts: `run.jsonl`, optional
`hardware.json`, optional `run-metadata.json`, patch diffs referenced by result
rows, and safe external-agent model-call JSONL logs when every non-empty line
uses the allowlisted telemetry shape. It omits raw payloads, workspaces, normal
task logs, verifier artifacts, and unsafe model-call logs by default while
recording hashes and byte counts for omitted regular files when available.

Bundles carry a required provenance label:
`self-reported`, `operator-curated`, or `independently-reproduced`. The bundle
manifest stores bundle-relative paths and source directory names, not canonical
local absolute result-directory paths. Creation and validation apply a
conservative text secret scan and fail on obvious bearer tokens, credentialed
URLs, tokenized query strings, secret-looking JSON fields, or non-UTF-8 copied
compact artifacts. Bundle output paths must be disjoint from source result
directories so `--force` cannot delete source evidence.

Validated bundles can be indexed offline with
`benchpack registry bundle import --db <sqlite> <bundle-dir>...`. That command
first applies the same bundle validation, including manifest, hash, role/path,
row, metadata, unlisted-file, UTF-8, and conservative secret-scan checks. It
then imports only the bundled compact run directories into the local SQLite
registry. It does not mutate the bundle, require the original source result
directories, read omitted artifacts, contact endpoints, or implement hosted
upload/review state.

Reason: directory bundles are easy to inspect, diff, validate, and test without
network access or hosted infrastructure. Keeping the export compact avoids
turning public sharing into a raw-artifact leak, while hashes preserve useful
provenance for omitted files. This is still not a full community upload policy:
moderation, deeper secret scanning, size limits, duplicate detection, object
storage, and website ingestion remain explicit later slices.

## D-031: Fenced Repo-Task Replacement Blocks Must Be Explicitly Path-Marked

The default fenced repo-task executor continues to prefer unified diffs in the
first fenced `diff` or `patch` block. It also accepts a narrow full-file
replacement fallback when the block starts with
`*** Begin File: <repo-relative-path>` and ends with `*** End File`. The runner
writes only the explicitly named UTF-8 file, after applying the same
workspace-relative path boundary used by harness helpers. Replacement content
is LF-canonicalized before it is written, matching the runner's existing text
diff normalization. Unsafe paths, missing markers, empty content, directory
targets, and write failures are task outcomes: the workspace is left unchanged,
deterministic task stderr is written, patch capture still runs, and the
verifier can classify the result.

The `endpoint-python-correctness` pack uses this fallback in version `0.2.0`
because the first local endpoint validation showed a model that produced
plausible replacement-file content but not an applicable unified diff. The
fallback is not inferred from arbitrary code in a fence and does not change
external-agent direct-edit behavior, adapter schemas, raw artifacts,
`run.jsonl`, or compare/report semantics.

Reason: accepting unmarked replacement content would make the runner guess
which file a model intended to edit and would weaken workspace safety. A
path-marked block is still simple enough for endpoint-only models while keeping
mutation explicit, deterministic, and verifier-driven.

## D-032: Hosted Registry Should Be A SQLite-First Django Service, Not Static-Only

The preferred hosted registry direction is a Django service in this repository,
deployed through a reusable `ops-library` role and a thin `ops-control`
playbook. The service should support curated compact bundle ingestion,
validation, quarantine/review state, operator approval, public read-only browse
views, and JSON APIs for approved compact data.

Start the hosted service with SQLite for app state, following the deployed
`nyxmon` pattern: uv-managed Django source sync, migrations on deploy, a
persistent database file outside destructive sync paths, Granian/systemd, and
Traefik. Keep a PostgreSQL migration path open, but do not require Postgres for
the first staging service.

The existing static `benchpack registry site` export remains a local/offline
review tool and possible temporary read-only publication fallback. It is not the
target architecture once hosted ingestion/review work starts.

Use Django rather than Wagtail for the first dynamic service. The benchmark
registry needs upload handling, auth, admin/review workflows, migrations, and
structured APIs more than CMS editing. Do not embed the service in the homepage
Wagtail app; homepage and Nyxmon are only references for local command and
deployment mechanics.

The web app should have a clean `llm-benchpacks` project layout with a local
Django dev server, migrations, tests, and ignored runtime state. It should
import reusable validation and registry helpers from `benchpack` rather than
making the CLI the core integration boundary.

Users should be able to self-register and submit compact benchmark bundles
after email verification. Transactional email is therefore part of the first
hosted product surface: account verification, password reset, submission
receipt, validation failure, approval, and rejection notifications. Local
development should use Django's console email backend, tests should use the
in-memory email backend, and neither should require real SMTP/API credentials.
Staging/production email credentials and sender settings belong in
`ops-control` secrets.

For web submission, the existing directory-style CLI bundle should be treated as
the validation format, not necessarily the browser upload shape. Users can
submit an archive that preserves the compact bundle directory contents. SQLite
JSON/text fields should be the default persistence layer for uploaded compact
payloads, validation results, hashes, row summaries, and review state. The
filesystem should be used only for temporary extraction during validation or for
retained upload archives if an explicit audit/retention policy later requires
that.

Reason: result submission and review are application behavior, not just
deployment plumbing. `ops-library` already provides the right style of Traefik,
systemd, uv, and SQLite-backed Django deployment primitives, while
`ops-control` should remain private configuration. Django gives the fastest path
to robust operator-facing review and public APIs without hand-building an admin
surface. SQLite is enough for the early operator-curated write pattern and
avoids adding a database service before public submission volume exists.

## D-033: One-Shot Agent Wrap Results Live In llm-benchpacks

Keep the hard one-shot Django/Electron agent wrapping runner and new generated
artifacts in this repository under `scripts/run-agent-wrap-oneshot` and
`results/agent-wrap-oneshot/`. Keep `desktop-django-starter` as the source of
the wrap prompt, skill, docs, and reference Electron shell, not the long-term
benchmark lab.

Reason: the starter repository owns the workload being exercised, while
benchmark orchestration, model/provider metadata, run logs, and generated result
artifacts churn with benchmark campaigns. The old
`desktop-django-starter/.bench-qwen36/` path is retained only as historical
scratch from the Qwen3.6 campaign.

## D-034: PriceRunner Data Lacks Price And Image Signals

The PriceRunner Product Classification and Clustering dataset (Kaggle
`lakritidis/product-clustering-matching-classification`, UCI 837) is text-only:
its sole columns are product title, merchant id, and category id/label, plus the
cluster id/label. It carries no price and no image fields, and neither can be
recovered — they are absent at the source, not dropped by
`build-fixture-from-pricerunner.py`.

Because price (same-product offers cluster tightly; large gaps are strong
negative evidence) and images (visual disambiguation of variants) are central
signals for realistic product matching, this Kaggle dataset is not suitable as
the basis for a multi-signal product-matching benchmark. The existing
`product-offer-matching` pack remains valid only as a title-only entity-matching
lane and must be labeled as such; a price- and image-bearing dataset is required
for any multimodal or price-aware lane.

Reason: keep the limitation explicit so the title-only fixture is not mistaken
for a faithful product-matching benchmark, and so future work scopes a richer
dataset rather than extending text-only PriceRunner data.

## D-035: Filter GTIN/EAN Out Of The Product-Matching Benchmark

Structured catalog identifiers — GTIN, EAN, and any reliable MPN *field* — are
removed from the offer data the matcher sees before a product-matching benchmark
runs. When a reliable identifier is present, matching collapses to a `GROUP BY
identifier` lookup rather than an entity-resolution problem, so leaving it in
lets a matcher shortcut the answer and measures nothing about resolution.

The rule applies to structured fields only. In-title model tokens that an
extractor (e.g. longest-common-substring over normalized titles) recovers from
noisy merchant titles are kept — they are the matching challenge, not a shortcut.
GTIN/EAN may still be used verifier-side during fixture building as a label-noise
cross-check (flagging offers whose GTIN disagrees with the reliable cluster key),
and are then stripped from the published offers. GTIN is never a gold label; the
cluster key is the reliable product id, which merchant feeds frequently get
wrong. Any identifier-only lookup ceiling, if wanted, lives in a separate and
clearly labeled baseline lane, never in the matching lanes.

Reason: a reliable identifier trivializes matching, so the benchmark must test
resolution from noisier signals. Documented in the methodology knowledge base
(`benchmarks/product-offer-matching/methodology/signals.md`,
`benchmark-constraints.md`, `data-quality.md`).

## D-036: Tiered Fixture — Real Quality Set, Amplified Scale Set

Quality/difficulty metrics (B-cubed, pairwise cluster F1, average precision) are
measured on a real scraped offer set; system metrics (offers per second, peak
RSS, blocking behaviour at scale) are measured on a much larger amplified set
derived from it. The two lanes have different size requirements and must not be
conflated.

Evidence from the billiger.de pilot at 10,825 offers / 1,485 clusters: a
deliberately simple title-only baseline (brand+category blocking, title-token
Jaccard, union-find) tops out at B-cubed F1 ≈ 0.41 and pairwise F1 ≈ 0.12 —
*failing* both pass thresholds (0.70 / 0.20). So the quality lane is already hard
and discriminating at ~10k, with large headroom for price/image/embedding
signals. But the system-metric terms *saturate* at this size: an isolated
clusterer run uses peak RSS ≈ 50 MB so `min(1024/rss_mb, 1)` = 1.000, and
~12–13k offers/s (above the 10,000 cap) so `min(offers_per_second/10000, 1)` =
1.000. That makes 15% of
the combined score
(0.10 throughput + 0.05 memory) dead weight at 10k — it returns 1.000 for every
implementation and discriminates nothing.

Therefore: keep the real set for quality (optionally deepened toward ~30–50k by
saturating dense product families, not by adding breadth), and measure system
metrics on a deterministic, block-structure-preserving amplification of the real
offers to 100k–1M rows. Do not brute-scrape to 1M — the supply of *popular*
products is shallow and the long tail adds singletons and noise, not signal.
Report the lanes separately and never average a saturated system term into a
small-scale quality comparison.

Reason: throughput and memory are scale-dependent and meaningless at 10k, while
matching quality is already hard there; sizing both lanes the same either wastes
an enormous scrape or reports saturated, non-discriminating system numbers. The
baseline lives at `benchpacks/product-offer-matching/scripts/baseline-clusterer.py`
and the finding is recorded in `dataset-sourcing-analysis.md`; it belongs in the
methodology `benchmark-constraints.md` resourcing/constraints notes.

## D-037: Billiger Replaces PriceRunner As The Product-Offer-Matching Pack

The runnable `product-offer-matching` pack uses the billiger.de-derived fixture
(`fixtures/billiger-matcher-repo`, cases `cluster-billiger-{python,rust}`) instead
of the title-only PriceRunner fixture. The PriceRunner lane is removed from the
live pack but preserved in git history and under `results/`. The verifier
(`verify/score_clusters.py`) is reused unchanged; only the data, hidden labels,
cases, prompts, and docs differ.

Reason: PriceRunner is text-only (no price or images — D-034), while the benchmark
should test multi-signal product matching. Billiger adds price and image signals
on a harder, denser fixture (decision D-036), so it supersedes PriceRunner as the
primary lane. Prompts are lightly guided so the benchmark measures programming
ability, not entity-resolution recall.

## D-038: Strip image_url From The Published Offers (It Is A Cluster-Id Proxy)

`image_url` is removed from the published `train_offers`/`test_offers` the matcher
sees. The billiger scrape only captured the **canonical product image** (one image
per variant/product page), copied to every offer in that cluster, so `image_url`
is constant within a gold cluster and unique across clusters (~99.7% / 100%
measured). Clustering by `image_url` therefore recovers the gold labels almost
exactly — a `GROUP BY image_url` shortcut, not entity resolution. It stays in the
raw scrape for provenance but is filtered out at fixture-build time.

This is the same class of leak as a reliable identifier (GTIN, D-035). Images are
only a legitimate matching signal as **real per-merchant photos**, which differ by
shop; we do not have those, so no image signal ships until we do.

Evidence: GPT-5.5 (under both the `pi` and `codex` tool-using harnesses)
independently found and exploited the shortcut, scoring ~0.999 B-cubed F1
(combined ~98–100). Opus 4.8 did honest title/attribute matching and scored ~0.51,
which is the representative result for the leak-free fixture.

Reason: a fixture-artifact identifier trivializes the task and rewards shortcut
discovery over matching; stripping it restores the intended multi-signal
(title/price/brand/category) difficulty.
