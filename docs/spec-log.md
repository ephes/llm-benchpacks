# Spec Log

Use this file for dated changes to the benchmark design. It is intentionally
lighter than ADRs: decisions go in `docs/decisions.md`; this file captures the
working history and open questions.

## Format

```text
## YYYY-MM-DD

### Changed
- ...

### Open Questions
- ...
```

## 2026-05-02 (Phase 3 manifest verifier timeout)

### Changed

- Added manifest-configurable verifier timeouts for measured `repo-task`
  `verify-script` scoring through optional `scoring.timeout_s`.
- `timeout_s` is a first-class scoring field, not an opaque extra key, and is
  validated as a positive TOML int or float. Booleans, strings, zero, and
  negative values fail manifest loading.
- Verifier execution now uses the effective scoring table's timeout, so
  case-local scoring overrides pack-level scoring for `timeout_s` the same way
  they already override `mode` and `script`.
- The default remains `300.0` seconds when `timeout_s` is absent. Timeout
  verifier JSON records the actual configured value, while normal result rows
  do not gain new top-level timeout fields.
- Adapter request shape, raw request/response paths, workspace, patch, task,
  verify, repo_task, and scoring row shapes, repo-task warmup rejection,
  prompt-output scoring, non-repo-task `verify-script` rejection, verifier
  environment handling, task timeout handling, and workspace retention behavior
  remain unchanged.

### Open Questions

- Future slices still need full agent-session harness integration, richer task
  status/reporting if needed, repo-task warmup support, cleanup and retention
  options, task environment support if needed, and larger bundled repo-task
  conversion.

## 2026-05-02 (Phase 3 manifest verifier environment)

### Changed

- Added manifest-configurable verifier environment support for measured
  `repo-task` `verify-script` scoring through optional `scoring.environment`.
- `environment` is a first-class scoring field, not an opaque extra key, and is
  validated as a TOML table of string keys to string values. Empty string values
  are allowed. Non-table values, non-string values, nested tables, arrays, empty
  names, names with unsafe characters, names starting with a digit, and values
  containing NUL fail manifest loading.
- Verifier execution now uses the effective scoring table's environment, so
  case-local scoring overrides pack-level scoring as a whole instead of
  field-merging environment entries.
- When `environment` is absent, verifier subprocesses keep the previous inherited
  environment behavior. When present, the runner copies the current environment,
  overlays the manifest entries, and passes that copy only to the verifier.
- Adapter request shape, raw request/response paths, workspace, patch, task,
  verify, repo_task, and scoring row shapes, timeout behavior and timeout JSON,
  repo-task warmup rejection, prompt-output scoring, non-repo-task
  `verify-script` rejection, task environment handling, task timeout handling,
  and workspace retention behavior remain unchanged.

### Open Questions

- Future slices still need full agent-session harness integration, richer task
  status/reporting if needed, repo-task warmup support, cleanup and retention
  options, task environment support if needed, and larger bundled repo-task
  conversion.

## 2026-05-02 (Phase 3 bundled repo-task patch pack)

### Changed

- Added the first bundled measured repo-mutating `repo-task` pack:
  `patch-from-failure` version `0.1.0`.
- The pack declares one tiny stdlib-only Python `kind = "repo"` fixture and one
  measured `fix-greeting` case with `defaults.warmup = 0`,
  `defaults.repetitions = 1`, `defaults.stream = false`, and case-local
  `scoring.mode = "verify-script"`.
- The prompt tells the model to return only a fenced `diff` block containing a
  unified diff from the repository root, exercising the current model-output
  patch bridge as an actual bundled benchmark surface.
- The verifier is stdlib-only and deterministic: it imports `greeter.py` from
  the prepared workspace, requires `greet("Ada") == "Hello, Ada!"`, requires a
  non-empty captured patch artifact, writes JSON to the runner-provided output
  path, and uses the process exit code as the pass/fail authority.
- Added bundled pack loading coverage and a mocked-adapter CLI test that runs
  `patch-from-failure` by name, applies a fenced diff, confirms source fixture
  immutability, and checks the existing `workspace`, `patch`, `task`, `verify`,
  `repo_task`, `scoring`, and `raw` row shapes without adding a generic
  `artifacts` object.
- No adapter request fields, CLI flags, manifest shell commands, manifest task
  commands, environment configuration, task timeout configuration, repo-task
  warmups, workspace retention options, live benchmark output, larger bundled
  repo-task conversion, broad generic artifact object, or new task status/result
  fields were added.

### Open Questions

- Future slices still need full agent-session harness integration, richer task
  status/reporting if needed, repo-task warmup support, cleanup and retention
  options, configurable verifier environment support, and larger
  bundled repo-task conversion.

## 2026-05-02 (Phase 3 repo-task verifier timeout)

### Changed

- Added a fixed runner-owned timeout for measured `repo-task`
  `verify-script` subprocess execution so verifier hangs do not hang the whole
  benchmark run.
- Verifier timeouts are recorded as completed failed measured rows rather than
  runner crashes. Timeout rows keep the existing `workspace`, `patch`,
  `verify`, `repo_task`, and top-level `scoring` shape.
- Timeout rows set `repo_task.status = "failed"`,
  `repo_task.verify_exit_code = null`, and top-level scoring to
  `{"mode": "verify-script", "passed": false}`.
- Timeout verifier JSON is created or corrected with authoritative
  `exit_code: null`, `passed: false`, `timed_out: true`, and `timeout_s`.
  If timeout-time JSON is an object, non-authoritative fields are preserved; if
  it is missing, malformed, or not an object, it is replaced with the minimal
  timeout object.
- Timeout stdout/stderr logs are always written at the deterministic verifier
  artifact paths. Captured partial output from `subprocess.TimeoutExpired` is
  preserved when Python exposes it; otherwise empty log files are created.
- Non-timeout verifier behavior, script path safety, prompt-output scoring,
  raw request/response paths, adapter request shape, workspace preparation,
  patch capture, repo-task fixture validation, symlink escape rejection,
  repo-task warmup rejection, and non-repo-task `verify-script` rejection remain
  unchanged.
- No manifest timeout field, CLI timeout flag, environment configuration, task
  execution logs, agent-session harness, model-output mutation/application,
  workspace retention option, repo-task warmup support, bundled pack
  conversion, live benchmark run, or generated result artifact was added.

### Open Questions

- Future slices still need real task or agent execution, model-output patch
  application, warmup workspace support, cleanup and retention options,
  configurable verifier environment support, and bundled pack
  conversion.

