# Changelog

## Unreleased

- Admit registry JSONL and sidecars through one directory generation and reuse
  validated snapshots during database writes instead of reopening source paths.

- Refuse unstable in-place result reads before summary/hash admission or bundle
  publication; keep complete opened generations on atomic pathname replacement.

- Sample Billiger positive pairs without quadratic pools; stage and validate all
  fixture outputs, serialize writers, and preserve recovery data on rollback failure.

- Withhold quality scores for invalid cluster evidence and publish each result
  atomically with its own complete immutable PR-curve generation.

- Build cluster PR curves in one sorted sweep and compute average precision
  over whole tied-score groups, independent of CSV order.

- Bound cluster prediction/metrics reads through no-follow regular descriptors;
  refuse duplicate/nonfinite metrics JSON and oversized scalar extensions.

- Drain clusterer output with bounded tails, retire owned process groups on every
  exit, and measure sampled group RSS with explicit unavailable memory evidence;
  members or the leader exiting during a sample do not count as failed evidence.
  SIGTERM/SIGHUP to the scorer retires the candidate session before exiting.

- Reject ambiguous/nonfinite runtime metadata before execution, including nested
  extension values and oversized integer decoder failures.
- Refuse redirected reporter artifacts and exchanged output directories after
  harness execution; use no-follow regular descriptors and atomic publication.
  A symlinked `run --out` directory is refused up front with a clear message.
- Registry import and bundle checks hash exactly the admitted `run.jsonl`
  bytes instead of reopening the file by path.
- Preserve the last successful summary on write/close/replace failures. Roll back
  JSONL appends on the owned descriptor, retain primary errors on failed rollback
  and stop further append/summary operations on uncertain streams.

- Refuse duplicate result JSON members and admit `run.jsonl` through an opened
  no-follow regular descriptor before bounded comparison/import reads.

- Keep comparison medians finite and require homogeneous repetition-level
  prompt/cache counts before publishing comparable prefill speed.

- Reject duplicate members in model-output JSON and cap escaped scoring
  diagnostics at 1024 UTF-8 bytes with explicit truncation.
- Bound hardware probe output to 64 KiB, share collector deadlines, and retire
  owned process groups on success, timeout, excess output or collection failure.
  Probe cleanup never raises, so an unkillable or unreaped leader leaves the
  probe unavailable instead of aborting a benchmark run.
- Refuse mixed runtime/pack-version identities in comparisons. Use successful
  rows for metrics/cache parity and show failure counts; all-failed groups have
  unavailable metrics. Registry report/site export also refuses mixed runs;
  importing them still preserves each row identity.
- Require finite nonnegative timing/rates and exact nonnegative token counts.
  Share compare/report cumulative input limits and opened-file deduplication;
  compare requires at least two distinct inputs.

- Bound verifier JSON admission; preserve exit-code authority and previous
  evidence when atomic publication fails.
  Keep verifier output written after SIGTERM, do not wait on pipes an escaped
  descendant holds open, keep JSON permissions, and read prompts/fixtures with
  text-mode newlines as before.
- Enforce verifier log disk ceilings and shared fixture workspace/baseline work
  allowances, including growth during copying, before model/harness execution.
- Bound manifest, schema, prompt and text-fixture admission with a cumulative
  pack allowance; reject ambiguous duplicate schema members before execution.
- Bind harness workspace reads, writes, existence checks and deletion to opened
  directories; preserve internal file symlinks while rejecting exchanged paths.
  Links among the trusted base's ancestors (macOS `/tmp`, a linked home) keep
  working; new published files follow the process umask.
- Limit harness text reads to 16 MiB of actual bytes and each inventory to
  100,000 visited entries; refuse special inputs and incomplete discovery.
- Publish full-file replacements from encoded sibling temporaries; preserve old
  bytes and permissions on encoding/write/flush/replace failure.
- Share one monotonic deadline across both patch checks and application.
- Refuse task-log symlinks before mutation and publish logs relative to admitted
  directories, reporting any streams already published when another fails.
- Serialize external-agent context before effects and atomically publish each
  complete JSON generation, preserving the prior file on failure.
- Deduplicate report inputs by canonical file identity and enforce report-wide
  limits of 100 runs, 64 MiB of run bytes and 100,000 records.
- Stop external harness process groups, reap leaders and close streams on every
  exceptional exit while preserving interrupts and collection errors; the final
  group kill after a timeout tolerates macOS EPERM for an already exiting group.
