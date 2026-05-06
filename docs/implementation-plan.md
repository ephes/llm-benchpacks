# Implementation Plan

## Phase 1: Minimal Runner

**Status:** landed 2026-04-26. See `docs/spec-log.md` for the dated entries.

Deliver a CLI that can run one benchmark case against one endpoint and write
results.

Scope:

- Python package managed with `uv`.
- `benchpack run <pack> --adapter <adapter> --model <model>` (with
  `--endpoint`, `--out`, `--host-label`, `--force`).
- `openai-chat` adapter.
- `ollama-generate` adapter.
- `smoke-chat` benchmark pack.
- JSONL run output plus Markdown summary, with `endpoint` recorded per run.
- Best-effort hardware metadata on macOS and Linux.
- Refuse-to-overwrite collision rule on the per-run output directory.

Validation:

- `uv run pytest` (manifest loading, result normalization, scoring,
  re-run safety, adapter HTTP handling).
- Smoke run against a locally reachable endpoint.

## Phase 2: Runtime Sweep

Add fixed-context performance cases that make runtime comparisons meaningful.

**Status:** closed 2026-04-30. The planned Phase 2 implementation slices have
landed: streaming TTFT, pack-driven warmup/repetitions, the bundled
`runtime-sweep` pack, Ollama native timing extraction, MLX and llama-server
OpenAI-compatible validation, read-only compare, normalized cache metadata,
cache-aware compare reporting, prompt/cache parity context, explicit prefill
parity status, gated comparable-only prefill TPS display, and explicit
`openai-chat` streaming usage omit mode. See `docs/spec-log.md` for the dated
history. Remaining items below are preserved as validation caveats or optional
future follow-up, not blockers for Phase 2 closure.

Scope:

- `runtime-sweep` pack with short, medium, and long prompt cases. **Landed
  2026-04-27.**
- Streaming TTFT measurement for OpenAI-compatible endpoints. **Landed
  2026-04-26.**
- Ollama native timing extraction. **Implemented and tested 2026-04-26** via
  the native `/api/generate` adapter's `prompt_eval_*` and `eval_*` duration
  fields, with those backend fields preserved in result metadata.
- Warmup and repetitions. **Landed 2026-04-26.**
- Validate the `mlx_lm.server` OpenAI-compatible path through the existing
  `openai-chat` adapter. **Validated 2026-04-28.**
  - Run `smoke-chat` first to prove basic chat behavior.
  - Run `runtime-sweep` next to exercise streaming TTFT, warmup, and measured
    repetitions.
- Complete `llama-server` validation on a host with a verified
  `llama-server` binary and a suitable local GGUF instruct model. **Validated
  2026-04-29** with Homebrew `llama.cpp` 8960 and
  `Qwen2.5-0.5B-Instruct-Q4_K_M.gguf`.
- For future optional OpenAI-compatible server validation, do not run benchmark
  commands until local server/model prerequisites and server help output have
  been verified.
- If another OpenAI-compatible server rejects `stream_options.include_usage`,
  run `openai-chat` streaming packs with `--openai-stream-usage omit`.
  **Landed 2026-04-29.** This explicit compatibility mode suppresses the
  `stream_options` key while preserving streamed output and TTFT; usage-derived
  token counts and token-rate fields remain null unless the endpoint reports
  token usage another way.
- Implement `benchpack compare` over existing `run.jsonl` result directories.
  **Landed 2026-04-29** as a compact read-only median table for wall time,
  TTFT, decode TPS, total TPS, and output tokens. Before using compare output
  for prefill-speed conclusions, establish prompt-cache parity between compared
  servers, for example by disabling llama.cpp prompt cache or recording
  cached-token counts on both sides.
- Normalize backend-reported cached prompt-token counts into
  `tokens.cached_prompt` for new rows. **Landed 2026-04-29** for
  OpenAI-compatible `usage.prompt_tokens_details.cached_tokens`; missing support
  is recorded as `null`, and existing result artifacts remain historical.
- Make `benchpack compare` cache-aware without adding `prefill_tps`.
  **Landed 2026-04-29** as cached-prompt medians, cache metadata coverage, and
  deterministic warnings for incomplete metadata or differing complete cached
  prompt-token medians.
- Make `benchpack compare` prompt/cache-parity-aware without adding
  `prefill_tps`. **Landed 2026-04-29** as prompt-token medians beside cached
  prompt-token medians, plus deterministic warnings when prompt-token medians
  differ and cache parity is therefore not comparable across different prompts.
- Add a compact deterministic `prefill parity` status to `benchpack compare`
  without adding `prefill_tps`. **Landed 2026-04-29** with case-level statuses
  repeated on each run row: `missing-case`, `prompt-missing`, `prompt-diff`,
  `cache-missing`, `cache-diff`, or `comparable`.
- Add a gated `prefill_tps med` compare column. **Landed 2026-04-29** as a
  median of normalized `timing.prefill_tps` values that renders numerically only
  when the case-level `prefill parity` status is `comparable`; every
  non-comparable status renders `—`.

Validation:

- The same pack is intended to run against `mlx_lm.server`, `llama-server`, and
  Ollama. Curated Phase 2 run-log evidence currently covers `mlx_lm.server` and
  `llama-server`; a curated Ollama `runtime-sweep` live run remains useful
  optional validation if needed later.
