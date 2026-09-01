# Sustained two-hour recovery protocol v2

This is a new experiment motivated by the preserved v1 failure at commit
d3cef83d1f4d86ab4efe1bcbaa8cf77f4b8b2ccf. It does not overwrite or retry
v1. V1 showed that an online SQLite backup invoked synchronously while four
writers continued could starve, block coordinator monitoring and worker
rotation, grow WAL beyond 10 GB, and leave no wrapper result after a safety
interrupt.

## General correction under test

The production recovery contract explicitly establishes a bounded write
quiescence window:

1. writers finish their current transaction and acknowledge pause;
2. scoped readers continue throughout;
3. backup and restore run in a dedicated child process;
4. the parent continues resource and disk monitoring;
5. the backup child has a hard timeout;
6. writers resume only after full logical backup/restore verification;
7. normal 15-minute worker rotation remains independent of backup completion.

This is a write-paused, read-live recovery test. It must not be described as a
fully online backup under uninterrupted writes, crash recovery, power-loss
recovery, actual disk-full recovery, or production readiness.

## Frozen configuration

- Exact clean pushed preregistration commit and full source hashes required.
- At least 7,200 monotonic seconds.
- Four independent writer processes and eight independent scoped-reader
  processes against the shipped SQLiteEvidenceStore.
- WAL and synchronous=FULL, 100 tenants, and 1,000 seed records.
- Graceful replacement of all workers every 900 seconds; at least eight worker
  generations.
- Backup due every 600 seconds; at least 12 cycles including a final cycle.
- Writer pause acknowledgement timeout: 30 seconds.
- Dedicated backup/restore child timeout: 180 seconds.
- Full logical digest, evidence count, generation, and sentinel validation for
  every backup and restored database.
- Final backup logical state must equal the stopped live database exactly.
- Parent resource/disk sample every 60 seconds, including while backup runs.
- At least 100 resource samples; per-process caps remain 1,500,000,000 RSS
  bytes and 1,024 handles.
- Preflight free-space floor 40,000,000,000 bytes and runtime safety floor
  30,000,000,000 bytes.
- At least 100,000 writes and 100,000 scoped reads.
- Exclusive result and fsynced event ledger; runtime SQLite files remain
  ignored.

## Conjunctive pass criteria

Every frozen threshold and invariant must pass: duration, write/read minimums,
at least eight clean worker generations, zero worker/report/read errors, at
least 12 completed backup/restore cycles, all pause acknowledgements within 30
seconds, all writer resumes acknowledged, all backup children within 180
seconds, exact final count/generation
and logical identity, at least 100 resource samples, resource caps, and runtime
disk floor.

Any timeout, early exit, missing acknowledgement/report, backup mismatch,
resource breach, disk-floor breach, exception, or final mismatch produces a
preserved FAIL or ERROR. No hidden retry is permitted.

## Claim boundary

A pass would show one bounded two-hour local run using an explicit
write-quiesced/read-live recovery contract. It would not erase the v1 failure
or establish backup progress under uninterrupted writes, mean time to failure,
absence of leaks, actual disk-full behavior, OS-crash/power-loss durability,
distributed correctness, or production readiness.
