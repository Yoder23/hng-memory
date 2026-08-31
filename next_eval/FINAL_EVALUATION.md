# Final old-versus-new evaluation

This table applies the same skeptical standard as the independent baseline. Local synthetic wins are not promoted to public state-of-the-art claims.

| Capability | Old 0.5.1 | New HNG 0.6.0rc1 | Best baseline | Winner |
|---|---:|---:|---:|---|
| Immediate continuity | 100% exact carry | 100% compatibility; direct typed state | Explicit keyed state machine | Tie; HNG is native-HDC friendly |
| Cross-chat recall | 100% synthetic | 100% compatibility | Modern structured memory not run locally | Unresolved publicly |
| Action disambiguation | 100% synthetic | 100% compatibility | Structured transition ledger | Tie on local data |
| Action evidence | shipped cases pass; adversaries fail | canonical adversaries 11/11 | Versioned policy/evidence ledger | New HNG ties the right architecture |
| Missing-state handling | missing sequence supports stale action | `INSUFFICIENT_STATE` | Schema-validated structured memory | New HNG / baseline tie |
| Stale evidence | old majority wins | 100 old positives excluded; 3 current failures challenge | Versioned event store | New HNG / baseline tie |
| Duplicate evidence | copies amplify support | one source event contributes once | Deduplicated event ledger | New HNG / baseline tie |
| Poisoning resistance | poisoned memory supports | low-trust poison returns `UNTRUSTED_EVIDENCE` | Authenticated trust-aware store | New HNG locally; not a universal proof |
| Actor perspective | 100% synthetic | old result preserved; exact/fuzzy layers separated | Structured dictionary also 100% | Tie |
| Profile uncertainty | incorrect profile supports | inferred 0.42 profile returns `PROFILE_UNCERTAIN` | Revisioned structured profile | New HNG / baseline tie |
| Privacy isolation | 0/2 shipped leaks | inherited checks plus private/tenant collision tests pass | SQL RBAC/ABAC | Tie |
| Raw ANN at 100K | HNGIX 1.270 ms p50, exact | FAISS provider 0.679 ms p50, exact | FAISS BinaryIVF | FAISS, now used by HNG |
| Long-term update | correct only when changed head supplied | required state + structured environment/policy versions | Temporal event/graph memory | New HNG locally; public unresolved |
| Document retrieval | HNG 41.79% QMSum hit@5 | custom hierarchy demoted; BM25/hybrid provider | BM25 65.67% on reproduced subset | BM25 |
| RAG evidence quality | not governed | 100% correct challenge vs 0% raw vote in 32-case poison harness | Comparable governed RAG not run | New HNG on synthetic only |
| Governed latency | old action gate 4.69 ms on different gauntlet | 3.987 ms p50, 4.715 ms p95 | Raw provider 0.679 ms | Acceptable; not directly comparable |
| Restart recovery | correct only after Windows no-op-fsync evaluation shim | native Windows tests/gauntlets pass | SQLite WAL/versioned store | New HNG |

## Architecture decision

For a frontier HDC assistant, use 0.6's deterministic state, transition/outcome records, governed evidence, exact HDC floors, structured access/perspective, and FAISS candidate provider. Keep HNGIX only as reference/fallback.

For an LLM assistant, use 0.6 as a bounded evidence harness in shadow/advisory mode around a conventional hybrid retrieval and structured state stack. Do not claim the current synthetic evidence proves better public long-horizon task performance.

For documents, use BM25 + semantic hybrid retrieval and an external hierarchy when required. Persist validated claims into HNG afterward; do not revive the failed custom hierarchy without new public evidence.

## Release-candidate verdict

The architecture is materially stronger and simpler than 0.5.1. It fixes the identified control-plane failures and adopts the winning commodity components. It is ready as a **research release candidate and shadow-mode integration**, not as a default autonomous hard gate or a state-of-the-art publication claim.