## 2026-05-02 (Phase 3 repo-task model-output patch application)

### Changed

- Added the next narrow measured `repo-task` task phase: after adapter
  execution, the runner extracts the first fenced code block whose info string
  is exactly `diff` or `patch`, treats that block body as a unified diff, and
  applies it inside the prepared workspace before source-vs-workspace patch
  capture and verifier execution.
- Non-matching fenced blocks are ignored. Missing matching blocks, empty patch
  blocks, unsafe paths, and unapplicable diffs are written as deterministic task
  stderr messages and do not crash the benchmark row.
- Successful application writes a short deterministic task stdout message and
  leaves task stderr empty. The existing top-level `task.stdout_path` and
  `task.stderr_path` row metadata shape is unchanged.
- Patch capture now observes any applied model patch, so
  `patch/<case-id>/rep-NNN.diff` reflects the mutated workspace. `verify-script`
  verifiers also observe the mutated workspace because they still run after
  patch capture.
- Path preflight rejects absolute paths, `..` traversal, null bytes, and paths
  that resolve outside the prepared workspace. Pack-owned source fixtures remain
  immutable and are not passed to the patch applier.
- Raw request/response paths, adapter request shape, workspace metadata,
  patch metadata, verifier pass/fail/timeout behavior, repo-task fixture
  validation, symlink escape rejection, repo-task warmup rejection,
  prompt-output scoring, non-repo-task `verify-script` rejection, and chat row
  shapes remain unchanged.
- No agent-session harness, shell command manifest, environment configuration,
  task timeout configuration, CLI task flags, workspace retention option,
  repo-task warmup support, bundled pack conversion, live benchmark run, broad
  generic `artifacts` object, or new task status/result field was added.

### Open Questions

- Future slices still need full agent-session harness integration, richer task
  status/reporting if needed, repo-task warmup support, cleanup and retention
  options, configurable verifier environment support, and bundled pack
  conversion.

## 2026-05-02 (Phase 3 repo-task task log artifacts)

### Changed

- Added deterministic task stdout/stderr log artifacts for every measured
  `repo-task` execution at `task/<case-id>/rep-NNN.stdout.log` and
  `task/<case-id>/rep-NNN.stderr.log`, including `rep-001` for
  single-repetition packs.
- The current task phase remains a runner-owned no-op placeholder, so the new
  task log files are created empty. No agent-session harness, shell command
  execution, manifest task command, or model-output mutation/application was
  added.
- Measured repo-task `run.jsonl` rows now include top-level `task.stdout_path`
  and `task.stderr_path` with run-relative POSIX paths. Repo-task rows using
  prompt-output scoring include `workspace`, `patch`, and `task`, while
  `verify` and `repo_task` remain limited to `verify-script`.
- Chat records, including chat cases that reference repo directory fixtures,
  still do not include `workspace`, `patch`, `task`, `verify`, or
  `repo_task`.
- Raw model request/response paths under `raw/`, adapter request shape,
  workspace preparation, patch capture, verifier pass/fail/timeout behavior,
  repo-task fixture validation, symlink escape rejection, repo-task warmup
  rejection, prompt-output scoring, and non-repo-task `verify-script`
  rejection remain unchanged.
- No manifest task-log fields, CLI flags, environment configuration, task
  timeout configuration, workspace retention option, repo-task warmup support,
  bundled pack conversion, live benchmark run, or generated result artifact was
  added.

### Open Questions

- Future slices still need real task or agent execution, model-output mutation
  or patch application, warmup workspace support, cleanup and retention options,
  configurable verifier environment support, and bundled pack
  conversion.

## 2026-05-02 (Phase 3 repo-task verifier artifacts)

### Changed

- Added measured `repo-task` verifier execution for
  `scoring.mode = "verify-script"`. The runner executes verifier scripts after
  workspace preparation, adapter execution, and patch capture, but before
  writing the measured `run.jsonl` row.
- Verifier scripts are resolved as pack-relative paths, must exist, and are
  rejected if absolute or escaping the pack root. The initial execution shape is
  `sys.executable <script>` with deterministic command-line arguments for the
  prepared workspace, case id, pack id/version, source fixture id, patch path,
  and requested output JSON path.
- Verifier artifacts are written beside `raw/` under
  `verify/<case-id>/rep-NNN.json`,
  `verify/<case-id>/rep-NNN.stdout.log`, and
  `verify/<case-id>/rep-NNN.stderr.log`, including `rep-001` for
  single-repetition packs.
- If a verifier does not create structured JSON, the runner writes a minimal
  object containing `exit_code` and `passed`. If the verifier writes a JSON
  object, the runner preserves it while making `exit_code` and `passed`
  authoritative from the process result.
- Measured repo-task `verify-script` rows now include top-level `verify`,
  `repo_task`, and `scoring` objects. `repo_task.status` is `"passed"` for exit
  code `0` and `"failed"` for nonzero; `repo_task.verify_exit_code` records the
  integer process exit code; top-level scoring is
  `{"mode": "verify-script", "passed": <bool>}`.
- Non-repo-task cases that request `verify-script` fail clearly. Normal chat
  records, including chat cases with repo directory fixtures, still do not
  include `workspace`, `patch`, `verify`, or `repo_task`.
- Adapter requests remain unchanged and still receive only prompt, model,
  endpoint, defaults, and raw request/response paths.
- Existing raw path behavior, prompt-output scoring, workspace metadata, patch
  metadata, repo-task fixture validation, symlink escape rejection, and
  repo-task warmup rejection remain unchanged.
- No agent-session harness, model-output mutation/application, workspace
  cleanup/retention option, repo-task warmup support, timeout/environment
  configuration, bundled pack conversion, live benchmark run, or generated
  result artifact was added.

### Open Questions

- Future slices still need real task or agent execution, model-output patch
  application, warmup workspace support, cleanup and retention options,
  timeout/environment configuration, and bundled pack conversion.

## 2026-05-02 (Phase 3 repo-task patch artifacts)

### Changed

- Added deterministic patch artifact capture for measured `repo-task`
  executions. After the adapter call, the runner compares the immutable source
  repo fixture directory to the prepared workspace directory and writes
  `patch/<case-id>/rep-NNN.diff`.
- Measured repo-task `run.jsonl` rows now include a top-level `patch` object
  with run-relative `patch.path`, alongside the existing `workspace` metadata.
- Patch files are written for every measured repo-task execution, including
  no-change runs where the patch file is empty. The path includes `rep-001`
  even when the pack has one measured repetition.
