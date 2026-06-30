# Benchmark Implementation Constraints

## Problem

The benchmark tests a *submitted implementation* — code an agent writes to
cluster offers into products. To make results trustworthy and comparable, the
benchmark must constrain how that implementation is built and run. These
constraints are not about the matching algorithm's quality (that is what the
metrics measure); they are about making the test fair, reproducible, and
informative about *engineering* quality, not just leaderboard score.

This document lists the constraints we impose or reward.

## Rule-level unit tests (the core requirement)

A matcher accretes rules: "same brand and shared model token → match", "price
gap > 3× → block match", "conflicting storage size → non-match", and so on. The
failure mode of a rule-based or feature-based matcher is **regression**: adding a
new rule silently breaks a case an old rule handled. The benchmark therefore
treats independent testability of every rule as a first-class quality
expectation.

**Policy: rewarded, not gated.** Rule-level tests are *scored and surfaced in
reporting*, not a hard validity gate. A submission without them is still valid
and still produces a clustering the metrics can score; it is simply marked as
weaker engineering. This avoids rejecting an otherwise-correct matcher over test
hygiene while still rewarding the discipline that keeps a rule system from
rotting.

Concretely, a strong submission provides:

- **One isolated unit test (or more) per matching rule**, asserting the rule's
  decision on a small, named, human-readable example pair — including the case
  the rule exists to handle and at least one case it must *not* fire on.
- **Tests that pin behavior, so adding a rule cannot silently regress earlier
  rules.** The suite is the regression guard: a new rule that breaks an old
  example fails CI.
- **Rules as separately addressable units.** Each rule is a named function /
  predicate with a docstring stating what it decides and why, so a test can
  target it directly and a reviewer can read it without tracing the whole scorer
  (cf. the isolation/clarity principle: understandable and testable in
  isolation).
- **A small labeled fixture of canonical hard cases** (same-brand adjacent
  models, unit-variant pairs, cross-language titles, terse titles) that the suite
  runs against, so the matcher's behavior on the known-hard categories is
  asserted, not assumed.

This mirrors Magellan's view of EM as a workflow with debugging and per-component
testing (`../literature.md` Tier 1), and it is what keeps an incrementally-built
rule system from rotting.

## Determinism and reproducibility

- **Deterministic output.** Same input → same clustering. Seed any randomness
  (ANN, sampling, tie-breaking) and document the seed. Non-determinism makes
  scores unrepeatable and uncomparable.
- **Pinned environment.** Standard-library-only lanes forbid external deps;
  dependency-enabled lanes pin versions. The build/run command is fixed (see
  `../index.md` program interface).
- **Regenerable fixture.** The data the implementation reads is a committed
  derived fixture plus a generating script and snapshot/manifest, never a live
  fetch (`../dataset-sourcing-analysis.md`).

## Anti-leakage

- Hidden labels stay verifier-side; never copied into the workspace.
- No network access during a run.
- No hardcoding of test ids or labels; no reading verifier files.
- Structured catalog identifiers (GTIN/EAN and any reliable MPN field) are
  **filtered out of the offer data before the benchmark**, so the learned
  pipeline cannot shortcut a reliable identifier into a `GROUP BY` lookup
  instead of resolving entities (signals.md, pair-scoring.md). In-title model
  tokens are kept — they are noisy and part of the task. Any identifier-only
  lookup ceiling lives in a separate, clearly labeled baseline lane, never in the
  matching lanes.
- The verifier rejects malformed CSVs, missing/duplicate/unknown ids, non-finite
  scores, empty patches, process failures, and timeouts.

## Stage decomposition

The implementation should expose the pipeline stages (blocking → scoring →
clustering) so each is measurable, not fused into one opaque pass:

- Optionally write a **candidate-edge file** so the verifier can compute blocking
  pair completeness / reduction ratio directly (blocking.md) and recompute
  transitivity violations (clustering.md).
- Optionally write **pair scores** for the eval sample so the scorer is
  measurable in isolation (pair-scoring.md, evaluation.md).
- Optionally write a flat-scalar **`metrics.json`** with per-stage timing and
  counters; the verifier validates derived values rather than trusting all
  reported numbers (`../literature.md` systems metrics).

Stage decomposition is rewarded but not mandated for a minimal valid submission;
a fused matcher still runs, it just earns no stage-level systems credit.

## Resource budgets

Per-lane caps make impractical algorithms fail rather than win on score
(`../literature.md`):

- **Memory cap** per lane (e.g. 512 MB tiny → 8–16 GB medium). Dense `n×n` score
  matrices are acceptable only on the tiny lane and must be called out.
- **Timeout** per lane.
- **Hard gates before combined scoring:** invalid output → 0; quality below a
  floor → capped; blocking recall below a floor → capped; memory/timeout exceeded
  → fail/cap.

## How we measure compliance

- Presence and pass-rate of the rule-level unit tests (a submission without them
  is weaker engineering even at equal score).
- Determinism check: run twice, compare output.
- Leakage checks enforced by the verifier (above).
- Systems metrics computed by wrapping the process (RSS sampler, wall clock) and
  by validating any self-reported `metrics.json` against verifier-owned counts.

## Benchmark implications

- Reward submissions that ship a rule-test suite and a hard-case fixture; treat
  their absence as a quality signal in reporting, not just a pass/fail.
- Keep at least one standard-library-only lane so from-scratch engineering is
  tested, plus dependency-enabled lanes for embedding/cross-encoder approaches.
- Document the anti-leakage stance honestly: external-agent runs are
  benchmark-grade only when the wrapper prevents broad filesystem access, else
  flag the result as weaker anti-cheat evidence (`../index.md`).

## Open questions

- Exact scoring weight for the rule-test signal (decided: rewarded, not a
  validity gate — see policy above; the remaining question is how much it counts
  toward the engineering-quality portion of reporting).
- The canonical hard-case fixture contents and size.
- How strictly to enforce stage decomposition vs accept a fused matcher with
  reduced systems credit.

## References

- Konda et al., *Magellan*, PVLDB 2016 — EM as a tested, debuggable workflow;
  `../literature.md` Tier 1.
- `../literature.md` — systems metrics, combined score, hard gates.
- `../index.md` (benchmark) — current anti-leakage rules and program interface.
