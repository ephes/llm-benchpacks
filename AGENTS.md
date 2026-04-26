# llm-benchpacks Agent Instructions

## Repo Intent

Build a compact benchmark runner for local LLM runtimes and coding-agent-shaped
workloads. Keep benchmark packs portable across Apple Silicon, Linux CUDA hosts,
and OpenAI-compatible local servers.

## Read First

- `README.md`
- `docs/specification.md`
- `docs/architecture.md`
- `docs/implementation-plan.md`
- `docs/benchpack-format.md`
- `docs/hardware-targets.md`
- `docs/decisions.md`
- `docs/spec-log.md`
- `docs/run-log.md`

## Working Rules

- Treat benchmark packs, specs, and result schemas as source contracts.
- Keep raw generated results out of git unless a small curated artifact is
  intentionally committed.
- Prefer deterministic scoring over LLM-as-judge. If a pack uses LLM-as-judge,
  document that explicitly in the pack.
- Do not assume Apple Silicon. Linux CUDA hosts and small GPUs such as Hetzner
  GEX44-class machines are first-class targets.
- Do not hide backend-specific metrics when they are useful. Normalize common
  fields, but preserve native Ollama, llama.cpp, MLX, or CUDA timing details.

## Spec And Log Discipline

- Update `docs/specification.md` when behavior, result schema, CLI shape, or pack
  semantics change.
- Update `docs/architecture.md` when component boundaries, adapter contracts, or
  result envelopes change.
- Update `docs/benchpack-format.md` when manifest fields, case kinds, or scoring
  modes change.
- Update `docs/hardware-targets.md` when supported targets or hardware metadata
  fields change.
- Add durable design choices to `docs/decisions.md`.
- Add dated design movement and open questions to `docs/spec-log.md`.
- Add curated benchmark outcomes to `docs/run-log.md`.
- Update documentation in the same change as implementation.

## Validation

Until the runner exists, validate documentation changes by reviewing links and
checking `git status --short`.

Once implementation starts, add a single repo-level validation command and record
it here.
