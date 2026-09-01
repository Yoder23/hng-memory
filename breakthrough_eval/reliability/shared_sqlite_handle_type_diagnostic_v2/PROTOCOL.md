# Shared-SQLite child handle-type diagnostic v2 protocol

## Correction and boundary

The first handle-type invocation failed closed before workload start because
the operator supplied a mistyped commit hash. Its `ERROR` result is preserved
and its output directory is never reused. V2 changes only the output namespace,
source manifest, and exact preregistered commit; the workload, validity rules,
thresholds, and decision rule remain identical.

This diagnostic asks which Windows object type accounts for handle growth that
the valid predecessor matrix localized to concurrent shared SQLite/WAL
activity. It is mechanism evidence only and cannot make a failed sustained run
pass or qualify HNG, storage, recovery, or production use.

## Frozen execution

The exact committed wrappers, protocol, handle-snapshot helper, valid matrix
result, and prior preflight failure are SHA-256 pinned in `PREPARED.json`.
Execution requires a clean worktree whose `HEAD` and `origin/main` equal the
full supplied preregistered commit. Existing output targets are never
overwritten.

Run four fresh-process conditions in order for 60 seconds each: 12 idle
children; 12 children with isolated SQLite/WAL databases; and two fresh
replications of 4 writers plus 8 readers sharing one SQLite/WAL database. Each
child independently records at least 50 one-second total-handle samples.

Immediately after synchronized start and immediately after workload stop—but
before its result-queue feeder starts—each child enumerates its handle table
with `NtQuerySystemInformation(SystemExtendedHandleInformation)` and resolves
object types with `NtQueryObject(ObjectTypeInformation)`. All 48 children must
report, exit zero, meet the sample minimum, have zero type-query errors, and
produce zero missing or malformed reader checks.

## Frozen decision

Return `IDENTIFIES_DOMINANT_HANDLE_TYPE` only if all validity controls pass and:

- both shared conditions have median total-handle slope at least 10
  handles/minute and at least 10 of 12 children at or above that slope;
- the maximum total-handle slope in each control is below 5 handles/minute;
- the same object type has the largest median child delta in both shared runs;
- its median delta is at least 10 handles in each shared run;
- it accounts for at least 80% of positive median type delta in each shared
  run; and
- no control child gains more than 2 handles of that type.

If all condition medians are below 5 handles/minute, return
`DOES_NOT_REPRODUCE`. Any failed control is `INVALID`; all other valid patterns
are `INCONCLUSIVE`. Preserve the exact result regardless of outcome and do not
retry it under this protocol.
