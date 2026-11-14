# Changelog

## Unreleased

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
