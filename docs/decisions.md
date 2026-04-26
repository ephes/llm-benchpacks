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
