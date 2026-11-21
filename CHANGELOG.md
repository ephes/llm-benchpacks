# Changelog

## Unreleased

- Accept up to 64 KiB of UTF-8 from a regular Linux `/etc/os-release` target.
  Missing or invalid release metadata leaves the distribution unknown.

- Keep hardware probe results and attempt all handle closures and child reaping
  when a selector or pipe close fails.

- Reject agent-wrap datasets that change in place or return incomplete bytes
  during admission, before writing to the registry.

- Reject incomplete `run.jsonl` reads before admitting rows or a digest, even
  when the last row read is valid JSON.

- Sync static registry sites before retiring the previous generation. Retain
  the backup when the new site is visible but the parent sync fails.

- Load registry duplicate groups and their members in one ordered query.

- Refuse report sidecars from a replacement result directory after admitting
  `run.jsonl`. Open hardware and runtime metadata relative to the verified
  directory descriptor, and fail the report with a clear refusal when either
  sidecar is a symlink.

- Sync each complete `run.jsonl` append and its directory entry before the
  first receipt for that file. Preserve visible rows on sync failure and
  refuse further appends and summaries from that reporter.

- Reject duplicate JSON object members at every depth in hardware sidecars
  read by `benchpack report`.

- Report hardware sidecar I/O, UTF-8, and JSON parser-limit failures as
  controlled `benchpack report` errors.

- Show the missing-value marker in reports when there are no pack version
  entries.

- Treat optional run metadata that disappears before opening as missing in
  reports. Explicit metadata inputs and other read errors still fail.

- Reject symlinks, directories, and other special destinations before the
  standalone run metadata writer stages output or copies permissions.

- Preserve standalone run metadata publication errors when temporary-file
  cleanup also fails, and report the cleanup failure in an exception note.

- Reject comparison and report summaries above 100,000 run/case rows before
  expansion, counting placeholders for missing cases.

- Report unreadable `run.jsonl` inputs as controlled errors in `benchpack compare`
  and `benchpack report`.

- Reject NaN and infinity in collected hardware telemetry before output
  creation or model calls, and again before publishing `hardware.json`,
  preserving any previously published hardware artifact.

- Refuse further appends and summaries when closing an output descriptor fails
  after a complete `run.jsonl` append.

- Classify both paths in Git renames when reporting repo-task source mutations.

- Write strict JSON to `run.jsonl`. Record nonfinite optional telemetry as
  `null` and reject other nonfinite values before appending.

- Retire example HTTP timers, responses, connections and detached sockets
  independently. Bound timer joining, stop socket traffic despite stream-close
  faults, preserve initiating errors/interrupts with private cleanup categories,
  and refuse success when cleanup remains uncertain.

- Bound the complete example HTTP call, including system DNS, all TCP attempts
  and TLS negotiation, under one deadline. Keep at most four outstanding resolver
  jobs per process, retain admission after caller timeout and never let abandoned
  resolution send request data.

- Isolate core Ollama/OpenAI HTTP client cleanup faults per case. Preserve the
  primary transport/HTTP/parse/incomplete-stream failure; cleanup-only failure
  returns `client cleanup error` without output or token/rate/TTFT credit, so
  subsequent cases can still record results. Exception text remains private.

- Keep Ollama URL userinfo, query/fragment credentials and transport exception
  text out of portable adapter results, JSONL, reports and new registry imports.
  Preserve existing transport URL resolution and credentials.

- Bind streamed core OpenAI answers to exact integer choice index 0; accept a
  missing singleton index as 0 for local servers. Reject multiple, unexpected or
  malformed indices before retaining delta text, preserving usage-only events.

- Reject duplicate decoded JSON members recursively in core OpenAI/Ollama
  responses and OpenAI SSE events before extracting evidence. Keep bounded raw
  failure previews and fixed diagnostics, with no output/token/rate/TTFT credit.

- Refuse successful example CLI results when denied process-group signals cannot
  be confirmed absent or zombie-only. Bound membership checks; attempt all cleanup
  stages independently, preserve primary failures with a fixed uncertainty warning,
  and never signal again after reaping the leader. Identify the zombie leader by
  pid so Darwin's ESRCH from getpgid for zombies still confirms a zombie-only group.

- Own example CLI children from acquisition onward: record cancellation before
  launch, retire/reap acquired handles on interruption, and restore caller signal
  dispositions even when handler setup fails.

- Preserve example staging/publication errors and interrupts through temporary
  unlink and descriptor/stream close failures; attempt all remaining cleanup.
  Report cleanup residue separately without changing successfully applied edits,
  also when the caller is handling an unrelated exception. Cleanup failures also
  print a fixed stderr warning on failure paths, where example agents show only
  the primary message.

- Sync distinct held parent directories after example edit publication and
  compensation. Report uncertain publication/rollback durability explicitly,
  including a held-directory identity failure;
  retain complete visible edits after a publication acknowledgement failure,
  and note that outcome (or the rollback outcome) on an interrupt during either
  acknowledgement.

- Admit reference-agent contexts with bounded stable regular reads, duplicate-free
  JSON and exact integer version/repetition checks before artifact writes.
- Stage reference marker/log bytes together through held no-follow parents;
  refuse linked/exchanged targets and restore owned artifacts on failure, retaining
  originals on failed rollback. New artifacts are private 0600; existing modes survive.

- Preserve publication/rollback failures through lock release errors, attempt
  descriptor close after failed unlock, and fail on release-only errors. Bundle and
  site CLI errors show the fixed release notes; release-only failures are registry
  errors instead of tracebacks.

- Admit publication locks nonblocking without following links; refuse multiply
  linked or exchanged lock inodes before bundle/site output mutation.

- Send Codex example prompts through bounded stdin; bound CLI output and retire
  owned process groups on every exit. Always remove staged Pi prompts.

- Admit bounded stable regular example contexts; stream contained Pi data previews
  and cap aggregate data reads and editable-file context before agent execution.

- Keep remote/agent failure bodies out of example diagnostics and sidecars; publish
  complete private telemetry atomically through destinations owned across calls.

- Refuse duplicate example control JSON members and incomplete OpenAI edit replies,
  upstream errors and explicit model mismatches before workspace mutation; a dated
  snapshot of the requested model id still matches.

- Bound example HTTP responses by actual bytes and elapsed time; refuse redirects
  and keep credentials bound to the configured endpoint.

- Pre-encode and stage example workspace replacements; bind writes to held
  no-follow parents, refuse hardlinks/generation changes and report rollback failure
  with original backups retained; never roll back over a newer concurrent leaf.
  Admission/staging failures are edit failures with failure telemetry, not Pi
  launch errors.

- Sync artifact directories after atomic reporter/context publication; report
  visible-but-uncertain durability on sync failure and retain complete evidence.
  Shared workspace/log writes preserve that outcome instead of claiming no write.

- Admit registry JSONL and sidecars through one directory generation and reuse
  validated snapshots during database writes instead of reopening source paths.

- Refuse unstable in-place result reads before summary/hash admission or bundle
  publication; keep complete opened generations on atomic pathname replacement.
  Verifier JSON mutated during its read records `supplemental_error: read_error`.

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
