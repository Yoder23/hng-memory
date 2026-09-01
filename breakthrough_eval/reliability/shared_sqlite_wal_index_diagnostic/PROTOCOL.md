# Shared-SQLite WAL-index Section-mapping diagnostic protocol

## Question and boundary

The valid predecessor identified Windows `Section` objects as 94.1% of positive
median handle growth in two shared SQLite/WAL replications. Official SQLite
documentation says each client memory-maps the database's `-shm` WAL-index in
32,768-byte units. This protocol tests the frozen hypothesis that each child's
Section growth matches growth in those WAL-index units.

This is mechanism evidence only. It cannot reverse the failed sustained run or
qualify HNG, storage, recovery, or production use.

## Frozen execution

The exact wrappers, protocol, primary-source basis, handle helper, valid
predecessor result, and base matrix are SHA-256 pinned in `PREPARED.json`.
Execution requires a clean worktree whose `HEAD` and `origin/main` equal the
full preregistered commit. Existing targets are never overwritten.

Run the same four 60-second fresh-process conditions as the valid handle-type
diagnostic: 12 idle children; 12 isolated SQLite/WAL children; and two fresh
replications of 4 writers plus 8 readers sharing one database. Retain the
queue-safe report-before-join ordering. Every child records at least 50
independent handle samples, start/end handle-type histograms, and start/end
database, WAL, and SHM file sizes before closing its connection. SHM sizes are
also expressed as 32,768-byte units.

All 48 children must report, exit zero, have zero handle-query or workload
errors, and produce zero missing or malformed reads.

## Frozen decision

Return `IDENTIFIES_WAL_INDEX_SECTION_MAPPING` only if:

- the predecessor handle-type rule independently returns
  `IDENTIFIES_DOMINANT_HANDLE_TYPE` in this run;
- both shared replications have a median SHM-unit delta of at least 10;
- in both shared replications, median Section delta equals median SHM-unit
  delta and every child's absolute difference is at most 1;
- idle and isolated controls have zero median Section growth and zero or
  inapplicable median SHM-unit growth; and
- every observed SHM byte size is an exact multiple of 32,768.

Any failed validity control is `INVALID`; every other valid pattern is
`INCONCLUSIVE`. Preserve the exact result regardless of outcome and never retry
it under this protocol.