- `smoke-chat` against `mlx_lm.server` is considered successful when it writes
  one measured row with `ok = true` and `scoring.passed = true`.
- `runtime-sweep` against `mlx_lm.server` is considered successful when it
  writes nine measured rows, no warmup rows appear in `run.jsonl`, and each
  measured row has `ok = true`, non-null `timing.ttft_s`,
  `timing.prefill_tps`, `timing.decode_tps`, and `tokens.output`.
- `runtime-sweep` against `llama-server` should use the same success criteria
  as `runtime-sweep` against `mlx_lm.server`. **Validated 2026-04-29.**
- If `runtime-sweep` does not meet that bar, capture the adapter error or
  missing fields in the run notes before choosing the compatibility slice.

Suggested local `mlx_lm.server` check:

```sh
mlx_lm.server --model <mlx-model>
uv run benchpack run smoke-chat --adapter openai-chat --model <mlx-model> --endpoint http://localhost:8080/v1 --host-label mlx-lm-smoke --force
uv run benchpack run runtime-sweep --adapter openai-chat --model <mlx-model> --endpoint http://localhost:8080/v1 --host-label mlx-lm-runtime --force
```

Use the same invocation shape against the `llama-server` OpenAI-compatible
endpoint when validating that path.

Do not add a dedicated `mlx-lm` adapter until this server-path validation shows
that the OpenAI-compatible adapter is insufficient for the measurements we need.

## Operational Track: Apple Silicon M4/M5 Comparison

Make local Apple Silicon comparisons repeatable before adding heavier remote or
production harness automation.

**Status:** started 2026-05-03. The first runbook/SSH orchestration slice
landed in `docs/apple-silicon-m4-m5-runbook.md` as a documentation-only
workflow for local M5 runs, SSH-driven M4 Studio runs, result pullback, compare
commands, fairness checks, interpretation boundaries, and troubleshooting. The
runner can already execute useful first-pass benchmarks for this goal with
`smoke-chat`, `runtime-sweep`, `desktop-django-wrap`, and
`patch-from-failure`. The optional bundled `python-regression-fix` repo-task
pack is now available for deeper fenced-patch signal, but it is not part of the
default four-pack matrix. Apple host model metadata and report-ready matrix
guidance have also landed. A read-only Markdown report generator also landed to
assemble run-log and comparison-note skeletons from existing result
directories while reusing compare median, warning, cache-row, and
`prefill parity` semantics. A narrow user-supplied runtime metadata slice also
landed: `benchpack run --run-metadata <json-file>` persists a small
`run-metadata.json` artifact and `benchpack report` includes it when present.
The narrow report-set manifest follow-up also landed: `benchpack report --set
<manifest.toml>` expands a source-only TOML list of existing result directories
into the same read-only report pipeline. Remaining work is deeper live
benchmark interpretation, production external harness execution, and larger
repo-task packs, not benchmark semantics.

Scope:

- Add a local/SSH benchmark runbook for comparing this local M5 Max machine
  against the M4 Max Studio over SSH. **Landed 2026-05-03** in
  `docs/apple-silicon-m4-m5-runbook.md`, covering prerequisite checks, repo
  sync, `uv sync`, runtime/server startup assumptions, benchmark commands,
  host labels, result directory naming, artifact pullback, and
  `benchpack compare` invocation.
- Keep the first workflow manual or script-assisted, not a broad remote
  orchestration framework. Do not add live benchmark result artifacts or
  ignored `results/*/raw/` payloads to git.
- Define a recommended first comparison matrix. **Landed 2026-05-03** in the
  runbook:
  - `smoke-chat` for endpoint sanity
  - `runtime-sweep` for TTFT, throughput, prompt-token, cached-token, and
    prefill-parity comparison
  - `desktop-django-wrap` for prompt-only coding-agent-shaped behavior
  - `patch-from-failure` as the current tiny repo-mutating verifier-backed
    smoke task
- Add fairness notes for same model, quantization, runtime path, endpoint
  options, context/cache settings, power mode, thermal state, and background
  load. **Landed 2026-05-03** in the runbook. Treat M4-vs-M5 conclusions as
  invalid when those are not aligned or clearly documented.
- Audit Apple Silicon hardware/runtime metadata. **Landed 2026-05-03** as a
  narrow `hardware.json` host-metadata improvement: Darwin collection now
  records optional `hardware_model`, `hardware_model_name`, and
  `hardware_model_identifier` fields when macOS reports them, and uses
  `SPHardwareDataType` as a fallback for chip, core count, and memory when
  `sysctl` output is generic or unavailable. The audit confirmed that runtime
  versions, server command, model checksum, quantization, context size,
  power/thermal state, and cache settings should remain explicit run-note
  responsibilities for now rather than broad runtime discovery.
- Document result interpretation boundaries: `runtime-sweep` is ready for
  performance comparison now; `desktop-django-wrap` is prompt-only;
  `patch-from-failure` is useful as a tiny repo-task smoke benchmark; and
  `python-regression-fix` is an optional deeper fenced-patch repo-task pack.
  Larger coding-agent conclusions should wait for production external harness
  support and more curated repo-task evidence. **Updated 2026-05-05** in the
  runbook.
- Add benchmark matrix and reporting polish before live M4/M5 runs.
  **Landed 2026-05-03** in the runbook as a comparison report checklist and
  compact report skeleton that separates `hardware.json` host identity from
  manually captured runtime/model/cache/power notes, calls out result
  directories, records compare warnings and prefill parity statuses, and keeps
  per-pack interpretation boundaries explicit.
