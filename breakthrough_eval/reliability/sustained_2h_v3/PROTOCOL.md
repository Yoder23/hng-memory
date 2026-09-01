# Sustained reliability v3: checkpoint-bounded recovery

## Status before execution

This is a separately versioned, fail-closed two-hour protocol. It is not a
retry or reinterpretation of either failed sustained run. V2 crossed its
frozen 1,024-handle cap after 4,020.09 seconds. Subsequent preregistered
diagnostics localized growth to shared SQLite WAL-index `Section` mappings and
then showed that fresh 30-second connection epochs followed by fully quiescent
`PRAGMA wal_checkpoint(TRUNCATE)` calls bounded the mechanism in two treatment
replications without reducing throughput below the untreated baseline.

No v3 result exists when this protocol is frozen. `PREPARED.json` must pin the
exact clean pushed commit and hashes before the sole qualifying invocation.

## Frozen hypothesis

Thirty-second complete connection rotation followed by a fully quiescent
TRUNCATE checkpoint bounds WAL/WAL-index Section-handle growth below the frozen
cap throughout the two-hour v2 recovery workload without violating exact
storage or backup identity.

## Frozen workload and intervention

- Run for at least 7,200 wall-clock seconds with four independent writers,
  eight scoped readers, 100 tenants, and 1,000 seeded records.
- Replace every worker process after each 30-second connection epoch.
- After every epoch, stop and join all workers before opening the checkpoint
  connection. Run `PRAGMA wal_checkpoint(TRUNCATE)` and `PRAGMA quick_check`,
  close that connection, and only then start replacement workers.
- Every checkpoint must return `busy=0`, report `quick_check=ok`, complete
  within 30 seconds, and leave no more than 32,768 WAL bytes after close.
- Require at least 216 completed worker epochs and exactly one successful
  checkpoint cycle for every completed epoch.
- Preserve v2's monitored recovery contract every 600 seconds: writers pause
  after their current transaction, readers remain live, and a separate child
  performs backup, restore, and exact logical comparison under a 180-second
  timeout. Require at least 12 successful cycles, including the final cycle.
- Sample cross-process resources every 30 seconds and require at least 216
  samples. Abort immediately above 1.5 GB RSS or 1,024 handles in any observed
  process, or below 30 GB free disk. Preflight requires 40 GB free.
- Require at least 100,000 writes and 100,000 scoped reads, zero worker errors,
  zero missing/malformed reads, exact final record count and generation, and
  exact final live/backup identity.

All criteria are conjunctive. A safety cap, timeout, missing report, partial
artifact, exception, or unmet criterion is `ERROR` or `FAIL`, never a pass.
The exact failed invocation and its artifacts are preserved; the protocol is
not rerun under the same frozen commit.

## Preregistered execution

```powershell
C:\Python310\python.exe breakthrough_eval\scripts\reproduce.py sustained-reliability-v3 --prepare-only
git add breakthrough_eval
git commit -m "Preregister sustained reliability v3"
git push origin main
C:\Python310\python.exe breakthrough_eval\scripts\reproduce.py sustained-reliability-v3 --preregistered-commit COMMIT
```

Execution requires `HEAD == origin/main == COMMIT`, a clean worktree, exact
prepared source/config hashes, and the frozen free-space preflight.

## Claim boundary

A pass is one bounded two-hour local write-quiesced/read-live recovery result
for this exact workload and intervention. It is not evidence for uninterrupted
write backup, OS crash, process kill during commit, power loss, actual disk
exhaustion, distributed deployment, days-long operation, absence of all leaks,
or production readiness. It does not qualify HNG-specific memory quality.