- Patch capture uses a deterministic directory snapshot diff rather than
  `git diff`, so repo fixtures do not need to be Git repositories. Text changes
  use unified diff output, added/deleted files are represented deterministically,
  symlink target changes are text diffs of link targets, UTF-8 text line endings
  are normalized before comparison, and binary changes use deterministic marker
  lines.
- Chat records, including chat cases that reference repo directory fixtures,
  still do not include `workspace` or `patch`.
- Adapter requests remain unchanged and still receive only prompt, model,
  endpoint, defaults, and raw request/response paths.
- Raw request/response path behavior, scoring, repo-task fixture validation,
  symlink escape rejection, measured workspace preparation, and repo-task
  warmup rejection remain unchanged.
- No verifier execution, final repo-task status, task or agent harness,
  workspace cleanup/retention option, bundled pack conversion, or live
  benchmark result artifact was added.

### Open Questions

- Future slices still need verifier invocation, verifier/log artifact paths,
  final repo-task status fields, task or agent execution, warmup workspace
  support, cleanup and retention options, and curated artifact rules for
  repo-task outputs.

## 2026-05-01 (Phase 3 measured repo-task workspaces)

### Changed

- Implemented the first narrow repo-task runtime slice: measured `repo-task`
  executions now prepare a disposable run-owned workspace before the adapter
  call.
- The runner requires each repo-task case to reference exactly one
  `kind = "repo"` directory fixture. Additional referenced file fixtures remain
  prompt/context inputs, while non-repo directory fixtures, missing repo
  fixtures, multiple repo fixtures, and repo fixtures that are not directories
  fail before adapter execution.
- Workspaces are copied under the run output directory at
  `workspace/<case-id>/rep-NNN/`, including `rep-001` for single-repetition
  packs. Existing destinations fail rather than being merged.
- Workspace preparation rejects absolute symlinks and relative symlinks whose
  target resolves outside the source repo fixture before copying, while
  allowing internal relative symlinks.
- Source fixtures under `benchpacks/<pack>/fixtures/` remain immutable by
  contract. Existing chat cases still treat referenced directory fixtures as
  metadata-only and do not create workspaces.
- Repo-task warmups are rejected for now because warmup workspace semantics are
  intentionally deferred.
- Adapter requests and `run.jsonl` records are unchanged; no workspace paths,
  repo-task status fields, verifier output, patch artifacts, agent harness, or
  live benchmark result artifacts were added.

### Open Questions

- Future slices still need verifier invocation, patch capture, repo-task result
  schema fields, task or agent execution, warmup workspace support, cleanup and
  retention options, and curated artifact rules for repo-task outputs.

## 2026-05-01 (Phase 3 repo-task workspace result metadata)

### Changed

- Added the next narrow repo-task result schema slice: measured `repo-task`
  `run.jsonl` rows now include a top-level `workspace` object.
- The workspace object records `path`, `source_fixture_id`, and `source_path`.
  `path` is relative to the run output directory, for example
  `workspace/<case-id>/rep-NNN`, and `source_path` is the manifest-declared
  fixture path rather than an absolute resolved path.
- Chat records, including chat cases that reference repo directory fixtures,
  still do not include `workspace`.
- Adapter requests remain unchanged and still receive only prompt, model,
  endpoint, defaults, and raw request/response paths.
- Raw request/response path behavior, scoring, repo-task fixture validation,
  symlink escape rejection, and repo-task warmup rejection remain unchanged.
- No verifier execution, patch capture, final repo-task status, task or agent
  harness, workspace cleanup/retention option, bundled pack conversion, or live
  benchmark result artifact was added.

### Open Questions

- Future slices still need verifier invocation, patch capture, repo-task patch
  and verifier artifact paths, final repo-task status fields, task or agent
  execution, warmup workspace support, cleanup and retention options, and
  curated artifact rules for repo-task outputs.

## 2026-04-30 (Phase 3 repo-task contract design)

### Changed

- Defined the docs-first repo-task contract for future disposable repository
  execution before adding runner support.
- Specified that pack-owned `kind = "repo"` directory fixtures are immutable
  source artifacts and that future repo-task mutation must happen only in a
  run-owned disposable workspace under the result directory.
- Documented the planned repo-task fixture rule: one primary repo directory
  fixture per repo-task case, with additional referenced file fixtures remaining
  prompt/context inputs unless a later explicit field gives them another role.
- Documented planned repo-task artifacts: prepared workspace metadata,
  retained `workspace/` contents when explicitly kept, `patch.diff`, task
  stdout/stderr logs, verifier output such as `verify.json`, and final status.
- Clarified that `verify-script` is the intended deterministic repo-task
  scoring mode once implemented, while `contains` and `regex` remain
  prompt-output scoring modes.
- Added durable decision D-021 for run-owned disposable workspaces and explicit
  repo-task artifacts.
- Preserved the current `desktop-django-wrap` behavior: it remains prompt-only,
  file fixture contents assemble into prompts, and the directory-shaped
  `synthetic-django-repo` fixture remains metadata-only.
- No runner implementation, adapter change, result schema writer change,
  fixture copying code, verifier execution, patch extraction, prompt change,
  pack manifest change, scoring change, live benchmark run, or generated result
  artifact was added.

### Open Questions

- Exact result schema keys for repo-task status and artifact paths still need to
  be designed with the implementation slice.
- The first coding slice should choose the concrete workspace path convention
  under each result directory and implement disposable directory copy for one
  repo fixture per measured execution.
- Later slices still need verifier invocation details, patch capture rules,
  timeout/environment handling, workspace retention options, and agent-session
  integration.

## 2026-04-30 (Phase 3 directory fixture snapshot)

### Changed

- Added a compact pack-local `desktop-django-wrap` directory fixture at
  `fixtures/synthetic-django-repo/` with a tiny synthetic Django source
  snapshot.
- Declared the snapshot as top-level fixture `synthetic-django-repo` with
  `kind = "repo"` and a pack-relative directory path.
- Bumped `desktop-django-wrap` to version `0.1.4` and linked both existing
  cases to `synthetic-django-app` and `synthetic-django-repo` in that order.
- The existing referenced file fixture still assembles into `Case.prompt`; the
  directory fixture remains metadata-only and is not read, copied, executed, or
  injected into prompts.
- No live benchmark run, adapter change, compare change, result schema change,
  scoring change, repo mutation, disposable worktree, directory copying,
  fixture execution, verifier execution, patch extraction, prompt templating,
  agent-session replay, or generated result artifact was added.

### Open Questions

