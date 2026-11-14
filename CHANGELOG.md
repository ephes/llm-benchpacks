# Changelog

## Unreleased

- Bind harness workspace reads, writes, existence checks and deletion to opened
  directories; preserve internal file symlinks while rejecting exchanged paths.
- Limit harness text reads to 16 MiB of actual bytes and each inventory to
  100,000 visited entries; refuse special inputs and incomplete discovery.
- Publish full-file replacements from encoded sibling temporaries; preserve old
  bytes and permissions on encoding/write/flush/replace failure.
- Share one monotonic deadline across both patch checks and application.
- Refuse task-log symlinks before mutation and publish logs relative to admitted
  directories, reporting any streams already published when another fails.
- Serialize external-agent context before effects and atomically publish each
  complete JSON generation, preserving the prior file on failure.
