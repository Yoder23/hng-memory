# Shared-SQLite child handle-type diagnostic protocol

## Question and boundary

The valid v2 matrix localized rising Windows process handles to concurrent
shared SQLite/WAL activity. This separate diagnostic asks which Windows object
type accounts for that growth. It is mechanism evidence only: it cannot make a
failed sustained run pass or qualify HNG, storage, recovery, or production use.

## Frozen execution

The exact committed wrapper, protocol, handle-snapshot helper, base matrix, and
predecessor result are SHA-256 pinned in `PREPARED.json`. Execution requires a
clean worktree whose `HEAD` and `origin/main` equal the supplied preregistered
commit. Existing output targets are never overwritten.

Run four fresh-process conditions in this order for 60 seconds each:

1. 12 idle children;
2. 12 children using isolated SQLite/WAL databases;
3. 4 writers and 8 readers using one shared SQLite/WAL database;
4. a fresh replication of condition 3.

Each child independently records at least 50 one-second total-handle samples.
Immediately after synchronized start and immediately after workload stop—but
before its result-queue feeder starts—the child enumerates its own handle table
with `NtQuerySystemInformation(SystemExtendedHandleInformation)` and resolves
each object type with `NtQueryObject(ObjectTypeInformation)`. The child records
the complete start/end type histograms and their delta. All 48 children must
report, exit zero, meet the sample minimum, have zero type-query errors, and
produce zero missing or malformed reader checks.

## Frozen decision

Return `IDENTIFIES_DOMINANT_HANDLE_TYPE` only if all validity controls pass and:

- both shared conditions reproduce the v2 lower bound: median total-handle
  slope at least 10 handles/minute and at least 10 of 12 children at or above
  that slope;
- the maximum total-handle slope in both controls is below 5 handles/minute;
- the same object type has the largest median child delta in both shared
  replications;
- that type's median delta is at least 10 handles in each shared replication;
- that type accounts for at least 80% of the positive median type delta in each
  shared replication; and
- no control child gains more than 2 handles of that type.

If all four condition medians are below 5 handles/minute, return
`DOES_NOT_REPRODUCE`. Any failed control is `INVALID`; all other valid patterns
are `INCONCLUSIVE`. Preserve the exact result regardless of outcome and do not
retry it under this protocol.