- Future Phase 3 slices still need to define disposable repo-task execution,
  directory fixture execution or copying semantics, prompt import from
  `desktop-django-starter`, verifier scripts, patch extraction, and eventual
  real agent-session replay.

## 2026-04-30 (Phase 3 regex output contract)

### Changed

- Implemented executable deterministic `regex` scoring with Python
  `re.search(pattern, output)` and no implicit regex flags.
- Bumped `desktop-django-wrap` to version `0.1.5`.
- Tightened both `desktop-django-wrap` prompts to require the same short output
  skeleton: `DDS_WRAP_PLAN`, then `Inspect:`, `Electron shell:`,
  `Django runtime:`, `Packaging:`, and `Verification:` in order.
- Changed `desktop-django-wrap` scoring from marker-only `contains` to `regex`
  so the marker and fixed labels must appear in order.
- The `synthetic-django-app` file fixture still assembles into prompts with
  stable delimiters, and the `synthetic-django-repo` directory fixture remains
  metadata-only and is not read, copied, executed, or injected into prompts.
- No live benchmark run, adapter change, compare change, result schema change,
  repo mutation, disposable worktree, directory copying, fixture execution,
  verifier execution, patch extraction, prompt templating, agent-session
  replay, or generated result artifact was added.

### Open Questions

- Future Phase 3 slices still need to define disposable repo-task execution,
  directory fixture execution or copying semantics, prompt import from
  `desktop-django-starter`, verifier scripts, patch extraction, and eventual
  real agent-session replay.

## 2026-04-30 (Phase 2 closure docs)

### Changed

- Closed Phase 2 administratively in `docs/implementation-plan.md` after
  reviewing the landed runtime-sweep, streaming TTFT, warmup/repetition,
  Ollama native timing, MLX validation, llama-server validation, compare,
  cache metadata, cache-aware compare, prompt/cache parity, prefill parity,
  gated prefill TPS, and OpenAI streaming usage compatibility slices.
- Marked Phase 2 as implemented/closed while preserving validation caveats:
  the curated run log has MLX and llama-server evidence, the 2026-04-29
  llama-server runtime rows are warm-cache rows, prompt-cache parity remains
  required for prefill-speed interpretation, and a curated Ollama
  `runtime-sweep` live run remains optional future validation.
- Kept Phase 3 as the active current workstream; `desktop-django-wrap`,
  prompt-file support, static fixture metadata, and case-level fixture refs
  remain the started Phase 3 surface.
- No live benchmark run, adapter change, compare change, result schema change,
  scoring change, pack format change, pack manifest change, or generated result
  artifact was added.

### Open Questions

- Whether to add a curated Ollama `runtime-sweep` live run later for additional
  Phase 2 validation evidence remains optional and should be recorded in
  `docs/run-log.md` only if an actual run is performed and curated.

## 2026-04-30 (Phase 3 file fixture prompt assembly)

### Changed

- Added fixture-backed prompt assembly for referenced file fixtures.
- Loaded `Case.prompt` remains the final adapter prompt. The base prompt still
  comes from exactly one `prompt` or `prompt_file` source, then referenced file
  fixture contents are appended in `fixture_refs` order.
- Appended file fixtures use stable plain-text delimiters that include the
  fixture id, kind, and pack-relative path.
- Directory fixture refs remain valid metadata-only refs and are not copied,
  executed, read into prompts, or turned into disposable repositories.
- `Case.raw` still preserves the manifest fields, `Case.fixture_refs` still
  exposes fixture id strings, and `Pack.fixtures` still exposes fixture
  metadata.
- Bumped `desktop-django-wrap` to version `0.1.3` because both effective
  prompts now include the referenced `synthetic-django-app` file fixture.
- No live benchmark run, adapter change, compare change, result schema change,
  scoring change, repo mutation, verifier execution, patch extraction,
  agent-session replay, or generated result artifact was added.

### Open Questions

- Future Phase 3 slices still need to define directory fixture semantics,
  disposable repo-task execution, prompt templating or multi-message support if
  needed, verifier scripts, patch extraction, and eventual real agent-session
  replay.

## 2026-04-30 (Phase 3 case fixture refs)

### Changed

- Added optional case-level `fixture_refs` support to benchpack manifests.
- Loaded `Case` objects now expose `fixture_refs` as fixture id strings, with
  cases that omit the field loading as `[]`.
- `fixture_refs` must be a TOML array of strings. Each ref must match the
  existing id grammar, be unique within the case, and point to an existing
  top-level fixture id in the same pack.
- Fixture refs are validated against the loaded top-level fixture inventory, so
  `[[fixtures]]` may appear before or after `[[cases]]` in TOML.
- Bumped `desktop-django-wrap` to version `0.1.2` and linked both existing
  cases to the existing portable `synthetic-django-app` fixture by id.
- Existing `desktop-django-wrap` case ids, defaults, prompt-file entries,
  scoring mode, prompt marker behavior, and fixture declaration/path remain
  unchanged.
- No live benchmark run, new adapter, new scoring engine, compare change,
  prompt templating, fixture content loading, fixture execution, disposable
  worktree handling, verifier script, patch extraction, repo mutation, or agent
  execution harness was added.

### Open Questions

- Future Phase 3 slices still need to define prompt assembly from fixtures,
  fixture loading semantics beyond metadata refs, directory fixture use,
  disposable target repos, `repo-task` execution, patch extraction, and
  verify-script scoring.

## 2026-04-29 (Phase 3 fixture metadata support)

### Changed

- Added top-level `[[fixtures]]` support to the benchpack manifest loader.
- Fixture ids use the existing id grammar and duplicate fixture ids fail at
  load time.
- Fixture kind values must be non-empty strings. Fixture paths must be strings,
  relative to the pack directory, exist, point to a file or directory, and not
  resolve to the pack directory itself.
- Fixture path resolution rejects absolute paths, `..` traversal outside the
  pack, and symlink targets outside the pack directory.
- Loaded `Pack` objects now expose `fixtures` metadata while packs without
  fixtures continue to load with an empty fixture list.
- Added one portable synthetic `desktop-django-wrap` fixture file under
  `benchpacks/desktop-django-wrap/fixtures/` and bumped that pack to version
  `0.1.1`.
- Existing `desktop-django-wrap` case ids, defaults, prompt-file entries,
  scoring mode, and `DDS_WRAP_PLAN` marker behavior remain unchanged.
- No live benchmark run, new adapter, new scoring engine, compare change,
  prompt templating, fixture execution, disposable worktree handling, verifier
  script, patch extraction, repo mutation, or agent execution harness was
  added.

