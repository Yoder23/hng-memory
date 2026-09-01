# Shared-SQLite child-handle diagnostic v2 result

The exact preregistered run from commit
`245090724cfbb1552388b44a4d17a939321b6fe8` completed all four 90-second
conditions and returned `status=PASS` with the frozen outcome
`SUPPORTS_SHARED_SQLITE_CAUSE`.

All 48 fresh child processes exited zero and reported without errors. Every
child produced 90 or 91 independent one-second samples, exceeding the frozen
minimum of 80. Readers reported zero missing and zero malformed records.

| Condition | Median slope (handles/minute) | Child-slope range | Valid |
| --- | ---: | ---: | --- |
| `idle_12` | 0.667 | 0.667-0.667 | yes |
| `isolated_sqlite_12` | 0.667 | 0.667-0.667 | yes |
| `shared_sqlite_12_a` | 41.792 | 41.325-41.794 | yes |
| `shared_sqlite_12_b` | 49.206 | 49.205-49.331 | yes |

Both shared-database replications exceeded the frozen 10-handles/minute median
and per-child lower bounds in all 12 children. The maximum idle and isolated
control slopes remained below the frozen 5-handles/minute ceiling. This validly
localizes the reproduced growth to concurrent access to a shared SQLite/WAL
database under this workload, rather than process count, isolated SQLite use,
or the independent sampler.

This is root-cause diagnostic evidence only. It does not identify the specific
Windows handle type or call path, make the failed sustained-v2 run pass, or
qualify HNG, storage, recovery, or production behavior. `RESULTS.json` and
`events.jsonl` are the authoritative machine artifacts.
