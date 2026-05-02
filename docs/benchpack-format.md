# Benchpack Format

This is the initial manifest sketch. The schema can change until the first
release.

## Example

```toml
[pack]
id = "smoke-chat"
version = "0.1.0"
description = "Tiny endpoint smoke test"

[defaults]
temperature = 0
max_tokens = 64
stream = true
warmup = 0
repetitions = 1

[[cases]]
id = "capital"
kind = "chat"
prompt = "What is the capital of France? Answer in one sentence."
fixture_refs = ["synthetic-context"]

[[fixtures]]
id = "synthetic-context"
kind = "context"
path = "fixtures/context.md"
description = "Portable synthetic context for future tasks"

[scoring]
mode = "contains"
expected = "Paris"
```

## Fields

`pack.id`
: Stable pack identifier used in result records. Must match the id grammar below.

`pack.version`
: Version of the workload. Change it when prompts, fixtures, fixture
  references, or scoring change.

`defaults`
: Request defaults shared by cases.

`defaults.stream`
: When true, adapters that support streaming may use a streaming request path.
  `openai-chat` honors this flag by requesting streamed chat completions and
  measuring TTFT from the first non-empty content delta. When false or absent,
  `openai-chat` keeps the non-streaming request shape. The example above is a
  schema example; individual packs such as `smoke-chat` may leave streaming off
  to preserve non-streaming smoke coverage.

`defaults.warmup`
: Number of unrecorded warmup executions per case. It defaults to `0` when
  absent and must be a non-negative integer. Warmups use the same adapter,
  endpoint, model, prompt, and defaults as measured executions, write raw
  request/response files under `raw/<case>.warmup-NNN.*.json`, and are excluded
  from `run.jsonl`, scoring, and `summary.md`.

`defaults.repetitions`
: Number of measured executions per case. It defaults to `1` when absent and
  must be a positive integer. Each measured execution writes one `run.jsonl`
  record. Packs with `repetitions = 1` use legacy raw file names
  `raw/<case>.request.json` and `raw/<case>.response.json`. Packs with
  `repetitions > 1` use `raw/<case>.rep-NNN.request.json` and
  `raw/<case>.rep-NNN.response.json`, and each record includes a 1-based
  top-level `repetition` field owned by the reporter.

`cases`
: Ordered benchmark cases. Each case `id` must match the id grammar below and
  must be unique within the pack.

`cases[].prompt`
: Inline prompt text for a case. Inline prompts remain supported for compact
  smoke and runtime-measurement cases.

`cases[].prompt_file`
: Pack-relative path to a UTF-8 prompt file, for example
  `prompt_file = "prompts/wrap-plan-small.md"`. A case must define exactly one
  prompt source: either `prompt` or `prompt_file`, never both and never neither.
  Prompt files are resolved relative to the pack directory, must not be absolute
  paths, and must resolve inside the pack directory after following symlinks.
  The runner rejects paths that escape the pack directory through `..` traversal
  or symlinks. Loaded file contents become the case prompt at manifest-load time,
  so adapters and result records do not distinguish inline prompts from prompt
  files.

`cases[].fixture_refs`
: Optional list of fixture ids declared in the same pack's top-level
  `[[fixtures]]` inventory. It defaults to an empty list when absent. When
  present, it must be a TOML array of strings; every ref must match the id
  grammar, must point to an existing top-level fixture id in the same pack, and
  must not appear more than once in the same case. Referenced file fixtures are
  appended to the loaded case prompt in `fixture_refs` order with stable
  delimiters. Referenced directory fixtures remain metadata-only. Fixture refs
  do not execute fixtures, mutate repositories, template prompts, change
  adapter request or result schemas, extract patches, or run verifiers. The one
  current exception is `repo-task`: each measured execution copies exactly one
  referenced `kind = "repo"` directory fixture into a run-owned disposable
  workspace under the output directory and captures a deterministic patch from
  the source fixture to that workspace.

