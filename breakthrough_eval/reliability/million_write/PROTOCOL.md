# Million-write production-store reliability protocol

This is a bounded high-volume reliability run against the shipped `SQLiteEvidenceStore`. It is not
an OS-crash, disk-full, multi-process, or days-long production soak, and it does not test retrieval
quality. Runtime databases are ignored; the machine result and cryptographic ledgers are committed.

## Frozen configuration

- 1,000,000 individually durable appends with SQLite WAL and `synchronous=FULL`.
- 100 tenants, exactly 10,000 records per tenant.
- Close/reopen and generation/sentinel verification after every 100,000 appends.
- After all appends, supersede 100 records and invalidate a disjoint 100 records.
- Snapshot through SQLite's backup API, reopen the backup, and compare the complete logical ledger.
- Require at least 8,000,000,000 free bytes before execution.

Preparation hashes this protocol, the bounded probe, the million-write wrapper, and the production
`storage_v2.py`. Execution requires an exact clean pushed preregistration commit and refuses any
hash/config mismatch or pre-existing database, backup, or result.

## Pass criteria

1. Exactly 1,000,000 records exist before and after backup/restore.
2. All nine restart checks match expected generation and recover their sentinel.
3. Every tenant has exactly 10,000 scoped records and the total is exactly 1,000,000.
4. All 100 supersession and 100 invalidation mutations survive restore.
5. Pre-backup and restored logical ledger SHA-256 values are identical.
6. Generation before backup equals generation after restore.
7. Database and backup file SHA-256 values and byte sizes are recorded.
8. Any exception or failed invariant produces a preserved `ERROR`/`FAIL`, never a hidden retry.

The qualifying command is frozen in `PREPARED.json`; `COMMIT` must be replaced only by the exact
clean commit that contains that preparation artifact.
