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

## 100,000-principal scoped-isolation probe

A second production-store experiment creates 100,000 distinct tenant/user principals across 1,000
tenants, with 100 local user identifiers per tenant. Local user identifiers are deliberately reused
between tenants, and every private record has the same structured semantic state. This removes
semantic separability as a possible explanation for isolation.

The run exhaustively issued 100,000 authorized private queries, 100,000 wrong-tenant queries, and
100,000 wrong-user queries. It observed zero authorized misses, zero victim records in cross-tenant
queries, and zero victim records in cross-user queries. ActorPolicy separately evaluated all
100,000 records: matching profiles passed, while 100,000 wrong-role and 100,000 below-authority
profiles were all rejected. During a bounded concurrent phase, eight reader workers completed
10,000 additional identity checks while four writer workers committed 800 global records; all
writes completed and no scoped leak appeared.

Three restart checks passed. A backup restored an identical 100,800-record logical ledger with
SHA-256 924dcf0fb3dfeb63cb59ef5903a579528abe42597d6ff10935cb4ec2d732d503.
Authorized private-query latency was 0.007 ms p50, 0.009 ms p95, and 0.018 ms p99. The full run
took 390.445 seconds. Machine evidence is reliability/MULTI_USER_100K_ISOLATION.json.

This is a qualified storage/policy result, not an end-to-end security certification. The scoped
eligible-ID path assumes tenant and user identifiers came from trusted server-side authentication.
Raw get and get_many remain deliberately unscoped administrative primitives and return a private
record when its identifier is known. A deployment must keep those primitives behind a trusted
service boundary. The test also is not an hours-long load test.
