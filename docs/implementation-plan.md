# Implementation Plan

## Phase 1: Minimal Runner

Deliver a CLI that can run one benchmark case against one endpoint and write
results.

Scope:

- Python package managed with `uv`.
- `benchpack run <pack> --adapter <adapter> --model <model>`.
- `openai-chat` adapter.
- `ollama-generate` adapter.
- `smoke-chat` benchmark pack.
- JSONL run output plus Markdown summary.
- Best-effort hardware metadata on macOS and Linux.

Validation:

- Unit tests for manifest loading and result normalization.
- Smoke run against a locally reachable endpoint.

## Phase 2: Runtime Sweep

Add fixed-context performance cases that make runtime comparisons meaningful.

Scope:

- `runtime-sweep` pack with short, medium, and long prompt cases.
- Streaming TTFT measurement for OpenAI-compatible endpoints.
- Ollama native timing extraction.
- Warmup and repetitions.
- Compare command that reads multiple result directories.

Validation:

- Same pack can run against `mlx_lm.server`, `llama-server`, and Ollama.

## Phase 3: Desktop Django Workload

Add the first real coding-agent-shaped workload.

Scope:

- Import or generate the `desktop-django-starter` resolved wrap prompt.
- Include a compact target-repo snapshot fixture.
- Add deterministic constraints for short output comparison.
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