- Add a read-only report generator to reduce manual run-log/report assembly
  after paired M4/M5 runs. **Landed 2026-05-03** as `benchpack report`, which
  loads existing result directories, includes optional `hardware.json` host
  identity, summarizes adapter/model/endpoint and scoring pass/fail counts, and
  reuses compare helpers for medians, warnings, cache rows, and
  `prefill parity`.
- Add structured user-supplied runtime/run metadata capture for benchmark
  result directories. **Landed 2026-05-03** as
  `benchpack run --run-metadata <json-file>`, which validates a permissive JSON
  object, writes `run-metadata.json` beside `hardware.json`, includes compact
  metadata in `summary.md`, and teaches `benchpack report` to render runtime,
  model, operating-condition, and notes fields when present. This remains
  explicit user input rather than runtime autodiscovery, and it does not change
  adapter schemas, result row fields, compare behavior, or pack semantics.
- Add a tmux-assisted matrix helper for the metadata-backed run workflow.
  **Landed 2026-05-05** as `scripts/benchpack-tmux-matrix`, a narrow dry-run
  and launch wrapper that assembles existing `benchpack run` commands for the
  default M4/M5 matrix, requires `--run-metadata`, maps pack names to stable
  host-label suffixes, and keeps `--force` opt-in. It is not a remote
  orchestration framework and does not change benchmark semantics.
- Add a compact durable summary for the completed Qwen3.6 M4/M5 benchmark
  sweep. **Landed 2026-05-05** as
  `docs/qwen36-m4-m5-benchmark-summary.md`, which summarizes the host/runtime/
  model matrix, runtime-sweep median total TPS, scoring outcome, interpretation
  caveats, and ignored result-directory patterns without committing generated
  result artifacts.
- Add a narrow report-set manifest for repeated report assembly. **Landed
  2026-05-05** as `benchpack report --set <manifest.toml>`, which loads a
  source-only TOML manifest with `version = 1` and `result_dirs = [...]`,
  resolves relative entries against the manifest location, and feeds the
  existing read-only report renderer without running benchmarks or mutating
  result directories.

Suggested implementation handoffs:

- Runbook / SSH orchestration slice: make the local-M5 plus SSH-to-M4 workflow
  repeatable without changing benchmark semantics. **Landed 2026-05-03** as
  documentation only.
- Hardware / runtime metadata audit slice: verify and, if necessary, improve
  Apple Silicon metadata capture for comparable result interpretation.
  **Landed 2026-05-03** with optional Apple host model metadata in
  `hardware.json`; runtime parity remains documented through run notes.
- Benchmark matrix / reporting polish slice: document the recommended matrix,
  compare commands, caveats, and result-reading guidance. **Landed 2026-05-03**
  as documentation only.
- Reporting generator slice: produce pasteable Markdown from existing result
  directories without writing artifacts or changing benchmark semantics.
  **Landed 2026-05-03** as `benchpack report`.
- Runtime metadata capture/reporting slice: persist explicit user-supplied
  runtime, model, and operating-condition metadata as a small result artifact
  and include it in reports without probing servers or changing compare.
  **Landed 2026-05-03** as `run-metadata.json`.
- Tmux metadata matrix helper slice: make the next metadata-backed local or
  SSH-launched benchmark matrix easier to dry-run and start in tmux while
  leaving result generation and reporting in the existing CLI. **Landed
  2026-05-05** as `scripts/benchpack-tmux-matrix`.
- Report-set manifest slice: let repeated comparison reports name their
  existing result directories once without changing report output or writing
  generated report artifacts. **Landed 2026-05-05** as `benchpack report
  --set`.

Validation:

- Documentation-only changes should pass link/path review and
  `git status --short`.
- If helper scripts are added, run their dry-run or unit-test path and
  `uv run pytest`.
- Do not run live M4/M5 benchmarks as part of implementation validation unless
  explicitly requested; curated benchmark outcomes belong in `docs/run-log.md`.

## Phase 3: Desktop Django Workload

Add the first real coding-agent-shaped workload.

