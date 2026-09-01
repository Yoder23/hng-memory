# Shared-SQLite child-handle diagnostic v2

Status before execution: **PREPARED_NOT_EXECUTED**.

This is a new diagnostic, not a retry of the preserved invalid predecessor. The
first matrix embedded sampling in each workload loop; shared-database writer
operations delayed several samplers below the frozen minimum. V2 moves sampling
to an independent thread inside every child, preserving process-local handle
measurement without coupling sample cadence to SQLite operation duration.

## Frozen matrix

The four 90-second sequential conditions are unchanged: 12 idle children, 12
per-process-isolated SQLite children, and two independent 4-writer/8-reader
shared-WAL conditions. Every condition uses fresh spawned processes. Each child
requires at least 80 one-second fsynced samples, a report, zero error, and zero
exit code; readers require zero missing or malformed checks.

## Frozen decision

The invalid predecessor descriptively observed control medians near 0.667 and
shared medians of 32.360 and 17.334 handles/minute. Those values are development
evidence only. V2 freezes a conservative replicated lower-bound rule:

- `SUPPORTS_SHARED_SQLITE_CAUSE` requires both shared medians at least 10
  handles/minute, at least 10 of 12 children in each shared condition at or
  above 10, and both the maximum idle slope and maximum isolated slope below 5;
- `SUPPORTS_PROCESS_COUNT_CAUSE` requires idle median at least 20;
- `DOES_NOT_REPRODUCE` requires every condition median below 5;
- otherwise the valid outcome is `INCONCLUSIVE`; any failed execution control
  is `ERROR/INVALID`.

The rule does not claim a specific operating-system handle type or code-level
leak. A supporting result would localize the phenomenon to concurrent shared
SQLite/WAL workload conditions and justify a narrower mechanism study. It cannot
qualify HNG, storage, recovery, production, or the failed sustained run.

## Execution

The wrapper freezes the 10-handles/minute shared lower bound as its default.

```powershell
C:\Python310\python.exe breakthrough_eval\scripts\shared_sqlite_handle_diagnostic_v2.py --prepare-only
C:\Python310\python.exe breakthrough_eval\scripts\shared_sqlite_handle_diagnostic_v2.py --preregistered-commit COMMIT
```

Execution requires exact clean pushed state and matching source/config hashes.
Outputs are exclusive and cannot be retried or overwritten.
