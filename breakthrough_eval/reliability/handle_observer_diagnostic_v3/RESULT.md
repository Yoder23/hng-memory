# Valid observer diagnostic result

The exact run from preregistered commit
`7bed722e642ca9c89663cf53d3fa6457c3082956` completed with `status=PASS`, all
six validity controls true, and the frozen outcome
`REFUTES_OBSERVER_EFFECT_AT_THRESHOLD`.

All 20 unique pulse ordinals landed inside the widened `[150,330)` external
phase. All four children returned zero exit codes and no errors, and every child
exceeded 100 self-samples in each measured phase. The idle, event-poll,
SQLite-read, and SQLite-write variants each lost two startup handles during the
quiet baseline, then had exactly zero net handle growth during the 180-second
external phase and zero during quiet recovery. Median external handle slope and
net growth were both zero.

This refutes the narrow preregistered hypothesis that separately launched
orchestration pulse commands cause the synchronized child-handle growth at the
frozen thresholds in these four isolated variants on this host. It does not
explain the sustained v2 failure, reproduce its 12-process shared-database
workload, or convert v2 into a pass. The next reliability work must isolate
workload/process-count/shared-SQLite causes before another hours-long protocol.

`RESULTS.json`, `events.jsonl`, `pulses.jsonl`, and all four self-sample ledgers
are the authoritative evidence.
