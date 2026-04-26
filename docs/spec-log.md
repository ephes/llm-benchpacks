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

### Open Questions

- Should the first implementation be Python with `uv`, or a single-file Node CLI?
- Should direct `mlx-lm` start as a CLI adapter or through `mlx_lm.server` only?
- Should remote Linux hosts be driven over SSH by the CLI, or should users run the
  CLI on the host and copy results back?
- Should benchmark pack manifests use TOML, YAML, or JSON?
- How much of `desktop-django-starter` should be vendored into the wrap benchmark
  versus referenced as an external checkout?
