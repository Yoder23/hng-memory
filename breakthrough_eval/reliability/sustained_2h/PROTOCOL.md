# Sustained two-hour production-store reliability protocol

This preregistered local experiment exercises the shipped SQLiteEvidenceStore
under sustained simultaneous reader/writer load. It targets the remaining
locally testable reliability gaps after the million-write result: multi-hour
operation, repeated online backup/restore, worker rotation, and resource-growth
observations.

It is not an operating-system crash, power-loss, actual filesystem-exhaustion,
distributed-system, authentication, or production-deployment test. Graceful
worker rotation must not be described as crash recovery. Resource observations
must not be converted into a proof that no leak exists.

## Frozen environment and configuration

- Exact clean pushed preregistration commit and full source hashes required.
- Python 3.10, SQLite runtime, psutil version, platform, and CPU count recorded.
- At least 7,200 monotonic seconds of concurrent activity.
- Four independent writer processes, each with its own production-store
  connection and one durable BEGIN IMMEDIATE append transaction at a time.
- Eight independent scoped-reader processes, each repeatedly checking a frozen
  sentinel through get and tenant-scoped eligible_ids.
- WAL journal mode and synchronous=FULL, as enforced by the shipped store.
- 100 tenants and 1,000 seed records, exactly ten seed records per tenant.
- Graceful replacement of all 12 workers every 900 seconds; eight expected
  generations over the two-hour window.
- Online SQLite backup every 600 seconds while workers continue, followed by a
  second backup into a restoration database, streaming full logical-state
  digest comparison, production-store reopen, generation check, and sentinel
  check.
- A final backup/restore after workers stop must be logically identical to the
  full live database.
- Cross-process RSS, handle count, process count, database bytes, and WAL bytes
  sampled every 60 seconds through the pinned psutil runtime.
- At least 40,000,000,000 free bytes required before runtime files are created.
- Runtime SQLite files are ignored. The exclusive result and fsynced append-only
  event ledger are retained in Git.

## Frozen pass criteria

Every criterion is conjunctive:

1. Concurrent duration is at least 7,200 seconds.
2. At least 100,000 durable writes complete.
3. At least 100,000 scoped read checks complete.
4. Every worker generation reports all 12 workers, all exit codes are zero, and
   there are no worker errors.
5. There are zero missing or malformed sentinel reads.
6. At least 12 online backup/restore cycles complete and every full logical
   digest, generation, and sentinel check passes.
7. Final evidence count and generation both equal seed records plus reported
   successful writes.
8. At least 100 resource samples are retained.
9. No sampled process exceeds 1,500,000,000 RSS bytes or 1,024 handles. These
   are safety caps, not leak-detection thresholds.
10. Any exception, early worker exit, missing report, invariant failure, or
    resource-cap breach produces preserved ERROR or FAIL, never a hidden retry.

Latency uses a fixed histogram rather than retaining millions of samples.
The event ledger is flushed and fsynced for run start, worker transitions,
resource samples, and backup/restore results. The final result records the
database byte hash; each retained backup records byte size, file hash, logical
digest, generation, count, and restoration identity.

## Claim boundary

A pass would establish one bounded two-hour local run with sustained
multi-process activity, repeated backups, and sampled resources. It would not
establish mean time to failure, zero-loss durability under power interruption,
actual disk-full recovery, absence of leaks, distributed correctness, or
production readiness.