### Open Questions

- Future Phase 3 slices still need to define prompt assembly from fixtures,
  directory fixture loading semantics, disposable target repos, `repo-task`
  execution, patch extraction, and verify-script scoring.

## 2026-04-29 (Phase 3 prompt-file support)

### Changed

- Added case-level `prompt_file` support to the benchpack manifest loader.
- `prompt_file` paths are resolved relative to the pack directory, must be
  relative paths, and must resolve inside the pack after following symlinks.
- Cases now fail at load time when they define both `prompt` and `prompt_file`,
  or neither prompt source.
- The loader reads prompt files as UTF-8 text and stores the contents in
  `Case.prompt`, so existing CLI, adapter, scoring, reporter, and result record
  behavior remains unchanged.
- Moved the bundled `desktop-django-wrap` prompts from inline TOML strings to
  pack-local files under `benchpacks/desktop-django-wrap/prompts/`, while
  keeping pack id, version, defaults, case ids, scoring mode, and marker check
  unchanged.
- No live benchmark run, new adapter, new scoring engine, compare change,
  fixture support, disposable worktree handling, verifier script, repo mutation,
  or agent execution harness was added.

### Open Questions

- Future Phase 3 slices still need fixture loading, disposable target repos,
  repo-task semantics, patch extraction or agent-harness integration, and
  verify-script scoring contracts before this becomes a repo-mutating wrapping
  benchmark.

## 2026-04-29 (Phase 3 desktop-django-wrap starter pack)

### Changed

- Added the bundled `desktop-django-wrap` pack as the first Phase 3
  coding-agent-shaped workload surface.
- The pack is prompt-only and portable: two inline chat cases ask for concise
  Django-in-Electron wrapping plans derived from the
  `desktop-django-starter` workflow, without local paths, target repo
  checkouts, network dependencies, fixtures, repo mutation, patch extraction,
  or verifier scripts.
- The pack sets `defaults.stream = true`, `defaults.warmup = 0`,
  `defaults.repetitions = 1`, and `defaults.max_tokens = 384`.
- Scoring uses the existing executable `contains` mode against the explicit
  marker `DDS_WRAP_PLAN` as a minimal deterministic sanity check.
- No live benchmark run, new adapter, new scoring engine, compare change,
  fixture support, disposable worktree handling, or agent execution harness was
  added.

### Open Questions

- Future Phase 3 slices still need compact target fixtures, disposable target
  repos, deterministic verify scripts, patch extraction or agent-harness
  integration, and eventual replay of fuller wrapping sessions.

## 2026-04-29 (Phase 2 OpenAI stream usage compatibility)

### Changed

- Added `benchpack run --openai-stream-usage {include,omit}` as an explicit
  `openai-chat` streaming compatibility switch.
- The default `include` mode preserves the existing request shape by sending
  `stream_options.include_usage` whenever the pack requests streaming.
- The `omit` mode still sends `"stream": true` but omits the `stream_options`
  key entirely for endpoints that reject OpenAI streaming usage options.
- In omit mode, streamed output text, raw chunks, `timing.wall_s`, and
  `timing.ttft_s` remain available when content chunks arrive. If no usage chunk
  is reported, `tokens.prompt`, `tokens.output`, `tokens.cached_prompt`,
  `timing.prefill_tps`, and `timing.decode_tps` remain null.
- The CLI passes the option through a private per-request defaults key for
  `openai-chat` only, without changing benchpack manifest semantics or mutating
  the loaded pack defaults.
- No automatic retry, endpoint detection, new adapter, compare behavior change,
  live benchmark run, or generated result artifact update was added.

### Open Questions

- Future work may add endpoint presets or manifest-level adapter options if
  several compatibility switches accumulate, but this slice intentionally keeps
  the usage mode as an explicit run-time option.
- Live validation against a server that rejects `stream_options.include_usage`
  remains useful when such a target is available.

## 2026-04-29 (Phase 2 gated compare prefill TPS)

### Changed

- Added a `prefill_tps med` column to `benchpack compare`.
- The column is a median of normalized `run.jsonl` `timing.prefill_tps` values
  using the same numeric filter as the other compare metrics.
- Numeric prefill TPS is rendered only when the case-level `prefill parity`
  status is `comparable`; `missing-case`, `prompt-missing`, `prompt-diff`,
  `cache-missing`, and `cache-diff` render `—` even if timing values exist.
- Existing prompt/cache warnings, cache coverage, and parity status priority
  remain unchanged.
- Compare still reads only normalized `run.jsonl` records and does not inspect
  ignored `raw/` artifacts or infer prompt/cache state from timing fields.

### Open Questions

- Future compare slices may add stronger summaries for comparable prefill cases,
  but they should preserve the parity gate unless a better deterministic parity
  contract replaces it.
- Historical artifacts without normalized cache fields will continue to suppress
  prefill speed display until rerun or otherwise supported by explicit
  normalized metadata.

## 2026-04-29 (Phase 2 compare prefill parity status)

### Changed

- Added a compact `prefill parity` column to `benchpack compare`, repeated on
  each run row with a case-level status.
- Status values use deterministic priority order: `missing-case`,
  `prompt-missing`, `prompt-diff`, `cache-missing`, `cache-diff`, then
  `comparable`.
- The status is derived only from normalized `run.jsonl` summaries: case row
  presence, complete numeric `tokens.prompt` coverage, prompt-token medians,
  complete numeric `tokens.cached_prompt` coverage, and cached prompt-token
  medians.
- Existing prompt/cache warnings remain, cache metadata coverage remains, and
  `timing.prefill_tps` remains omitted from the primary compare table.

### Open Questions

- A future compare slice can expose `prefill_tps` only after deciding how to
  gate the numeric speed column on the explicit parity status.
- Historical artifacts without `tokens.cached_prompt` will continue to show
  non-comparable status for prefill interpretation until rerun or otherwise
  supported by explicit normalized cache metadata.

## 2026-04-29 (Phase 2 compare prompt/cache parity)

### Changed

- Added prompt/cache parity context to `benchpack compare`: the table now shows
  median numeric `tokens.prompt` beside median `tokens.cached_prompt`.
- Compare warns when all compared runs for a case have measured rows and every
  row has numeric prompt-token metadata but the prompt-token medians differ,
  because cache parity is not comparable across different prompt token counts.
