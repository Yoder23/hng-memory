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

A third bounded probe uses 100,000 tenant/user principals with identical semantic state, then
overlaps 10,000 scoped reader checks with 800 durable global writes:

| Measure | Result |
|---|---:|
| Total duration | 390.445 s |
| Append p50 / p95 / p99 | 3.739 / 4.486 / 8.484 ms |
| Verified restarts | 3/3 |
| Exhaustive authorized / wrong-tenant / wrong-user checks | 100,000 / 100,000 / 100,000 |
| Scoped cross-tenant / cross-user leaks | 0 / 0 |
| Matching / wrong-role / below-authority policy checks | 100,000 / 100,000 / 100,000 |
| Role / authority leaks | 0 / 0 |
| Concurrent read checks / completed writes | 10,000 / 800 |
| Pre/post-backup records | 100,800 / 100,800 |
| Pre/post logical ledger SHA-256 | identical (924dcf...2d503) |

Machine evidence is reliability/MULTI_USER_100K_ISOLATION.json. The result is explicitly bounded:
it assumes trusted tenant/user context on scoped queries, and raw get/get_many primitives are
unscoped. It is neither an authentication test nor an hours-long load result.

A preregistered high-volume probe at exact clean commit
`bc18cf4f21869c92b98b26ad79219498e532358b` performs 1,000,000 individually durable appends
against the shipped `SQLiteEvidenceStore`, with WAL and `synchronous=FULL`, across 100 tenants:

| Measure | Result |
|---|---:|
| Total duration | 4,164.902 s (69.415 min) |
| Append p50 / p95 / p99 | 3.772 / 4.728 / 13.336 ms |
| Verified restarts | 9/9 |
| Tenant counts | exactly 10,000 for each of 100 tenants |
| Supersession/invalidation checks | 100/100 and 100/100 pass |
| Pre/post-backup records | 1,000,000 / 1,000,000 |
| Pre/post logical ledger SHA-256 | identical (`5c09c3...c75aba`) |
| Generation pre/post backup | 1,000,101 / 1,000,101 |
| Database / backup bytes | 1,242,869,760 / 1,242,869,760 |

Machine evidence is `reliability/million_write/RESULTS.json`. Independent post-run SHA-256 checks
exactly match both file hashes recorded there: database `562a4e...fe08f` and backup
`d0af0e...1706e`. The runtime database and backup remain local and Git-ignored. This closes the
previously absent million-write checkpoint only. It contains one graceful close/reopen every
100,000 writes and one backup/restore cycle; it is not OS-crash, power-loss, disk-full,
multi-process, or hours/days-long concurrent-load evidence.

## What is not a soak result

Passing bounded fault tests and durability probes through one million writes is not equivalent to
an hours- or days-long production soak. The current evidence does not include:

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

## Sustained reliability attempt: interrupted failure

The attempted run is frozen under `reliability/sustained_2h/PROTOCOL.md` and
`PREPARED.json`. It required an
exact clean pushed commit, at least 7,200 seconds, four writer processes, eight
scoped-reader processes, graceful 15-minute worker rotation, at least 12 online
backup/restore cycles, and at least 100 one-minute cross-process resource
samples. Its development smoke passed with four writers, four readers, two
worker generations, and four backup/restore cycles.

The exact command ran from clean pushed commit
`d3cef83d1f4d86ab4efe1bcbaa8cf77f4b8b2ccf` and failed before qualification.
At ten minutes, the coordinator entered the first online SQLite backup while
writers continued. The backup did not complete, no backup event was recorded,
and the coordinator could not perform the scheduled 15-minute worker rotation.
At that boundary all 12 workers remained live, WAL was 10,237,227,712 bytes,
and maximum worker handles were 815. A single safety interrupt stopped all
workers before the frozen handle cap or disk floor was breached.

The wrapper exited code 1 without serializing RESULTS.json. The 13 fsynced
events and ignored runtime files are content-addressed in
`reliability/sustained_2h/INTERRUPTED.json`. Status is
`INTERRUPTED_FAIL`: zero backup/restore cycles completed, the two-hour
duration was not reached, and no soak pass is claimed. This protocol must not
be retried or overwritten.

## Failure-driven v2 prepared, not executed

V2 is frozen separately under
`reliability/sustained_2h_v2/PROTOCOL.md` and `PREPARED.json`. It tests the
general recovery correction suggested by v1: writers acknowledge a pause only
after their current transaction, scoped readers stay live, backup/restore runs
in a dedicated child with a 180-second timeout, and the parent continues
resource and disk-floor checks. All writer resumes must also be acknowledged.

The eight-process development smoke passes multiple pause/backup/restore
cycles and final logical identity. Status remains `PREPARED_NOT_EXECUTED`;
the smoke validates the harness but is not two-hour reliability evidence. A
future v2 pass would establish only write-quiesced/read-live recovery and would
not erase the uninterrupted-write v1 failure.
