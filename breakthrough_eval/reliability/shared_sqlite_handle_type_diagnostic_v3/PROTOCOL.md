# Shared-SQLite child handle-type diagnostic v3 protocol

## Correction and boundary

V2 preserved an invalid queue-transport result: the parent joined children
before draining their enlarged handle-type reports, so three child queue feeders
blocked and were terminated in every condition. V3 changes only report
collection order. The parent drains reports concurrently after signaling stop,
then joins children against one shared timeout. Workload, process counts,
sampling, handle enumeration, thresholds, and the frozen decision are unchanged.

This remains a Windows handle-type mechanism diagnostic only. It cannot make a
failed sustained run pass or qualify HNG, storage, recovery, or production use.

## Frozen execution

The exact committed wrappers, protocol, handle-snapshot helper, valid shared
SQLite matrix, and invalid V2 result are SHA-256 pinned in `PREPARED.json`.
Execution requires a clean worktree whose `HEAD` and `origin/main` equal the
full supplied preregistered commit. Existing targets are never overwritten.

Run four fresh-process conditions in order for 60 seconds each: 12 idle
children; 12 children with isolated SQLite/WAL databases; and two fresh
replications of 4 writers plus 8 readers sharing one SQLite/WAL database. Each
child records at least 50 independent one-second handle samples and start/end
Windows object-type histograms. All 48 children must report, exit zero, have
zero handle-type query errors, and produce zero missing or malformed reads.

## Frozen decision

Return `IDENTIFIES_DOMINANT_HANDLE_TYPE` only if all controls pass and:

- both shared runs have median total-handle slope at least 10 handles/minute
  and at least 10/12 children at or above that slope;
- each control's maximum total-handle slope is below 5 handles/minute;
- the same object type dominates both shared runs;
- its median delta is at least 10 handles in each shared run;
- it accounts for at least 80% of positive median type delta in each shared
  run; and
- no control child gains more than 2 handles of that type.

If all condition medians are below 5 handles/minute, return
`DOES_NOT_REPRODUCE`. Any failed control is `INVALID`; all other valid patterns
are `INCONCLUSIVE`. Preserve the exact result regardless of outcome and do not
retry it under this protocol.
