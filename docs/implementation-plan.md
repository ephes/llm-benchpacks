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
schemas.

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
  default when absent. CLI flags, task timeout configuration, and broader
  timeout policy remain planned.
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
  semantics, or result schema changes.
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
- Add the first bundled measured repo-mutating repo-task pack over the fenced
  unified-diff contract. **Landed 2026-05-02** as `patch-from-failure`: one
  tiny Python repo fixture, one `fix-greeting` measured `repo-task` case,
  `defaults.warmup = 0`, `defaults.repetitions = 1`, a prompt that requires a
  fenced `diff` block, and a stdlib `verify-script` that checks the patched
  workspace.
- Integrate a production agent-session harness after disposable workspace,
  verifier, and patch artifacts exist. **Partially landed 2026-05-03** as an
  internal executor path for runner-side callers only. Public harness
  selection, external coding-agent integration, and richer harness
  configuration remain planned later.
- Add richer task status/reporting only if a real harness proves the existing
  task logs and runner-failure boundaries are insufficient. **Planned later.**
- Add repo-task warmup support, workspace cleanup/retention options, task
  environment support if needed, task timeout support if needed, and larger
  bundled repo-task conversion. **Planned later.**
- Add optional full agent-session replay later.

Validation:

- The pack runs on Apple Silicon and Linux without path-specific edits.

## Phase 4: Task Completion Benchmarks

Move beyond speed into correctness.

Scope:

- `patch-from-failure` pack. **Landed 2026-05-02** as the first bundled
  measured repo-mutating repo-task pack using fenced model-output diffs.
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