**Status:** started 2026-04-29 with the bundled `desktop-django-wrap` pack.
The first slice is prompt-only: two prompt-file-backed static chat cases ask for
concise wrapping plans. Prompt-file loading landed 2026-04-29 so longer static
prompts can live under pack-local `prompts/` directories. Static fixture
metadata loading and one portable synthetic `desktop-django-wrap` fixture
landed 2026-04-29. Case-level fixture refs landed 2026-04-30 as metadata-only
links from cases to top-level fixture ids. Fixture-backed prompt assembly for
referenced file fixtures landed 2026-04-30, appending file fixture contents to
loaded case prompts with stable delimiters while leaving directory fixtures
metadata-only. A compact pack-local synthetic Django repo snapshot directory
fixture landed 2026-04-30 as metadata only. Deterministic `regex` scoring and a
short fixed output skeleton for `desktop-django-wrap` landed 2026-04-30. A
docs-first repo-task contract design landed 2026-04-30, defining disposable
workspace, directory fixture, artifact, verifier, and mutation-isolation
semantics before implementation. Measured repo-task workspace preparation
landed 2026-05-01: each measured execution copies exactly one referenced
`kind = "repo"` directory fixture into `workspace/<case-id>/rep-NNN/` under the
run output directory, while repo-task warmups are rejected. Measured repo-task
workspace metadata landed 2026-05-01. Deterministic patch capture landed
2026-05-02: each measured repo-task execution writes
`patch/<case-id>/rep-NNN.diff` and records `patch.path`. Phase 3 does not yet
include fixture execution, repo mutation by a task harness, agent-session
replay, prompt templating, workspace retention options, task environment
configuration, or broader bundled pack conversion. Measured repo-task
verifier execution and final verifier status landed 2026-05-02 for
`verify-script` rows only. A fixed-default runner-owned verifier subprocess
timeout landed 2026-05-02 so measured verifier hangs become completed failed
rows instead of runner hangs, and manifest-configurable verifier timeout via
`scoring.timeout_s` landed 2026-05-02 while preserving the `300.0` second
default. Manifest-configurable verifier environment support via
`scoring.environment` landed 2026-05-02 for measured `repo-task`
`verify-script` executions, overlaying string entries onto the inherited
verifier subprocess environment without adding CLI flags or result fields.
Deterministic no-op task log artifacts landed 2026-05-02: each measured
repo-task execution writes empty
`task/<case-id>/rep-NNN.stdout.log` and
`task/<case-id>/rep-NNN.stderr.log` files and records `task.stdout_path` and
`task.stderr_path`. Fenced model-output patch application landed 2026-05-02:
for measured repo-task executions, the runner extracts the first fenced `diff`
or `patch` block from model output, applies it as a unified diff inside the
prepared workspace, logs the task-phase outcome, then captures the
source-vs-workspace patch and runs any verifier. Full agent harness
integration and manifest task command execution remain planned. The first
bundled measured repo-mutating repo-task pack, `patch-from-failure`, landed
2026-05-02 as a narrow fixture/prompt/verifier slice over that fenced diff
contract. An internal repo-task task-executor boundary landed 2026-05-03 around
the existing fenced model-output patch phase, preserving behavior while keeping
full agent-session harness integration planned for a later slice. A docs-first
internal agent-session harness contract landed 2026-05-03, specifying the
future harness input shape, write boundaries, task log relationship, patch and
verifier ordering, and adapter/result boundary constraints without implementing
the harness or adding public manifest, CLI, adapter, artifact, or result schema
surface. The first narrow internal agent-session harness path landed
2026-05-03 behind `run_repo_task_executor`: runner-side callers can supply a
harness that receives the prepared workspace and deterministic task log paths,
mutates only the prepared workspace through validated helpers, writes the
existing task logs, and leaves patch capture, verifier execution, current CLI
defaults, adapter schemas, and result row shapes unchanged. A narrow internal
read-helper slice landed 2026-05-03 on the same request shape, giving harnesses
a validated workspace-relative UTF-8 text read helper alongside the existing
write helper without adding public harness selection or changing adapter/result
schemas. Internal workspace discovery helpers landed 2026-05-03: runner-side
harnesses can list deterministic sorted workspace-relative POSIX file paths and
check whether candidate regular files exist, still without public harness
selection, CLI flags, manifest fields, or adapter/result schema changes.
Symlinks to regular files are treated as file entries only when their targets
resolve inside the prepared workspace. An internal workspace file-delete helper
landed 2026-05-03: runner-side harnesses can remove existing regular files and
in-workspace symlink-to-file entries through the same workspace boundary, with
missing paths and directories returning false and unsafe paths remaining runner
failures before task logs are recorded. An internal workspace directory
discovery helper landed 2026-05-03: runner-side harnesses can list
deterministic sorted workspace-relative POSIX directory paths, including nested
directories created earlier in the same harness invocation, excluding the
workspace root, files, and symlinks including symlinks to directories. A
docs-first public harness selection contract landed 2026-05-03 without
implementation: future repo-task cases may explicitly declare
`harness = { id = "..." }`, absence keeps the current fenced `diff`/`patch`
executor default, and public selection must not change adapter schemas, result
row shapes, raw artifact paths, task log paths, patch/verifier ordering, or
repo-task warmup rejection by default. Narrow public manifest parsing and
executor routing for `harness = { id = "fenced-patch" }` landed 2026-05-03:
the loader accepts only that public id on `repo-task` cases, the CLI routes it
to the existing fenced model-output `diff`/`patch` executor, absence preserves
the same default, and external coding-agent harnesses remain future work. A
docs-first production external harness contract plus narrow task timeout
support landed 2026-05-03: future external harnesses must be explicit
case-local public `harness.id` values, adapter schemas and result rows stay
unchanged by default, and optional `harness.timeout_s` now bounds the
subprocess-backed fenced task executor without adding CLI flags or production
external coding-agent integration. A follow-on docs-first production external
harness contract refinement landed 2026-05-05 after the second fenced-patch
repo-task pack: it keeps the loader unchanged, treats `external-agent` as a
provisional documentation name only, enumerates future runner-owned harness
inputs, preserves existing adapter/raw/result/report boundaries, and defines the
external harness mutation, artifact, timeout, and failure boundaries for the
next implementation slice. The first narrow subprocess-backed external harness
skeleton landed 2026-05-05 behind the same repo-task executor boundary:
runner-side callers can provide explicit argv, the runner appends context
arguments, runs the subprocess without a shell in the prepared workspace,
captures existing task stdout/stderr logs, treats completed nonzero exits and
cleanly stopped timeouts as task outcomes, and leaves patch capture, verifier
execution, manifest parsing, CLI behavior, adapter schemas, raw paths, result
rows, compare/report behavior, and the default matrix unchanged. The public
`external-agent` parser-policy lock landed 2026-05-05: a named
`PROVISIONAL_EXTERNAL_AGENT_HARNESS_ID` constant is intentionally excluded from
`KNOWN_PUBLIC_HARNESS_IDS`, parser/CLI/executor tests reference that constant
directly, and the provisional id remains rejected at all three layers without
adding production external coding-agent execution. The first narrow public
`external-agent` repo-task harness slice then landed 2026-05-05: the loader now
accepts `harness = { id = "external-agent", timeout_s = ... }` on `repo-task`
cases, the CLI requires runner-owned `BENCHPACK_EXTERNAL_AGENT_ARGV` only when
such a case is selected, routes those cases to `ExternalProcessHarness`, and
keeps adapter schemas, raw paths, result rows, task log paths, patch/verifier
ordering, and fenced-patch defaults unchanged. The next narrow external-agent
context handoff slice landed 2026-05-06: public external-agent executions now
write `task/<case-id>/rep-NNN.context.json` with versioned runner-owned JSON
context and append `--context <path>` to the subprocess argv while preserving
the same adapter/result/report boundaries. The follow-up optional model-call
log path slice landed 2026-05-06: external-agent contexts now expose
`run.model_call_log_path` at
`task/<case-id>/rep-NNN.model-calls.jsonl` without requiring, parsing, reporting,
or adding that artifact to `run.jsonl`. The next recommended-shape slice also
landed 2026-05-06: docs and fake external-agent coverage now use the minimal
recommended JSONL line
`{"schema_version":1,"sequence":1,"model":"test-model","ok":true}` while
leaving the runner's treatment of the file optional and opaque. A deterministic
reference external-agent harness example also landed 2026-05-06 under
`examples/external-agent/`: it validates the public argv/context handoff,
mutates only the prepared workspace, writes one recommended model-call JSONL
line, and is covered through the public CLI external-agent path without adding
runner parsing, validation, result fields, reports, raw artifacts, manifest
commands, task environments, or production agent integration. The deterministic
model-call-shaped external-agent example then landed 2026-05-06 as
`examples/external-agent/model-call-agent.py`: it performs one tiny local HTTP
JSON request to an example-owned fake endpoint, writes the deterministic
response content only into the prepared workspace, writes one safe model-call
JSONL telemetry line to `run.model_call_log_path`, and is exercised through the
existing public CLI external-agent path while leaving runner schemas and
artifact parsing unchanged.