- Existing cache metadata warnings remain: compare still warns for incomplete
  `tokens.cached_prompt` metadata and for differing complete cached prompt-token
  medians, while suppressing prompt/cache median mismatch warnings when a case
  is absent from one compared run.
- `timing.prefill_tps` remains omitted. This slice adds prompt/cache parity
  visibility only; it does not make prefill-speed claims and does not read raw
  artifacts or infer token/cache state.

### Open Questions

- Future compare work can add `prefill_tps` only after the output makes
  prompt/cache parity explicit enough to avoid mixing different prompts or
  warm-cache and cold-prefill behavior.

## 2026-04-29 (Phase 2 compare cache awareness)

### Changed

- Extended `benchpack compare` to report median numeric `tokens.cached_prompt`
  and cache metadata coverage for each case/run row while keeping
  `timing.prefill_tps` out of the primary table.
- Added deterministic per-case warnings when cache metadata is incomplete for
  compared measured rows or when all compared runs for a case have complete
  cache metadata but cached prompt-token medians differ.
- Compare still reads only normalized `run.jsonl` records. It does not inspect
  ignored `raw/` artifacts and does not infer cache counts from prompt length,
  timing, or backend-specific duration fields.
- Existing historical rows that lack `tokens.cached_prompt`, or carry null or
  non-numeric values, remain readable and are displayed as missing cache
  metadata.

### Open Questions

- Future compare work may reintroduce `prefill_tps` only after cache parity is
  explicit enough to avoid warm-cache and cold-prefill comparisons being mixed.

## 2026-04-29 (Phase 2 compare command)

### Changed

- Added `benchpack compare <result-dir> <result-dir> [...]` as the first
  read-only comparison slice over existing result directories that contain
  `run.jsonl`.
- The compare command loads normalized result rows only, groups by case and
  input run, and prints a deterministic Markdown table with row count, `ok`
  count, and median `wall_s`, `ttft_s`, `decode_tps`, `total_tps`, and
  `tokens.output`.
- Compare warns when pack ids or versions differ and handles missing, empty, or
  malformed `run.jsonl` inputs with clear nonzero CLI errors.
- `prefill_tps` is intentionally omitted from the primary table because
  normalized result rows do not include prompt-cache parity metadata. The
  2026-04-29 `llama-server` runtime rows remain warm-cache rows, so compare
  output must not be read as cross-server cold-prefill evidence.
- No adapter behavior, adapter return payload shape, benchmark pack semantics,
  result record schema, compatibility fallback, live server orchestration, or
  generated result artifacts changed in this slice.

### Open Questions

- A future result schema may need normalized cached-token fields before
  `prefill_tps` can be compared across servers with cache parity.
- Future compare slices may add richer aggregation or output formats, but this
  slice deliberately stays at per-case medians over measured rows.

## 2026-04-29 (Phase 2 prompt-cache metadata)

### Changed

- Added normalized `tokens.cached_prompt` to new `run.jsonl` records. The field
  is the backend-reported count of prompt tokens served from cache, or `null`
  when unavailable.
- `openai-chat` now extracts
  `usage.prompt_tokens_details.cached_tokens` from both non-streaming responses
  and final streaming usage chunks while preserving existing prompt/output token
  behavior.
- `ollama-generate` leaves `tokens.cached_prompt` as `null`; its native
  `prompt_eval_*` fields are timing/count fields, not equivalent cache-hit
  counts.
- Existing committed result artifacts were not rewritten. Historical rows may
  lack `tokens.cached_prompt`; compare continues to read those rows.
- `benchpack compare` keeps the same table columns and still omits
  `prefill_tps`; its caveat now names `tokens.cached_prompt`. The new field
  makes future cache-parity checks possible, but missing or unequal cached-token
  counts do not support cross-server prefill-speed conclusions.

### Open Questions

- A future compare slice can summarize `tokens.cached_prompt` or warn on cache
  mismatch before exposing any prefill-speed comparison.
- Old curated artifacts without `tokens.cached_prompt` remain useful for
  wall/TTFT/decode/total/output comparisons, but not for cache-aware prefill
  analysis without separate evidence.

## 2026-04-29 (Phase 2 llama-server validation passed)

### Changed

- Completed the Phase 2 `llama-server` validation slice on `atlas.local` after
  preparing the host with Homebrew `llama.cpp` 8960
  (`version: 8960 (19821178b)`) and a local GGUF instruct model.
- Used model repository `bartowski/Qwen2.5-0.5B-Instruct-GGUF` at repository
  SHA `41ba88dbac95fed2528c92514c131d73eb5a174b` and model file
  `/Users/jochen/models/gguf/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf`
  (`sha256: 6eb923e7d26e9cea28811e1a8e852009b21242fb157b26149d3b188f3a8c8653`).
  `llama-server` reported GGUF V3, file type `Q4_K - Medium`, 494.03M
  parameters, and Qwen2.5 0.5B Instruct metadata.
- Verified local server usage before benchmark execution. Relevant help output
  confirmed `--model`, `--host`, `--port`, `--alias`, `--ctx-size`,
  `--gpu-layers`, and OpenAI-compatible server flags. The live server command
  was:
  `llama-server --model /Users/jochen/models/gguf/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf --alias qwen2.5-0.5b-instruct-q4_k_m --host 127.0.0.1 --port 8081 --ctx-size 4096 --gpu-layers auto`.
- The server listened at `http://127.0.0.1:8081`; the runner endpoint was
  `http://127.0.0.1:8081/v1`, which resolved to
  `http://127.0.0.1:8081/v1/chat/completions` in result rows.
- `smoke-chat` passed through the existing `openai-chat` adapter with exactly
  one measured row, `ok = true`, `scoring.passed = true`, output containing
  `Paris`, and non-streaming usage fields populated.
- `runtime-sweep` passed through the existing `openai-chat` adapter with
  exactly nine measured rows, no warmup rows in `run.jsonl`, and non-null
  `timing.ttft_s`, `timing.prefill_tps`, `timing.decode_tps`, and
  `tokens.output` for every measured row. Warmup raw files were generated
  locally under `raw/` and are not committed.
- `llama-server` accepted the current streaming request shape, including
  `stream_options.include_usage`, and returned streaming usage chunks with
  prompt and completion token counts. Because each case's warmup primed the
  llama.cpp prompt cache, all nine measured `runtime-sweep` rows were warm-cache
  rows: `short` reported 103 cached / 104 prompt tokens, `medium` reported
  375 / 376, and `long` reported 810 / 811. TTFT-derived `prefill_tps` in this
  run is therefore a prompt-cache fast-path artifact, not cold prefill speed.
