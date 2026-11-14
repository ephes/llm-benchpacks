# Changelog

## Unreleased

- Bind harness workspace reads, writes, existence checks and deletion to opened
  directories; preserve internal file symlinks while rejecting exchanged paths.
- Limit harness text reads to 16 MiB of actual bytes and each inventory to
  100,000 visited entries; refuse special inputs and incomplete discovery.