Scope:

- Add a prompt-only `desktop-django-wrap` starter pack derived from the
  `desktop-django-starter` wrapping workflow. **Landed 2026-04-29.**
- Add static prompt-file support and move `desktop-django-wrap` prompts under
  `benchpacks/desktop-django-wrap/prompts/`. **Landed 2026-04-29.**
- Add top-level static `[[fixtures]]` manifest metadata with pack-relative file
  and directory path validation. **Landed 2026-04-29.**
- Add one synthetic portable `desktop-django-wrap` fixture under
  `benchpacks/desktop-django-wrap/fixtures/`. **Landed 2026-04-29.**
- Add case-level `fixture_refs` metadata that validates refs against top-level
  fixture ids in the same pack. **Landed 2026-04-30.**
- Add fixture-backed prompt assembly for referenced file fixtures, preserving
  directory fixtures as metadata-only refs. **Landed 2026-04-30.**
- Include a compact target-repo snapshot directory fixture. **Landed
  2026-04-30** as a pack-local static `repo` fixture referenced by existing
  cases but not copied, executed, injected into prompts, or used to mutate a
  repository.
- Define the repo-task disposable workspace contract before implementation.
  **Landed 2026-04-30** as documentation only: source repo fixtures are
  immutable; repo-task cases copy exactly one primary `kind = "repo"`
  directory fixture into a run-owned disposable workspace; mutation is isolated
  to that workspace; expected artifacts include workspace metadata, patch diff,
  task logs, verifier output, and final status; current directory fixtures
  remain metadata-only outside repo-task execution.
- Import or generate the `desktop-django-starter` resolved wrap prompt in a
  later slice after repo-task execution support starts.
- Add deterministic constraints for short output comparison. **Landed
  2026-04-30** with executable `regex` scoring and the
  `desktop-django-wrap` `DDS_WRAP_PLAN`/fixed-label output skeleton.
- Implement disposable directory copy for one pack-owned repo fixture per
  measured repo-task execution. **Landed 2026-05-01** as runner-owned
  workspace preparation at `workspace/<case-id>/rep-NNN/`, with exactly one
  referenced `kind = "repo"` directory fixture, source fixture immutability,
  separate measured repetition copies, destination-exists failures, and
  no adapter changes.
- Add a repo-task runner skeleton that prepares workspaces and records planned
  artifact paths without changing existing chat adapter behavior. **Partially
  landed** for workspace preparation and measured workspace metadata in
  `run.jsonl` on 2026-05-01, and measured patch artifact paths on 2026-05-02;
  verifier artifact paths and final verifier status landed later on
  2026-05-02; task execution log paths landed on 2026-05-02.
