# Shared-SQLite handle-type diagnostic v3 result

The exact preregistered run from commit
`53e3602689e59255c2152fbd4a02ce500b87fa67` completed with `status=PASS` and
the frozen outcome `IDENTIFIES_DOMINANT_HANDLE_TYPE`.

All 48 fresh children reported and exited zero. Every child produced 60 or 61
independent handle samples, all handle-type queries succeeded, and readers
reported zero missing or malformed records. Queue-safe report draining removed
the validity failure preserved in v2.

| Condition | Median total slope (handles/minute) | Median `Section` delta | `Section` share of positive median delta |
| --- | ---: | ---: | ---: |
| `idle_12` | 1.017 | 0 | 0% |
| `isolated_sqlite_12` | 1.017 | 0 | 0% |
| `shared_sqlite_12_a` | 48.810 | 48 | 94.1% |
| `shared_sqlite_12_b` | 49.814 | 48 | 94.1% |

Every shared child exceeded the frozen 10-handles/minute lower bound. Both
controls remained below the 5-handles/minute ceiling and no control child gained
a `Section` handle. The same `Section` object type dominated both shared
replications, exceeded the frozen median-delta lower bound, and accounted for
more than the frozen 80% share.

This validly identifies Windows `Section` objects as the dominant handle type
behind the reproduced shared SQLite/WAL growth. A Section is a Windows kernel
memory-mapping object; this result does not yet name the mapped file or exact
SQLite call path. It remains mechanism evidence only and does not reverse the
failed sustained reliability qualification or qualify HNG, storage, recovery,
or production use. `RESULTS.json` and `events.jsonl` are authoritative.