- No adapter behavior, request shape, result schema, CLI flags, benchmark pack
  semantics, compatibility fallback, compare command, or aggregation changed in
  this slice.

### Open Questions

- The Phase 2 OpenAI-compatible server-path question is resolved for
  `mlx_lm.server` and this Homebrew `llama-server` build: both accept
  `stream_options.include_usage`. The next useful Phase 2 slice is
  `benchpack compare`, with prompt-cache parity handled before drawing numeric
  prefill-speed conclusions across servers.
- A future compatibility slice may still be useful for older or different
  OpenAI-compatible local servers that reject `stream_options.include_usage`,
  but it is no longer blocking compare for the validated MLX and llama.cpp
  server paths.

## 2026-04-29 (Phase 2 llama-server validation blocker, rechecked; superseded)

### Changed

- Attempted the next Phase 2 `llama-server` validation slice on `atlas.local`;
  a second 2026-04-29 implementation pass on branch
  `phase2-llama-server-live-validation` rechecked the prerequisites before any
  benchmark command was run. Live benchmark execution remained blocked by
  missing local server/model prerequisites rather than by an adapter
  compatibility result.
- No `llama-server`, `llama.cpp-server`, `llama-cpp-server`, or `llama-cli`
  executable was available on `PATH`; `llama-server --help` and
  `llama-server --version` therefore failed with `command not found`.
- Local executable searches checked `/opt/homebrew/bin`, `/usr/local/bin`,
  `~/.local/bin`, `~/bin`, and `~/projects` for `llama-server`,
  `*llama*server*`, and `server`-named files. Local GGUF searches checked
  `~/.cache`, `~/models`, `~/.local/share`, `~/Library/Caches`,
  `/opt/homebrew`, `~/Projects`, and `~/projects` with `*.gguf` file globs,
  plus Spotlight `mdfind 'kMDItemFSName == "*.gguf"c'`. The second pass also
  checked Homebrew package metadata for `llama.cpp` and scanned
  `/opt/homebrew`, `/usr/local`, `~/projects`, `~/Projects`, and `$HOME` for
  executable `llama-server`-compatible binaries. Those searches found no usable
  `llama-server` executable and no `.gguf` model file.
- `ollama list` showed local Ollama tags, but those are not directly usable as
  the GGUF model file required to start `llama-server` for this validation
  slice.
- No `smoke-chat` or `runtime-sweep` `llama-server` benchmark command was run,
  because the server command, endpoint, model file, model label, and
  quantization could not be verified locally.
- The blocked run means the `llama-server` success criteria in the Validation
  section of `docs/implementation-plan.md` remain untested: `smoke-chat` still
  needs exactly one measured row with `ok = true`, `scoring.passed = true`, and
  a resolved `/v1/chat/completions` endpoint, while `runtime-sweep` still needs
  exactly nine measured rows, no warmup rows in `run.jsonl`, and non-null
  `timing.ttft_s`, `timing.prefill_tps`, `timing.decode_tps`, and
  `tokens.output` for every measured row.
- No adapter behavior, request shape, result schema, CLI flags, benchmark pack
  semantics, or compatibility fallback changed in this slice.

### Open Questions

- Superseded by the later 2026-04-29 `llama-server` validation pass above:
  this blocker no longer represents the current Phase 2 state.

## 2026-04-28 (Phase 2 MLX server-path planning)

### Changed

- Validated `mlx_lm.server` through the existing `openai-chat` adapter on
  `atlas.local` using `mlx-community/Qwen2.5-0.5B-Instruct-4bit` at
  `http://localhost:8080/v1`.
- `smoke-chat` passed with exactly one measured row, `ok = true`,
  `scoring.passed = true`, and the resolved endpoint
  `http://localhost:8080/v1/chat/completions`.
- `runtime-sweep` passed with exactly nine measured rows, no warmup rows in
  `run.jsonl`, and non-null `timing.ttft_s`, `timing.prefill_tps`,
  `timing.decode_tps`, and `tokens.output` for every measured row.
- `mlx_lm.server` accepted the current streaming request shape, including
  `stream_options.include_usage`; no `openai-chat` compatibility slice is
  needed before validating `llama-server`.
- Phase 2 now validates `mlx_lm.server` through the existing `openai-chat`
  adapter before adding any dedicated MLX adapter.
- The `mlx_lm.server` validation path is explicit: run `smoke-chat` first for
  basic OpenAI-compatible chat behavior, then run `runtime-sweep` for streaming
  TTFT, warmup, and measured repetitions.
- Added D-010 to record the durable decision that the OpenAI-compatible server
  path should be tried before a direct MLX adapter.
- Supersedes the 2026-04-26 open question about whether direct `mlx-lm` should
  start as a CLI adapter or through `mlx_lm.server`: try the server path first.
- Refines the 2026-04-26 streaming TTFT compatibility question: validate
  `stream_options.include_usage` against `mlx_lm.server` and `llama-server`,
  then add a narrow `openai-chat` compatibility mode only if needed.

### Open Questions

- Whether `llama-server` accepts `stream_options.include_usage` remains to be
  validated locally. If it rejects the option, the next slice should be a
  narrow `openai-chat` streaming compatibility mode before `benchpack compare`.

## 2026-04-27 (Phase 2 runtime-sweep pack)

### Changed

- Added the bundled `runtime-sweep` pack with `short`, `medium`, and `long`
  fixed inline chat prompts for repeated local runtime measurement.
- The pack uses `defaults.stream = true`, `defaults.warmup = 1`,
  `defaults.repetitions = 3`, `max_tokens = 128`, and `scoring.mode = "none"`.
- Documented adapter interpretation for this pack: `openai-chat` exercises
  streaming TTFT with `stream_options.include_usage`, while
  `ollama-generate` preserves Ollama native timing fields.

### Open Questions

- Compare/aggregation remains the next Phase 2 slice now that repeated
  runtime-oriented rows can be produced by a bundled pack.

## 2026-04-26 (Phase 2 warmup and repetitions)

### Changed

- `benchpack run` now gives `defaults.repetitions` runner semantics: each case
  records that many measured executions, with a top-level 1-based `repetition`
  field only when the count is greater than one.
- `defaults.warmup` now runs unrecorded warmup executions before measured
  repetitions. Warmups call the same adapter and write raw artifacts, but do not
  appear in `run.jsonl`, scoring, or `summary.md`.