- Implement `verify-script` execution against the disposable workspace and
  record verifier artifacts. **Landed 2026-05-02** for measured `repo-task`
  executions only: scripts run as `sys.executable <pack-relative script>` after
  patch capture, stdout/stderr and structured JSON are written under
  `verify/<case-id>/rep-NNN.*`, and result rows include `verify`, `repo_task`,
  and top-level `verify-script` scoring.
- Add bounded verifier subprocess execution. **Landed 2026-05-02** for
  measured `repo-task` `verify-script` executions only: the runner uses a
  fixed default verifier timeout, records timeouts as completed failed measured
  rows, keeps verifier JSON/stdout/stderr artifact paths stable, writes
  `repo_task.verify_exit_code = null`, and marks timeout JSON with
  `timed_out` and `timeout_s`. Manifest-configurable verifier timeout via
  `scoring.timeout_s` also landed 2026-05-02, preserving the `300.0` second
  default when absent. CLI timeout flags and broader timeout policy remain
  planned; narrow task timeout later landed under `harness.timeout_s`.
- Add manifest-configurable verifier environment support. **Landed 2026-05-02**
  for measured `repo-task` `verify-script` executions only: optional
  `scoring.environment` is a validated string-to-string table in the effective
  scoring table, overlaid onto the inherited verifier subprocess environment
  when declared, and omitted from `run.jsonl` result rows. CLI environment
  flags, task environment configuration, shell expansion, templating, and
  secrets handling remain out of scope.
- Capture deterministic patch/diff artifacts from workspace changes. **Landed
  2026-05-02** as source-vs-workspace directory snapshot diffs written to
  `patch/<case-id>/rep-NNN.diff`, with `patch.path` recorded in measured
  repo-task rows.
- Extend result records conservatively for repo-task patch/verifier/log artifact
  paths and final status once the runner/verifier contract is implemented.
  **Partially landed 2026-05-02** for `patch.path`; verifier artifact paths and
  final verifier status also landed 2026-05-02 for `verify-script`; task log
  artifact paths landed 2026-05-02.
- Apply model output to the prepared workspace through a narrow explicit patch
  contract. **Landed 2026-05-02** for measured `repo-task` executions only: the
  runner uses the first fenced `diff` or `patch` block in adapter output as a
  unified diff, applies it inside the prepared workspace after the adapter call
  and before patch capture, writes task stdout/stderr logs, keeps rows
  completed for missing or unapplicable patches, and leaves the adapter boundary
  and result object shapes unchanged.
- Introduce an internal repo-task task-executor boundary around the existing
  fenced model-output patch phase. **Landed 2026-05-03** without adding
  manifest fields, CLI flags, executor selection, task commands, task
  environment configuration, task timeout configuration, agent harness
  semantics, or result schema changes. Narrow task timeout later landed under
  the public harness table.
- Define the docs-first internal agent-session harness contract behind the
  repo-task executor boundary. **Landed 2026-05-03** as documentation only:
  future harness input may include the prepared workspace, case and pack
  metadata, model/adapter/endpoint/default context, output directory,
  repetition, and deterministic task log paths; writes are limited to the
  prepared workspace and run output directory; pack-owned fixtures, prompts,
  verifier scripts, source docs, adapter request/result schemas, existing
  artifact paths, and row shapes remain unchanged.
- Add the first narrow internal agent-session harness executor path behind the
  repo-task executor boundary. **Landed 2026-05-03** without adding manifest or
  CLI selection: runner-side callers can supply a harness to
  `run_repo_task_executor`; current CLI repo-task runs still use the fenced
  model-output `diff`/`patch` executor by default; task log paths and record
  shape remain unchanged; patch capture and verifier execution observe the
  harness-mutated prepared workspace.
- Add a validated internal workspace text read helper to
  `AgentSessionHarnessRequest`. **Landed 2026-05-03** without adding manifest
  or CLI selection: runner-side harnesses can read existing UTF-8 workspace
  files through the same path safety boundary used for workspace writes, while
  unsafe or unreadable paths remain runner failures before task logs are
  recorded.
- Add internal workspace discovery helpers to `AgentSessionHarnessRequest`.
  **Landed 2026-05-03** without adding manifest or CLI selection:
  `list_workspace_paths()` returns sorted POSIX regular-file paths under the
  prepared workspace, including files created earlier in the same harness
  invocation and in-workspace symlinks to regular files, and
  `workspace_file_exists(relative_path)` checks candidate files through the same
  path safety boundary as workspace reads and writes.
- Add an internal workspace file-delete helper to
  `AgentSessionHarnessRequest`. **Landed 2026-05-03** without adding manifest
  or CLI selection: `delete_workspace_file(relative_path)` removes existing
  regular files and in-workspace symlink-to-file entries through the same path
  safety boundary as workspace reads and writes, returns false for missing
  paths and directories, leaves symlink targets intact, and keeps unsafe paths
  or delete `OSError`s as runner failures before task logs are recorded.
- Add an internal workspace directory discovery helper to
  `AgentSessionHarnessRequest`. **Landed 2026-05-03** without adding manifest
  or CLI selection: `list_workspace_dirs()` returns sorted POSIX
  workspace-relative directory paths under the prepared workspace, including
  nested directories and directories created earlier in the same harness
  invocation, excluding the workspace root, files, and symlinks including
  symlinks to directories.
