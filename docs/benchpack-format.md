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
  do not execute fixtures, copy repositories, create disposable worktrees,
  mutate repositories, template prompts, change adapter request or result
  schemas, extract patches, or run verifiers.

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
  not copy repositories, create disposable worktrees, mutate repositories,
  extract patches, execute verifiers, or score from fixtures.

`scoring`
: Optional scoring configuration. May appear at pack level as a default and/or
  inline on individual cases as an override. See **Scoring** below.

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
loader validates the ref but does not read, copy, execute, or inject the
directory contents.

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
globbing, include support, fixture execution, repository copying, disposable
worktrees, repository mutation, patch extraction, verifier execution, adapter
schema changes, or result schema changes.

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
: A task that prepares a disposable repository and verifies changes.

`replay`
: A recorded request sequence.

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
: Output must equal `expected` exactly after trimming whitespace.

`regex`
: Output must match the regular expression in `pattern`.

`json-schema`
: Output must parse as JSON and validate against the file at `schema`.

`verify-script`
: Run the script at `script` (a path relative to the pack root, normally under
  `verify/`) with the case output and fixtures available. Exit code 0 means
  pass.

`llm-judge`
: Send the output to a configured judge endpoint. Per D-004 this mode must be
  declared explicitly in the pack; it is never a default and never inferred.

### Relationship to `verify/`

Scripts under `verify/` are invoked only when a scoring entry references them
via `mode = "verify-script"` and a `script = "verify/..."` path. Inline
declarative modes (`contains`, `equals`, `regex`, `json-schema`) do not need
`verify/` and should be preferred for fast deterministic checks. A pack may
mix both: a pack-level default of `contains` for smoke cases plus a per-case
`verify-script` for cases that need richer logic.

## Requires (TBD)

`docs/specification.md` lists per-pack runtime requirements (model family,
minimum context, streaming support) as part of `benchpack.toml`. The exact
`[requires]` shape is not locked yet. Until it is, packs should describe
requirements in prose in the pack's `README.md`, and the runner should fail
loudly when a hard requirement is unmet.

## Result Compatibility

Result records must include the pack id and version. Comparisons should warn when
pack versions differ.
