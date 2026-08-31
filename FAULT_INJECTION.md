# Fault injection and concurrency

The process-level suite is `closure_eval/scripts/fault_injection.py`; machine output is `closure_eval/raw/FAULT_INJECTION.json`.

All 10 scenarios pass: kill before commit, kill after vector-only work, kill after evidence commit, kill during rebuild, four competing writer processes, four reader processes, profile revision during query, supersession during query, invalidation during query, and index replacement during query. Corrupt persisted metadata is additionally covered by the closure test suite and fails closed.

The coherence rule is generation based. Queries capture SQLite generation/data-version, retrieve and govern, then verify the versions. A concurrent change causes cache invalidation and retry (up to three attempts), never a mixed-generation frame. SQLite uses WAL and transactional commits; derived indexes can be rebuilt from authoritative records.

This is strong single-host/process fault evidence, not a distributed-consensus claim. Multi-node replication, network partitions, and Byzantine writers are outside the release scope.