- Define a docs-first public harness selection contract. **Landed
  2026-05-03** as documentation only: a future explicit case-local
  `harness = { id = "..." }` table may select runner-known repo-task
  harnesses, absence keeps the fenced `diff`/`patch` executor as the
  compatibility default, selection is not inferred, and adapter schemas, result
  row shapes, task log paths, raw artifact paths, patch capture ordering,
  verifier ordering, and repo-task warmup rejection remain unchanged in this
  slice.
- Implement narrow public `fenced-patch` harness selection. **Landed
  2026-05-03** for `repo-task` cases only: manifests may declare
  `harness = { id = "fenced-patch" }`, the loader rejects malformed harness
  tables, unknown ids, extra keys, and harness declarations on non-`repo-task`
  cases, and the CLI routes explicit `fenced-patch` to the existing fenced
  model-output `diff`/`patch` executor. Absence keeps the same default fenced
  executor. No CLI flags, adapter schema changes, raw path changes, task log
  path changes, row-shape changes, task commands, task environment, task
  timeout, workspace retention, repo-task warmups, pack-level harness defaults,
  or external coding-agent integration were added.
- Define the docs-first production external harness contract and add narrow
  task timeout support. **Landed 2026-05-03** as one scoped slice: future
  production external harnesses are public repo-task harnesses selected by
  explicit case-local `harness.id`, never inferred from model, adapter,
  endpoint, fixture shape, verifier, host, or pack id. Normal adapter
  request/result schemas remain unchanged by default; harness-owned model calls
  are runner/harness concerns; task logs, raw paths, row shapes, patch capture
  after task execution, verifier execution after patch capture, source fixture
  immutability, and repo-task warmup rejection remain unchanged. The manifest
  now accepts `harness = { id = "fenced-patch", timeout_s = <positive number> }`
  for `repo-task` cases only. The timeout bounds the fenced executor's
  subprocess preflight and apply calls. Preflight timeout is a task outcome with
  unchanged workspace; apply timeout after preflight is a runner failure because
  partial mutation cannot be ruled out. Internal in-process harness callables
  reject task timeout.
- Refine the next production external harness contract after bundled
  fenced-patch coverage exists. **Landed 2026-05-05** as documentation only:
  no parser or executor behavior changed; `external-agent` is documented only as
  a provisional future id and remains rejected by the loader; future production
  harness inputs are runner-owned context such as prepared workspace, case and
  pack metadata, prompt text, output directory, repetition, task log paths,
  selected harness options, optional run metadata, and model/adapter/endpoint/
  defaults context when the harness owns model calls. External harnesses may
  mutate only the prepared workspace and write only existing task logs until a
  later artifact schema names more outputs. Existing adapter schemas, raw paths,
  result row shapes, compare/report behavior, patch capture after the task
  phase, verifier execution after patch capture, repo-task warmup rejection, and
  the default M4/M5 matrix remain unchanged.
- Add the first narrow subprocess-backed external harness runner skeleton.
  **Landed 2026-05-05** behind `run_repo_task_executor` without public manifest
  or CLI selection: runner-side callers can supply an explicit argv sequence,
  the runner appends prepared workspace, case, output directory, and repetition
  arguments, runs without `shell=True`, captures stdout/stderr to the existing
  task log paths, and keeps nonzero exits and cleanly stopped timeouts inside
  the existing task/verifier flow. Invalid harness combinations, unsafe argv,
  missing executables, invalid workspaces, and unwritable logs remain runner
  failures. At landing time, `external-agent` remained loader-rejected; the
  later public runnable slice below superseded that parser policy.
- Lock the public `external-agent` parser policy as loader-rejected.
  **Landed 2026-05-05** without changing executor or CLI behavior: a named
  `PROVISIONAL_EXTERNAL_AGENT_HARNESS_ID` constant lives alongside
  `PUBLIC_HARNESS_FENCED_PATCH` and is intentionally excluded from
  `KNOWN_PUBLIC_HARNESS_IDS`. Parser, CLI, and executor tests reference the
  constant directly: the parser error mentions both the provisional id and the
  implemented `fenced-patch` id; the CLI test proves manifest load fails before
  any adapter call or run-output directory is created; the executor test proves
  a stray `harness_id="external-agent"` raises `TaskError` without writing task
  logs and without mutating the prepared workspace. Existing fenced-patch
  defaults, internal in-process and runner-side subprocess harness paths,
  adapter schemas, raw paths, row shapes, patch/verifier ordering,
  compare/report behavior, and the default M4/M5 matrix remain unchanged. This
  policy was intentionally superseded by the following public runnable slice.
- Implement the first narrow public `external-agent` repo-task harness slice.
  **Landed 2026-05-05** with parser support for
  `harness = { id = "external-agent", timeout_s = <positive number> }` on
  `repo-task` cases, CLI loading of runner-owned
  `BENCHPACK_EXTERNAL_AGENT_ARGV` as a JSON array of non-empty strings, routing
  through the existing `ExternalProcessHarness` subprocess executor, and early
  missing/malformed argv failures before output directory creation or adapter
  calls. Direct executor `harness_id="external-agent"` remains rejected so the
  CLI owns public-to-internal routing. The normal adapter call still precedes
  the task harness phase, and no manifest command blobs, CLI task-command flags,
  task environments, raw artifact paths, result row fields, compare/report
  changes, workspace retention controls, repo-task warmups, or live benchmark
  artifacts were added.
