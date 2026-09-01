# Long-run reliability and soak status

## Executed evidence

The immutable 0.7.0rc1 baseline passes all ten automated fault/concurrency cases:

1. process kill before commit;
2. kill after semantic-vector write;
3. kill after evidence commit;
4. kill during index rebuild;
5. competing writer processes;
6. multiple reader processes;
7. profile revision during query;
8. supersession during query;
9. invalidation during query;
10. index replacement during query.

The frozen assistant gauntlets also cover restart behavior and a 20,000-turn stream. Raw command,
stdout/stderr, return code, duration, and copied artifacts are preserved under
`baseline_070/raw/`; `FAULT_INJECTION_10.json` reports 10/10.

An additional bounded production `SQLiteEvidenceStore` probe writes 10,000 real evidence records
with WAL and `synchronous=FULL`, reopens after each 1,000 writes, and performs a SQLite
backup/restore:

| Measure | Result |
|---|---:|
| Total duration | 28.125 s |
| Append p50 / p95 / p99 | 2.332 / 2.971 / 7.091 ms |
| Verified restarts | 9/9 |
| Ten-tenant counts | exactly 1,000 each |
| Supersession/invalidation checks | pass |
| Pre/post-backup records | 10,000 / 10,000 |
| Pre/post logical ledger SHA-256 | identical (`1e7584...e1ded`) |
| Generation pre/post backup | 10,011 / 10,011 |

Machine evidence is `reliability/STORAGE_PROBE.json`; the 12.4 MB source and backup databases are
preserved locally but excluded from Git by the runtime-database ignore policy.

A second bounded scale probe writes 100,000 records across 1,000 tenants, reopens the production
store after each 10,000 writes, performs 200 lifecycle mutations, and backs up/restores the full
logical ledger:

| Measure | Result |
|---|---:|
| Total duration | 408.630 s |
| Append p50 / p95 / p99 | 3.710 / 5.330 / 10.326 ms |
| Verified restarts | 9/9 |
| Tenant counts | exactly 100 for each of 1,000 tenants |
| Supersession/invalidation checks | pass |
| Pre/post-backup records | 100,000 / 100,000 |
| Pre/post logical ledger SHA-256 | identical (`93c302...453c02`) |
| Generation pre/post backup | 100,101 / 100,101 |

Machine evidence is `reliability/MULTITENANT_100K_1K.json`; its runtime databases are excluded from
Git. This is 100,000 records and 1,000 tenant partitions, not 100,000 users and not a concurrency
load test.

## What is not a soak result

Passing bounded fault tests and 10,000/100,000-write durability probes is not equivalent to an hours- or
days-long production soak. The current evidence does not include:

- millions of durable evidence writes;
- repeated backup/restore cycles;
- disk-full injection;
- an operating-system crash during SQLite/fsync;
- hours of simultaneous readers/writers;
- long-run memory/file-descriptor growth;
- recovery-time distributions after repeated rebuilds.

Therefore long-run reliability remains `PARTIAL`. No mean-time-to-failure, zero-loss durability,
or production-readiness claim is made from the bounded suite.

## Required closure protocol

A qualifying soak should pin the release artifact and database schema, run at least one million
writes with deterministic checkpoints, rotate process crashes and rebuilds, verify a cryptographic
ledger after every recovery, sample RSS/file descriptors/database bytes, and retain every failure
log. Disk-full testing must use a disposable bounded volume. Backup/restore must compare the full
evidence/provenance/supersession graph, not only row counts.
