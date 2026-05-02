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
replay, prompt templating, workspace retention options, verifier
timeout/environment configuration, or bundled pack conversion. Measured
repo-task verifier execution and final verifier status landed 2026-05-02 for
`verify-script` rows only.

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
  verifier artifact paths and final verifier status landed later on 2026-05-02;
  task execution log paths remain planned.
- Implement `verify-script` execution against the disposable workspace and
  record verifier artifacts. **Landed 2026-05-02** for measured `repo-task`
  executions only: scripts run as `sys.executable <pack-relative script>` after
  patch capture, stdout/stderr and structured JSON are written under
  `verify/<case-id>/rep-NNN.*`, and result rows include `verify`, `repo_task`,
  and top-level `verify-script` scoring.
- Capture deterministic patch/diff artifacts from workspace changes. **Landed
  2026-05-02** as source-vs-workspace directory snapshot diffs written to
  `patch/<case-id>/rep-NNN.diff`, with `patch.path` recorded in measured
  repo-task rows.
- Extend result records conservatively for repo-task patch/verifier/log artifact
  paths and final status once the runner/verifier contract is implemented.
  **Partially landed 2026-05-02** for `patch.path`; verifier artifact paths and
  final verifier status also landed 2026-05-02 for `verify-script`; task log
  artifact paths remain planned.
- Integrate an agent-session harness after disposable workspace, verifier, and
  patch artifacts exist. **Planned later.**
- Add optional full agent-session replay later.

Validation:

- The pack runs on Apple Silicon and Linux without path-specific edits.

## Phase 4: Task Completion Benchmarks

Move beyond speed into correctness.

Scope:

- `patch-from-failure` pack.
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
