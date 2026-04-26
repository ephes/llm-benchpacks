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
repetitions = 1

[[cases]]
id = "capital"
kind = "chat"
prompt = "What is the capital of France? Answer in one sentence."

[scoring]
mode = "contains"
expected = "Paris"
```

## Fields

`pack.id`
: Stable pack identifier used in result records. Must match the id grammar below.

`pack.version`
: Version of the workload. Change it when prompts, fixtures, or scoring change.

`defaults`
: Request defaults shared by cases.

`cases`
: Ordered benchmark cases. Each case `id` must match the id grammar below and
  must be unique within the pack.

`scoring`
: Optional scoring configuration. May appear at pack level as a default and/or
  inline on individual cases as an override. See **Scoring** below.

## ID Grammar

Pack and case ids are used both as stable record keys and as filesystem path
components (e.g. `raw/<case-id>.request.json`). They must match
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
