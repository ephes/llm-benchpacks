# Run Log

Curated benchmark runs should be recorded here. Raw artifacts under
`results/*/raw/` are ignored by default; a curated `summary.md`, `hardware.json`,
and (when small) `run.jsonl` may be committed alongside.

| Date | Host | Runtime | Model | Pack | Result | Artifacts | Notes |
|------|------|---------|-------|------|--------|-----------|-------|
| 2026-04-26 | n/a | n/a | n/a | n/a | repo created | n/a | Initial documentation scaffold only. |

## Run Entry Guidance

- Use stable host labels such as `m5-mbp-64gb` or `hetzner-gex44`. Result
  directories follow `<date>-<host-label>` (e.g. `2026-04-26-m5-mbp-64gb`).
- Include runtime version in the artifact summary.
- Record whether the model was cold or warm.
- Link to committed summaries (and `run.jsonl` when it accompanies a curated
  run), not large raw responses.
- The `Artifacts` column should hold a repo-relative path to a committed
  `summary.md` (e.g. `results/2026-04-26-m5-mbp-64gb/summary.md`). Use `local`
  when nothing was committed, or an external URL for remote-host runs whose
  artifacts live elsewhere.
- If a run is exploratory and not comparable, say that explicitly.
