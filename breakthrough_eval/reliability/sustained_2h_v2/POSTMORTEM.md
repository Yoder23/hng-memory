# Sustained reliability v2 postmortem

The one exact preregistered v2 run from commit
`d446a455f9695cf05ffeba955720f5556c916d36` is a failed qualification. It
started at 2026-09-01T17:58:40Z and the frozen harness terminated itself at
4,020.09 seconds after a resource sample measured 1,059 handles in each writer
process and 1,049 in each reader process, above the 1,024-per-process cap. The
wrapper wrote `RESULTS.json` with `status=ERROR`, stopped every worker, and
exited code 1. It is not retried and is not represented as a partial pass.

## What improved over v1

Write-quiesced/read-live recovery fixed the failure that motivated v2. Six of
six scheduled backup/restore cycles completed. Every completed backup had
byte-identical backup and restored files, logical-ledger identity, a restored
generation equal to its backup generation, and the sentinel record. Backup
duration rose from 7.00 to 51.36 seconds as the database grew, remaining below
the frozen 180-second child timeout. Four of four completed worker epochs
returned all 12 reports with zero worker exit failures. Those reports contain
908,830 durable writes, 802,305 scoped reads, and zero missing or malformed
reads.

These observations show that the v2 recovery mechanism made real progress.
They do not satisfy the two-hour gate because only four of eight required
epochs, six of twelve required cycles, and 68 of 100 required samples completed.

## Terminal safety failure

The last fsynced sample recorded:

- 4,020.086 seconds elapsed;
- 1,059 handles per writer and 1,049 per reader;
- 268 coordinator handles;
- 69,947,392 bytes maximum per-process RSS;
- 14,192,518,352 WAL bytes;
- 70,028,767,232 free bytes.

The handle limit was the only safety limit breached. The harness responded as
specified. Post-stop read-only inspection found no live worker PID, SQLite
`quick_check=ok`, 1,008,409 evidence rows, generation 1,008,409, and logical
SHA-256
`472bd66bced56a11abf095b63569e5aa4ba1b205db0777abe3e64eae5558794e`.
That inspection is recovery evidence, not a substitute for the final ledger
check that the frozen protocol never reached.

## Unproven observer-effect hypothesis

The coordinator stayed at 268 handles while all 12 children rose almost in
lockstep despite readers and writers executing different database operations.
Rotations reset child counts in the first four epochs. In epoch 4, most children
were near 209 to 219 handles shortly after start and all reached 851 to 861 by
the next sample. That interval coincided with unusually heavy external
orchestration and repository inspection prompted by a progress report.

This correlation does not prove causation and does not invalidate the safety
failure. It motivates a separate, frozen diagnostic comparing a quiet interval
with a controlled external-command interval while children self-sample handle
counts. V2 itself remains failed regardless of the diagnostic outcome.

The authoritative machine postmortem is `FAILURE_ANALYSIS.json`; the original
`RESULTS.json` and fsynced `events.jsonl` are unchanged.