- Raw artifact names preserve `raw/<case>.request.json` and
  `raw/<case>.response.json` for single-repetition packs. Multi-repetition runs
  use `raw/<case>.rep-NNN.*.json`; warmups use
  `raw/<case>.warmup-NNN.*.json`.
- The summary table keeps its existing columns and displays repeated measured
  rows as `<case>#<repetition>`.

### Open Questions

- The `runtime-sweep` pack and compare/aggregation command remain later Phase 2
  slices.

## 2026-04-26 (Phase 2 streaming TTFT)

### Changed

- `openai-chat` now honors `defaults.stream = true` by using streamed chat
  completions with `stream_options.include_usage`, measuring TTFT from request
  send to the first non-empty `delta.content` chunk, and assembling raw streamed
  output plus per-chunk wall offsets under `raw/<case>.response.json`.
- When streaming usage is reported, `openai-chat` fills `tokens.prompt`,
  `tokens.output`, `timing.prefill_tps`, and `timing.decode_tps`. The prefill
  and decode rates are TTFT-based approximations because OpenAI-compatible
  streaming APIs do not expose native runtime phase durations.
- Non-streaming `openai-chat` requests remain the default when
  `defaults.stream` is false or absent.
- Stream parse failures keep any assembled partial content in the raw response
  file for debugging, but return empty `output_text` to the reporter so failed
  partial generations are not scored as successful output.

### Open Questions

- The `runtime-sweep` pack and compare command remain later Phase 2 slices.
- Some older OpenAI-compatible local servers reject
  `stream_options.include_usage`; an explicit compatibility mode may be needed
  when validating against those servers.

## 2026-04-26 (post-review)

### Changed

- Promoted the `benchpack run ... [--force]` CLI shape and the output-directory
  collision rule (refuse-by-default, `--force` replaces, `--out` writes
  elsewhere) into `docs/specification.md`. The spec is the contract;
  `spec-log.md` only records history.
- Reporter now writes `endpoint` (the resolved URL the adapter actually called)
  alongside `adapter`/`model` in every `run.jsonl` record. Adapter return
  payload gained an `endpoint` field. Closes the gap between
  `docs/specification.md` (which already required endpoint capture) and the
  initial implementation. `docs/architecture.md` updated.
- CLI refuses to overwrite an existing run directory that already contains a
  `run.jsonl`; pass `--force` to replace it or `--out` to write elsewhere.
  Prevents the "second run on the same date+host appends to old `run.jsonl`
  while overwriting `raw/` and rewriting `summary.md` from only the current
  records" failure mode flagged in review.
- `benchpack.toml` pack and case ids must now match
  `^[A-Za-z0-9][A-Za-z0-9_-]*$`. Manifests with unsafe ids (slashes, `..`,
  empty) are rejected at load time so the reporter can use ids verbatim as
  path components. `docs/benchpack-format.md` documents the grammar.

## 2026-04-26 (afternoon)

### Changed

- Landed the Phase 1 minimal runner from `docs/implementation-plan.md`.
  - Python package `benchpack` managed with `uv`; console script
    `benchpack = "benchpack.cli:main"`.
  - `benchpack run <pack> --adapter <adapter> --model <model> [--endpoint] [--out] [--host-label]`.
  - Adapters: `openai-chat` (POST `/v1/chat/completions`, non-streaming) and
    `ollama-generate` (POST `/api/generate`, derives `prefill_tps` /
    `decode_tps` from native duration fields and preserves them under `backend`).
  - Pack loader, scoring (`none` and `contains` only — other modes parse but
    raise `NotImplementedError` per Phase 1 scope), best-effort
    macOS/Linux hardware collector, and reporter that writes
    `run.jsonl`, `summary.md`, `hardware.json`, plus `raw/`.
  - Reporter assembles the three-contributor envelope from
    `docs/architecture.md` and runs scoring before appending each `run.jsonl`
    line. Adapters do not import the pack loader, the reporter, or the
    collector.
- Recorded `uv run pytest` as the repo-level validation command in `AGENTS.md`.
- Added the `smoke-chat` benchpack at `benchpacks/smoke-chat/`.

### Open Questions

- Streaming TTFT measurement and the `runtime-sweep` pack remain Phase 2 work.
- `mlx-lm` adapter shape (CLI vs server) is still open.
- Remote Linux orchestration over SSH is still open.
- Vendoring strategy for `desktop-django-starter` content is still open.

## 2026-04-26

### Changed

- Created the initial spec for `llm-benchpacks`.
- Scoped the project around benchmark packs rather than a single hard-coded local
  LLM benchmark.
- Added Apple Silicon and small Hetzner GPU hosts as first-class targets.
- Defined initial adapters: OpenAI-compatible chat and Ollama native generate.
- Defined initial packs: smoke, runtime sweep, desktop Django wrapping,
  patch-from-failure, and tool/JSON reliability.
- Closed implementation-language and manifest-format choices: Python with `uv`
  (D-007) and TOML pack manifests (D-008).
- Defined scoring modes and per-case override semantics in
  `docs/benchpack-format.md`, and clarified the relationship between declarative
  `[scoring]` blocks and `verify/` scripts.
- Added `hardware.json` to the canonical result artifact tree.
- Split the result record into three contributions: adapter return payload
  (runtime fields), collector sample (`resources.memory_mb`,
  `resources.gpu_memory_mb`), and reporter additions (`pack.id`,
  `pack.version`, `case`, derived `total_tps`, and `scoring`). Adapters do
  not produce or read collector or reporter fields.
- Reordered the execution flow so deterministic verifiers run before
  `run.jsonl` is written; the scoring result is captured in the same record
  rather than emitted afterwards.
- Clarified that curated `run.jsonl` files may be committed alongside
  `summary.md` and `hardware.json`, matching the narrowed `.gitignore`.
- Standardized host label format on `<chip>-<form>-<memory>` (for example
  `m5-mbp-64gb`, `hetzner-gex44`).
- Narrowed `.gitignore` so only `results/*/raw/` is excluded by default; curated
  `summary.md`, `hardware.json`, and small `run.jsonl` files under `results/`
  are committable.
- Extended `AGENTS.md` "Spec And Log Discipline" to name `architecture.md`,
  `benchpack-format.md`, and `hardware-targets.md` as docs that must be updated
  when their respective contracts change.

### Open Questions

- Should direct `mlx-lm` start as a CLI adapter or through `mlx_lm.server` only?
- Should remote Linux hosts be driven over SSH by the CLI, or should users run the
  CLI on the host and copy results back?
- How much of `desktop-django-starter` should be vendored into the wrap benchmark
  versus referenced as an external checkout?