- Add runner-owned public `external-agent` context input. **Landed 2026-05-06**
  as deterministic `task/<case-id>/rep-NNN.context.json` files plus appended
  `--context <path>` subprocess arguments. The context includes pack/case
  metadata, loaded prompt text, fixture/source workspace metadata, task log
  paths, optional run metadata path, and selected adapter/model/endpoint/
  defaults. It remains harness input only: no new manifest commands, CLI
  task-command flags, task environments, adapter fields, raw artifacts,
  `run.jsonl` fields, compare/report changes, or live benchmark artifacts were
  added.
- Expose an optional external-agent model-call log path. **Landed 2026-05-06**
  as `run.model_call_log_path` in the external-agent context, using the
  deterministic task artifact location
  `task/<case-id>/rep-NNN.model-calls.jsonl`. The runner does not pre-create,
  require, validate, parse, summarize, report, or add that file to `run.jsonl`;
  harness-owned model calls remain outside normal adapter `raw/` artifacts.
- Document a recommended external-agent model-call JSONL object shape. **Landed
  2026-05-06** as guidance and fake external-agent coverage only. The
  recommended minimal per-call line is
  `{"schema_version":1,"sequence":1,"model":"test-model","ok":true}`, with
  optional safe timing, adapter/endpoint label, token count, and short error
  fields. This did not add runner parsing, validation, summaries, reports,
  result schema fields, or normal adapter `raw/` artifacts for harness-owned
  calls, and it explicitly avoids recommending full prompts, full responses,
  request bodies, headers, environment variables, API keys, bearer tokens, or
  credentials in the default shape.
- Add a deterministic reference external-agent harness example. **Landed
  2026-05-06** as `examples/external-agent/reference-agent.py` plus usage docs
  and focused CLI coverage. The example reads the public context, validates
  core fields against the appended argv, writes only a small marker inside the
  prepared workspace and one recommended JSONL line at
  `run.model_call_log_path`, makes no live model calls, and leaves the runner's
  optional/opaque treatment of that file unchanged.
- Add a deterministic model-call-shaped external-agent example. **Landed
  2026-05-06** as `examples/external-agent/model-call-agent.py` plus usage docs
  and focused CLI coverage. The example reads the public context, performs one
  stdlib local HTTP JSON request to an example-owned fake endpoint, sends only
  case id, repetition, and model, writes the deterministic response content
  only inside the prepared workspace, and writes one safe JSONL telemetry line
  at `run.model_call_log_path`. The runner still does not parse, validate,
  summarize, report, or add that file to `run.jsonl`, and no adapter raw
  artifacts are created for harness-owned calls.
- Add the first bundled measured repo-mutating repo-task pack over the fenced
  unified-diff contract. **Landed 2026-05-02** as `patch-from-failure`: one
  tiny Python repo fixture, one `fix-greeting` measured `repo-task` case,
  `defaults.warmup = 0`, `defaults.repetitions = 1`, a prompt that requires a
  fenced `diff` block, and a stdlib `verify-script` that checks the patched
  workspace. A second bundled fenced-patch repo-task pack,
  `python-regression-fix`, landed 2026-05-05 with a small stdlib Python
  task-summary fixture, multiple edge cases, and deterministic
  `verify-script` scoring.
- Integrate a production agent-session harness after disposable workspace,
  verifier, patch artifacts, public compatibility selection, and the
  docs-first production external harness contract exist. **Partially landed**
  as an internal executor path for runner-side callers only, public
  `fenced-patch` selection for the existing compatibility executor, the
  2026-05-05 production external contract refinement, and a runner-side
  subprocess skeleton for deterministic external harness boundary tests, plus
  the first public `external-agent` CLI routing slice and optional model-call
  log artifact path plus a recommended, non-enforced model-call JSONL line
  shape. Full production external coding-agent execution, required model-call
  logging/schema/reporting, and richer harness configuration remain planned
  later.
- Add richer task status/reporting only if a real harness proves the existing
  task logs and runner-failure boundaries are insufficient. **Planned later.**
- Add repo-task warmup support, workspace cleanup/retention options, task
  environment support if needed, broader timeout/reporting policy if needed,
  and additional larger repo-task packs if current bundled fixtures remain too
  small. **Planned later.**
- Add optional full agent-session replay later.

Validation:

- The pack runs on Apple Silicon and Linux without path-specific edits.

## Phase 4: Task Completion Benchmarks

Move beyond speed into correctness.

Scope:

- `patch-from-failure` pack. **Landed 2026-05-02** as the first bundled
  measured repo-mutating repo-task pack using fenced model-output diffs.
- `python-regression-fix` pack. **Landed 2026-05-05** as a second bundled
  measured repo-mutating repo-task pack with a small stdlib Python regression,
  multiple deterministic edge cases, and the existing fenced unified-diff
  executor.
- Disposable worktree setup.
- Model output to patch extraction or agent-harness integration.
- Deterministic scoring by tests passing, diff size, and timeout.

Validation:

- A baseline model/runtime pair can solve at least one toy fixture end to end.

## Phase 5: Remote Host Orchestration

Make remote GPU runs practical.

Scope:

- Document a manual remote workflow first.
- Optional SSH runner after local execution is stable.
- Artifact pullback from hosts such as `hetzner-gex44`.
- Host labels and result comparison across machines.

Validation:

- A run from a remote Linux CUDA host can be compared with a local Mac run.
