# Shared-SQLite WAL-index Section-mapping result

The exact preregistered run from commit
`0221dd8fd076103a15c8dd58dd8aa5ef57b64ad0` completed with `status=PASS` and
the frozen outcome `IDENTIFIES_WAL_INDEX_SECTION_MAPPING`.

All 48 children reported, exited zero, met their independent sample minimums,
and had zero handle-query, workload, missing-read, or malformed-read errors.

| Condition | Median handles/minute | Median `Section` delta | Median 32 KiB SHM-unit delta | Maximum per-child mismatch |
| --- | ---: | ---: | ---: | ---: |
| `idle_12` | 1.017 | 0 | n/a | n/a |
| `isolated_sqlite_12` | 1.017 | 0 | 0 | 0 |
| `shared_sqlite_12_a` | 35.581 | 34 | 34 | 0 |
| `shared_sqlite_12_b` | 48.808 | 48 | 48 | 0 |

The first shared WAL-index grew from one to 35 32-KiB units while every one of
its 12 clients gained exactly 34 Section handles. The replication grew from one
to 49 units while every client gained exactly 48 Section handles. Across all 24
shared clients, the per-client Section delta and shared SHM-unit delta matched
exactly. The isolated clients remained at one SHM unit with zero Section growth.
Every observed SHM size was an exact 32-KiB multiple.

The shared WAL files reached 589,584,392 and 818,891,232 bytes in 60 seconds.
Together with the official SQLite implementation basis pinned in
`MECHANISM_BASIS.md`, the exact controlled correspondence identifies the
growing process handles as each client mapping newly allocated 32-KiB units of
the shared database's `-shm` WAL-index. The sustained failure is therefore not
an unexplained generic handle leak: it is unbounded WAL/WAL-index growth under
the tested concurrency contract, multiplied into one Section handle per new
WAL-index unit per client.

This is mechanism evidence only. It does not yet prove a safe checkpoint or WAL
bounding intervention and does not reverse the failed sustained reliability
qualification. `RESULTS.json` and `events.jsonl` are authoritative.