`fixtures`
: Optional top-level fixture inventory. Each `[[fixtures]]` entry declares a
  static pack-owned file or directory by `id`, `kind`, `path`, and optional
  `description`. Fixture ids use the same id grammar as packs and cases and
  must be unique within the pack. Fixture paths are source contracts: they must
  be strings, relative to the pack directory, resolve inside the pack after
  following symlinks, exist at manifest-load time, and point to either a file or
  a directory. The runner validates and exposes fixture metadata on loaded
  packs. Referenced file fixtures are read as UTF-8 and appended to
  `Case.prompt`; directory fixtures are not read into prompts. The runner does
  not mutate repositories, execute verifiers, or score from fixtures. For
  `repo-task` measured executions only, it copies one referenced `kind = "repo"`
  directory fixture into a disposable run-owned workspace and captures a
  deterministic source-vs-workspace patch artifact after the adapter call.

`scoring`
: Optional scoring configuration. May appear at pack level as a default and/or
  inline on individual cases as an override. Current executable deterministic
  modes are `none`, `contains`, `regex`, and `verify-script` for measured
  `repo-task` executions. Other reserved modes still parse as manifest values
  but are not implemented by the scorer. See **Scoring** below.

### Prompt Files

Use `prompt_file` when a prompt is long enough that keeping it in TOML would make
the manifest hard to scan:

```toml
[[cases]]
id = "wrap-plan-small"
kind = "chat"
prompt_file = "prompts/wrap-plan-small.md"
```

Prompt files are static text in the current format. After the base prompt is
loaded from `prompt` or `prompt_file`, referenced file fixtures may be appended
as described below. There is no templating, variable substitution, globbing,
include support, or multi-message loader in this slice.

### Fixtures

Use top-level `[[fixtures]]` entries to declare pack-local static inputs that
future workload slices can consume:

```toml
[[fixtures]]
id = "synthetic-django-app"
kind = "context"
path = "fixtures/synthetic-django-app.md"
description = "Portable synthetic target app description"
```

Directory snapshots use the same manifest shape and can declare `kind = "repo"`:

```toml
[[fixtures]]
id = "synthetic-django-repo"
kind = "repo"
path = "fixtures/synthetic-django-repo"
description = "Compact static synthetic Django source snapshot"
```

Required fields:

- `id`: stable fixture identifier. It must match the id grammar below and be
  unique within the pack.
- `kind`: explicit non-empty fixture type string, such as `context` or `repo`.
- `path`: pack-relative file or directory path.

Optional fields:

- `description`: human-readable description. It defaults to an empty string
  when absent.

The loader resolves `path` relative to the pack directory and rejects absolute
paths, `..` traversal outside the pack, symlink targets outside the pack,
paths that resolve to the pack directory itself, missing paths, and existing
paths that are neither files nor directories. File and directory fixtures are
both allowed so later repo-task work can introduce directory snapshots without
changing this source contract.

Fixture declarations remain available as metadata on loaded packs. Cases may
reference fixtures by id with `fixture_refs`. When a referenced fixture path is
a file, the loader reads it as UTF-8 and appends it to the loaded case prompt.
When a referenced fixture path is a directory, including a repo snapshot, the
loader validates the ref but does not read, execute, or inject the directory
contents. The runner later copies the single `kind = "repo"` directory fixture
only for measured `repo-task` executions.

File fixture prompt assembly uses this stable plain-text shape:

```text
<base prompt>

--- BEGIN FIXTURE <fixture-id> (<fixture-kind>, <pack-relative-path>) ---
<fixture file contents>
--- END FIXTURE <fixture-id> ---
```

Multiple referenced file fixtures are appended in the exact `fixture_refs`
order chosen by the case author. `Case.prompt` is the final assembled prompt
that adapters receive. `Case.raw` preserves the original manifest fields, and
`Case.fixture_refs` preserves the fixture id list.

Fixture assembly does not add prompt templating, variable substitution,
globbing, include support, fixture execution, repository mutation, patch
extraction, verifier execution, adapter schema changes, or result schema
changes. Repository copying is limited to the runner-owned measured repo-task
workspace preparation described below.

