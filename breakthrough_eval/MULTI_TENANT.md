# Multi-tenant storage probe

The production `SQLiteEvidenceStore` was exercised with 100,000 real `EvidenceRecordV2` rows split
evenly across 1,000 tenant identifiers. WAL and `synchronous=FULL` were enabled. The process reopened
the store after every 10,000 appends, checked a sentinel and the exact generation, applied 100
supersessions plus 100 invalidations, and compared a full logical ledger after SQLite backup/restore.

All nine restart checks passed. Every tenant returned exactly 100 in-scope records, the lifecycle
checks passed, and the pre/post restore ledger was identical at 100,000 records with SHA-256
`93c302482b5eb8de86b4487609757a5f32f3fd18dfd8641c052e26a8be453c02`. Append latency was 3.710 ms
p50, 5.330 ms p95, and 10.326 ms p99. The run took 408.630 seconds.

The machine record is `reliability/MULTITENANT_100K_1K.json`. The 124 MB source and backup databases
remain local runtime artifacts and are excluded from Git.

This test establishes bounded partition accounting and restart/restore integrity. It does not model
1,000 concurrent clients, does not represent 100,000 users, does not measure cross-tenant query
leakage under adversarial concurrency, and does not satisfy the required long-run soak protocol.
