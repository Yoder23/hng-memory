# Child-handle observer diagnostic protocol

Status before execution: **PREPARED_NOT_EXECUTED**.

This is a failure-attribution diagnostic motivated by the unproven hypothesis
in `../sustained_2h_v2/FAILURE_ANALYSIS.json`. It cannot qualify storage,
recovery, HNG behavior, or the failed v2 run. V2 remains failed regardless of
this result.

## Question

Do separately launched orchestration commands coincide with synchronized
Windows handle growth inside already-running spawned child processes on this
host?

## Frozen design

- multiprocessing start method: `spawn`;
- four self-sampling children: idle sleep, event polling, isolated SQLite read,
  and isolated SQLite write;
- one-second self-sampling to per-child fsynced JSONL logs;
- 30-second warmup;
- 120-second quiet baseline;
- 120-second external-command phase;
- 120-second quiet recovery;
- exactly 20 serial external pulse commands during the external phase;
- each pulse is a separately launched invocation of the same frozen script with
  `--pulse-ordinal N` and the exact preregistered commit;
- no pulse is accepted outside the external phase;
- no result is accepted with a missing/duplicate ordinal, fewer than 100 child
  samples per measured phase, a child error, or a nonzero child exit code.

The operator may make one observation call that waits across the warmup and
baseline to receive the `EXTERNAL_PHASE_READY` marker, then launches the 20
pulses approximately five seconds apart. After the last pulse, the operator
makes no further observation call until the main process becomes terminal.
The pulse ledger is authoritative for the exact command count and timing.

## Frozen analysis

For every child and phase, the handle slope is the endpoint change divided by
elapsed minutes, and net change is last handles minus first handles. Medians are
computed across all four children.

The diagnostic reports `SUPPORTS_OBSERVER_EFFECT` only when all validity checks
pass, the median external-phase slope is at least 20 handles/minute above both
quiet-phase slopes, and median external net growth is at least 50 handles.

It reports `REFUTES_OBSERVER_EFFECT_AT_THRESHOLD` only when all validity checks
pass, external slope differs from baseline by at most 5 handles/minute, and
median external net growth is below 20 handles.

Every other valid result is `INCONCLUSIVE`. Invalid execution is `ERROR` and is
never interpreted.

These thresholds are attribution controls, not acceptable production handle
growth and not a revision of v2's frozen 1,024-handle safety cap.

## Execution

Preparation and execution are separate. Execution requires a clean worktree,
exact `HEAD == origin/main == --preregistered-commit`, matching source/config
hashes, absent result/runtime targets, `psutil`, and Windows `num_handles`.

```powershell
C:\Python310\python.exe breakthrough_eval\scripts\handle_observer_diagnostic.py --prepare-only
C:\Python310\python.exe breakthrough_eval\scripts\handle_observer_diagnostic.py --preregistered-commit COMMIT
```

During `EXTERNAL_PHASE_READY`, launch ordinals 1 through 20 as separate serial
processes:

```powershell
C:\Python310\python.exe breakthrough_eval\scripts\handle_observer_diagnostic.py --pulse-ordinal N --preregistered-commit COMMIT
```

Outputs are exclusive under this directory. A rerun requires a new directory,
protocol, preparation artifact, and pushed commit.