### Case Fixture References

Use `fixture_refs` on a case to declare which top-level fixture ids are relevant
to that case:

```toml
[[cases]]
id = "wrap-plan-context"
kind = "chat"
prompt_file = "prompts/wrap-plan-context.md"
fixture_refs = ["synthetic-django-app"]
```

`fixture_refs` defaults to `[]` when omitted. The loader rejects non-array
values, non-string entries, ids that do not match the documented grammar,
duplicate refs within one case, and refs that do not exist in the same pack's
top-level fixture inventory. Top-level `[[fixtures]]` entries may appear before
or after `[[cases]]` in TOML; refs are validated against the loaded inventory.

Changing fixture refs alters the effective prompt for referenced file fixtures,
so pack authors should bump `pack.version`.

## ID Grammar

Pack, case, and fixture ids are used as stable record keys or source
identifiers, and case ids are also used as filesystem path components (e.g.
`raw/<case-id>.request.json`). They must match
`^[A-Za-z0-9][A-Za-z0-9_-]*$`: start with an alphanumeric, then any mix of
alphanumerics, underscore, and hyphen. No dots, slashes, spaces, or empty
strings. The runner rejects manifests that violate this at load time.

## Case Kinds

`chat`
: A direct prompt or message list sent to an adapter.

`completion`
: A raw prompt-completion case.

`repo-task`
: Partially implemented case kind for a task that prepares a disposable
  repository workspace and can verify it deterministically. Current runner
  support copies exactly one referenced `kind = "repo"` directory fixture into
  `workspace/<case-id>/rep-NNN/` under the run output directory before each
  measured adapter call, captures a deterministic patch artifact at
  `patch/<case-id>/rep-NNN.diff` after the adapter call, executes
  `verify-script` scoring when declared, and records workspace metadata,
  `patch.path`, `verify`, `repo_task`, and top-level `scoring` in the measured
  `run.jsonl` row. Applying model or agent changes, task logs, retention
  options, repo-task warmups, configurable verifier timeout/environment
  support, and bundled pack conversion remain planned.

`replay`
: A recorded request sequence.

### `repo-task` Contract

The current `repo-task` implementation prepares disposable measured workspaces,
captures patch artifacts, and executes `verify-script` scoring when declared.
Referenced file fixtures still append to `Case.prompt`; referenced non-repo
directory fixtures are rejected for repo-task; the single referenced repo
directory is copied into a run-owned workspace; the measured result record
includes the prepared workspace metadata, `patch.path`, verifier artifact
paths, final verifier status, and top-level `verify-script` scoring. The
runner still does not execute an agent harness or apply model output as code
changes.

Repo-task cases should use this conservative shape:

```toml
[[cases]]
id = "wrap-repo"
kind = "repo-task"
prompt_file = "prompts/wrap-repo.md"
fixture_refs = ["synthetic-django-repo", "synthetic-django-app"]
scoring = { mode = "verify-script", script = "verify/wrap-repo.py" }
```

Fields:

- `id`: case id using the normal id grammar.
- `kind`: must be `repo-task`.
- `prompt` or `prompt_file`: task instructions sent to the model or future
  agent harness. The one-prompt-source rule remains the starting point unless a
  later multi-message contract replaces it.
- `fixture_refs`: must identify exactly one primary fixture with
  `kind = "repo"` whose path is a directory. That fixture is the source
  repository snapshot for the disposable workspace. Additional refs, if any,
  must be non-directory file fixtures and remain prompt/context inputs.
- `scoring`: should use `mode = "verify-script"` for deterministic repo-task
  correctness. `contains` and `regex` remain prompt-output scoring modes and
  are not sufficient for repository correctness.

The contract intentionally does not define broad generic blobs such as
`workspace`, `commands`, or `environment` yet. Add explicit fields only when a
future implementation needs them and the semantics are narrow enough to test.

Directory fixture semantics for repo-task cases:

