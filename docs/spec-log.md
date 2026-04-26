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
