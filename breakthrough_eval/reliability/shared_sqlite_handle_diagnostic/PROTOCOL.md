# Shared-SQLite child-handle diagnostic

Status before execution: **PREPARED_NOT_EXECUTED**.

The failed sustained v2 run breached its 1,024-handle cap. A valid controlled
follow-up refuted the narrow hypothesis that separately launched orchestration
commands caused handle growth in four isolated child variants. This diagnostic
tests whether the v2-like 12-process shared-SQLite workload reproduces growth
that is absent from idle and per-process-isolated controls.

This is root-cause evidence only. It cannot qualify storage, recovery, HNG, or
the failed sustained run.

## Frozen matrix

Run four sequential conditions with fresh spawned children:

1. `idle_12`: four writer-labeled and eight reader-labeled children wait only;
2. `isolated_sqlite_12`: the same roles use independent seeded SQLite databases;
3. `shared_sqlite_12_a`: four writers and eight scoped readers share one seeded
   WAL database using the shipped `SQLiteEvidenceStore` and v2-like operations;
4. `shared_sqlite_12_b`: an independent shared-database replication.

Each condition lasts 90 seconds after all 12 children report readiness. Every
child self-samples Windows handle count, RSS, and threads once per second into a
separate fsynced JSONL ledger. There is no backup, rotation, external pulse, or
cross-condition process reuse. Each condition requires all 12 reports, zero
errors, zero nonzero exits, and at least 80 samples per child.

## Frozen analysis

For each child, handle slope is endpoint change divided by elapsed minutes.
Condition medians are calculated across 12 children.

- `SUPPORTS_SHARED_SQLITE_CAUSE` requires both shared conditions to have median
  slope at least 20 handles/minute, the two shared medians within 15
  handles/minute of each other, and both idle and isolated medians below 5.
- `SUPPORTS_PROCESS_COUNT_CAUSE` requires idle median at least 20.
- `DOES_NOT_REPRODUCE` requires every condition median below 5.
- all other valid outcomes are `INCONCLUSIVE`; any failed execution control is
  `ERROR/INVALID`.

The result may narrow root cause but never relax the sustained v2 safety cap.

## Execution

```powershell
C:\Python310\python.exe breakthrough_eval\scripts\shared_sqlite_handle_diagnostic.py --prepare-only
C:\Python310\python.exe breakthrough_eval\scripts\shared_sqlite_handle_diagnostic.py --preregistered-commit COMMIT
```

Execution requires exact clean `HEAD == origin/main == COMMIT`, matching frozen
hashes/configuration, Windows `psutil.num_handles`, and absent output targets.
Outputs are exclusive and cannot be retried or overwritten.