- The referenced `kind = "repo"` fixture is immutable source. The runner must
  never mutate files under `benchpacks/<pack>/fixtures/`.
- The runner prepares a fresh copy under the run output directory for every
  measured execution at `workspace/<case-id>/rep-NNN/`. The runner includes
  `rep-001` even when `defaults.repetitions = 1`. If the destination already
  exists, the run fails rather than merging into it. Repo-task warmups are
  rejected for now; if they are later supported, each warmup also gets a fresh
  copy and does not share mutations with measured repetitions.
- Repo fixtures must not contain symlinks that would escape workspace
  isolation. Absolute symlinks and relative symlinks whose target resolves
  outside the source repo fixture are rejected before copying. Internal
  relative symlinks may be preserved.
- Future mutation is allowed only inside the disposable workspace. Pack
  fixtures, prompts, verify scripts, and other source artifacts remain
  read-only by contract.
- Repo-task execution must not write outside the run output directory and the
  prepared workspace, and pack contracts must not depend on implicit network
  access or private local host paths.
- Multiple repo fixtures are not allowed until merge/copy rules are explicitly
  documented. Non-repo directory fixtures in repo-task `fixture_refs` are
  reserved and are rejected by the current repo-task runner.
- Referenced file fixtures keep the existing prompt-assembly behavior. They are
  not copied into the workspace or exposed to verifiers unless a later explicit
  field says so.
- Directory fixtures outside repo-task execution remain metadata-only.

Workspace and artifact layout:

- Workspaces live under the run output directory, for example
  `workspace/<case-id>/rep-NNN/`.
- Measured repo-task `run.jsonl` records include a top-level `workspace` object
  with `path`, `source_fixture_id`, and `source_path`. The path is relative to
  the run output directory. The source path is the manifest-declared fixture
  path, not an absolute resolved path.
- Patch capture writes a deterministic diff artifact at
  `patch/<case-id>/rep-NNN.diff`, including `rep-001` for single-repetition
  packs. Measured repo-task records include a top-level `patch` object with the
  run-relative `path`. Empty changes still create an empty patch file and
  record `patch.path`.
- Verifier execution for `scoring.mode = "verify-script"` writes artifacts at
  `verify/<case-id>/rep-NNN.json`,
  `verify/<case-id>/rep-NNN.stdout.log`, and
  `verify/<case-id>/rep-NNN.stderr.log`, including `rep-001` for
  single-repetition packs. Measured repo-task records include a top-level
  `verify` object with run-relative `path`, `stdout_path`, and `stderr_path`.
  They also include `repo_task.status` (`"passed"` for exit code `0`,
  `"failed"` for nonzero or verifier timeout) and
  `repo_task.verify_exit_code` (the integer process exit code, or `null` on
  timeout). Timeout rows keep the same artifact and result object shape and set
  top-level scoring to `{"mode": "verify-script", "passed": false}`.
- Task execution logs should be explicit artifacts, for example
  `task.stdout.log` and `task.stderr.log`.
- Model request/response payloads remain under `raw/`; repo-task workspace,
  patch, task logs, and verifier artifacts are conceptually separate.

The current directory snapshot diff is deterministic and does not require the
fixture or workspace to be a Git repository. It compares the immutable source
fixture directory to the prepared workspace after the adapter call, orders paths
lexicographically by POSIX-style relative path, emits unified diffs for UTF-8
text file additions, deletions, and changes, emits deterministic marker lines
for binary additions, deletions, and changes, represents changed symlink targets
as text diffs of the link target strings, normalizes UTF-8 text line endings to
`\n` before comparison, and ignores empty directories.

Cleanup should be deterministic. Keeping a workspace after a run should be an
explicit runner option or future manifest-independent debug setting, not
implicit behavior. Curated commits should normally include small summaries,
`hardware.json`, compact `run.jsonl`, and small explanatory artifacts such as
patch diffs or `verify.json` when useful; full workspaces and large logs should
usually remain local or ignored.

## Scoring

