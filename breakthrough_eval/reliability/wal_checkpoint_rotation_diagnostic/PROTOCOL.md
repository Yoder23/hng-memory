# WAL checkpoint/rotation intervention diagnostic protocol

## Question and boundary

The preceding controlled study proved that uncontrolled shared WAL growth adds
one 32-KiB WAL-index mapping Section to every client. This protocol tests a
specific operational treatment: short worker-connection epochs followed by a
fully quiescent `PRAGMA wal_checkpoint(TRUNCATE)` before replacement clients
start.

This is bounded intervention evidence only. It cannot make the failed sustained
run pass or qualify HNG, storage recovery, or production reliability.

## Frozen execution

The exact wrapper, protocol, storage implementation, queue-safe worker harness,
and successful mechanism result are SHA-256 pinned in `PREPARED.json`.
Execution requires a clean worktree whose `HEAD` and `origin/main` equal the
full supplied preregistered commit. Existing output targets are never
overwritten.

Use fresh databases with 1,000 seed records, 100 tenants, four writers, eight
readers, and one-second independent sampling:

1. Run one untreated shared condition for 120 seconds. Each child must produce
   at least 100 samples.
2. Run two independent treatment replications. Each contains four 30-second
   worker epochs. Every epoch starts 12 fresh connections, requires at least 25
   samples per child, stops all clients at operation boundaries, and then runs
   a TRUNCATE checkpoint from the sole coordinator connection before starting
   the next epoch.

All reports and exits, type snapshots, reader integrity checks, SQLite
`quick_check`, row count, and generation must be exact. Record per-epoch handle,
Section, WAL/SHM, operation, checkpoint, and identity evidence.

## Frozen decision

Return `SUPPORTS_ROTATE_CHECKPOINT_WAL_BOUNDING` only if:

- the untreated baseline reaches at least 300 handles in one process and gains
  at least 60 median SHM units;
- every treatment epoch stays below 300 handles per process and gains no more
  than 40 Section handles in any child;
- every TRUNCATE checkpoint reports `busy=0` and leaves at most 32,768 WAL
  bytes;
- both treatment databases finish with `quick_check=ok` and exact equality of
  row count, evidence generation, seed records plus reported writes;
- all worker and reader-integrity validity controls pass; and
- each treatment retains at least 50% of untreated total-operation throughput.

Any validity or identity failure is `INVALID`; every other valid result is
`INCONCLUSIVE`. Preserve the exact outcome and never retry this protocol.
