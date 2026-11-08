# Scout round 85 resume

Branch: `r85-b05-registry-ingestion`; base: `main` at
`d83201e17bac0a3649d26e043c920096c17d6d0d`.

B05 implemented, awaiting review:

1. `benchpack-current-schema-import-no-global-rewrite`
2. `benchpack-agent-wrap-dataset-source-ownership`
3. `benchpack-bundle-total-ingestion-budget`

All three were verified present on the freshly cloned default branch. The new
synthetic regressions failed on that implementation and pass with the changes.
Targeted registry/compare tests passed (176 tests); all 12 new ingestion tests
passed after adding revision-change and multiple-bundle coverage. The full local
pytest run passed: **1,210 passed, 5 skipped** (405.48 seconds). Dependency
audit passed with no known vulnerabilities. There is no configured lint/type gate or changelog.

The mandatory `claude-review-loop` attempt used `claude-opus-5-5`, high effort,
and failed before any review with `PROVIDER_ERROR`: OAuth session expired and
could not be refreshed. No clean verdict exists. This branch is parked under the
owner's explicit authentication-failure exception; do not merge it yet.
Local artifacts are in the workspace's `reviews/b05-r1-retry/` directory.
The bundle recorded a registry diff redaction: inspect that entry and address
any false-positive redaction before accepting a future scoped verdict.

After restoring authentication, review B05 using the installed harness with
`--model claude-opus-5-5 --effort high`, a fresh run directory, and workspace
`--lock-dir` / `--ledger-dir`. Keep fixes and scoped re-reviews within the
owner's four-round/repeated-finding stopping rule. Fetch before merging; rebase
and rerun checks if origin moved. Only a clean or suggestion-only gate permits
`--no-ff` merge to main; run the full checks after merging and before pushing
main, then verify via `git ls-remote`. Do not run or wait for Actions.

Use these environment settings for local checks:

```sh
export UV_PYTHON=3.14
export UV_CACHE_DIR=/Users/jochen/workspaces/ws-cx-r85-llm-benchpacks/.cache/uv
export UV_TOOL_DIR=/Users/jochen/workspaces/ws-cx-r85-llm-benchpacks/.cache/uv-tools
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen python scripts/audit-python.py
```

B06 and B07 were not started because the owner explicitly requires stopping on
expired review OAuth. Continue in the report's bundle order, re-verifying each
slice against current main first:

- B06: `benchpack-summary-linear-case-grouping`,
  `benchpack-multipack-case-identity`, `benchpack-report-untrusted-label-escaping`.
- B07: `benchpack-outcome-patch-opened-snapshot`,
  `benchpack-report-set-bounded-decoder`, `benchpack-export-publisher-single-writer`,
  `benchpack-bundle-copy-opened-source-containment`.

Read full descriptions and validation notes in
`~/workspaces/ws-work-planning/reviews/scout-round85.md` before resuming.
No deploys, tags, releases, PRs, host access, work-app writes or remote branch
deletion. Feature pushes are permitted only to park unfinished work.