A pack can declare default scoring at the top level. Cases override it inline
when they need a different mode.

### Pack-level default

```toml
[scoring]
mode = "contains"
expected = "Paris"
```

### Per-case override

```toml
[[cases]]
id = "json-output"
kind = "chat"
prompt = "Return a JSON object with key 'city'."
scoring = { mode = "json-schema", schema = "fixtures/city.schema.json" }
```

### Modes

`none`
: No scoring. The run is recorded but no pass/fail is computed.

`contains`
: Output must contain the `expected` string.

`equals`
: Reserved; not implemented by the scorer yet. Intended behavior is that output
  must equal `expected` exactly after trimming whitespace.

`regex`
: Output must match the regular expression in `pattern`. The scorer uses
  Python's standard `re.search(pattern, output)` with no implicit flags. Pack
  authors who need multiline, dotall, or other flag behavior should use inline
  regex flags or explicit character classes in the pattern. The runner raises a
  `ValueError` when `mode = "regex"` is evaluated without `pattern`.

`json-schema`
: Reserved; not implemented by the scorer yet. Intended behavior is that output
  must parse as JSON and validate against the file at `schema`.

`verify-script`
: Implemented for measured `repo-task` executions only. The runner resolves
  `script` as a pack-relative path, rejects absolute paths and paths that
  resolve outside the pack root, and requires an existing file. It runs the
  script with the current Python interpreter as `sys.executable <script>` after
  workspace preparation, adapter execution, and patch capture, but before
  writing the measured row.

  The verifier receives deterministic arguments:
  `--workspace <absolute prepared workspace path>`, `--case <case id>`,
  `--pack-id <pack id>`, `--pack-version <pack version>`,
  `--source-fixture-id <repo fixture id>`,
  `--patch <absolute patch artifact path>`, and
  `--output <absolute verify JSON path>`.

  Exit code `0` means pass; any nonzero exit code means fail. Verifier
  subprocesses are bounded by a fixed runner-owned default timeout in the
  current implementation. A timeout is recorded as a completed failed measured
  row with `repo_task.verify_exit_code = null` and top-level scoring
  `{"mode": "verify-script", "passed": false}`.

  The runner captures stdout/stderr to deterministic log artifacts and ensures
  the structured JSON exists. If the script does not create the requested JSON,
  the runner writes `{"exit_code": <int>, "passed": <bool>}`. If the script
  writes a JSON object, the runner preserves it while forcing `exit_code` and
  `passed` to match the process result. On timeout, stdout/stderr logs are
  still created, captured partial output is written when Python exposes it, and
  the structured JSON is created or corrected with authoritative
  `exit_code: null`, `passed: false`, `timed_out: true`, and `timeout_s`.
  If timeout-time JSON is missing, malformed, or not an object, the runner
  replaces it with that minimal authoritative timeout object. Non-repo-task
  cases that request `verify-script` fail clearly. The verifier must not mutate
  pack-owned source fixtures. Configurable timeout and environment support
  remain planned.

`llm-judge`
: Reserved; not implemented by the scorer yet. Intended behavior is to send the
  output to a configured judge endpoint. Per D-004 this mode must be declared
  explicitly in the pack; it is never a default and never inferred.

### Relationship to `verify/`

Scripts under `verify/` are used by scoring entries that reference them via
`mode = "verify-script"` and a `script = "verify/..."` path. Implemented inline
declarative modes (`contains` and `regex`) do not need `verify/` and should be
preferred for fast deterministic prompt-output checks. `verify-script` is the
deterministic scoring mode for measured repo-task correctness.

## Requires (TBD)

`docs/specification.md` lists per-pack runtime requirements (model family,
minimum context, streaming support) as part of `benchpack.toml`. The exact
`[requires]` shape is not locked yet. Until it is, packs should describe
requirements in prose in the pack's `README.md`, and the runner should fail
loudly when a hard requirement is unmet.

## Result Compatibility

Result records must include the pack id and version. Comparisons should warn when
pack versions differ.
