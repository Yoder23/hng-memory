# Executive verdict

## Decision

**C — Valuable specialized system**

HNG 0.5.1a1 is a coherent research prototype for HDC-native assistants, especially its deterministic working state, explicit transition/action/outcome model, exact access/authority policy, full-vector per-head floors, provenance, and fail-closed decision vocabulary. It is **not** supported as a state-of-the-art general memory substrate. Its strongest results are synthetic and encode the variables that define the answer; ordinary structured and dense baselines reproduce those gains. On public QMSum, its hierarchy collapses to one segment per meeting and simple baselines win. Its ANN loses to FAISS BinaryIVF at matched recall at 100K and 1M.

| Capability | HNG | Best competitor | Winner | Evidence tier | Confidence |
|---|---|---|---|---|---|
| Immediate turn continuity | 100% synthetic via exact carry | Explicit state machine / recent context | Tie | A | High |
| Cross-chat recall | 100% synthetic | Modern structured agent memory; no direct local public run | Unresolved | A/C | Low |
| Dynamic state tracking | Correct only when changed head is supplied; missing sequence wrongly supports stale action | Typed state/event store | Competitor | A | High |
| Action/outcome memory | Correct synthetic support/challenge/conflict/unknown | Relational event/outcome ledger | Tie | A | High |
| Fail-closed action evidence | Good on unseen/strict-action cases; fails stale-majority, poison, duplicates, missing head | Versioned/deduplicated policy ledger | Competitor | A | High |
| Perspective/personalization | 100% synthetic | Structured dictionary 100%; dense multi-head 100% | Tie; no HNG-specific gain | A | High |
| Access isolation | 0/2 shipped leaks plus unit tests | Standard RBAC/ABAC database filters | Tie | A | Medium |
| Long-horizon memory | No public assistant benchmark executed | AgentRunbook-C 72.5% on LongMemEval-V2; other current systems | Competitor evidence only | C | Medium |
| Raw ANN | Exact, 1.27 / 6.74 / 45.88 ms at 100K / 1M / 10M | FAISS BinaryIVF exact at 0.296 / 2.86 / 28.01 ms | FAISS | A | High |
| Multi-head constrained retrieval | Expressive and exact after routing | Structured filter + per-head FAISS + exact rescore | Tie architecturally | A | Medium |
| Update/freshness behavior | Exact unindexed tail works; Windows sync fails | Mature mutable vector/database systems | Competitor | A/C | High |
| Long-document synopsis | Synthetic 98% claims; one segment on all 20 QMSum meetings | Uniform sampling beats all HNG ROUGE metrics | Competitor | B | High |
| Document Q&A | QMSum span hit@5 41.8% | BM25 65.7% | BM25 | B | High |
| Cross-document memory | API/provenance test only | Graph/hierarchical retrieval systems | Unresolved | A/C | Low |
| Provenance | Exact slots/source retained | Mature RAG/graph stores also retain citations | Tie | A/C | Medium |
| Memory poisoning robustness | 5/11 adversarial cases pass | Versioned, authenticated, deduplicated memory policy | Competitor | A | High |
| Operational maturity | Alpha, no license, no Git provenance, Windows portability defect | FAISS/USearch/Letta/GraphRAG ecosystems | Competitor | A/C | High |

## Build recommendation

For a frontier **HDC-native assistant**, I would keep HNG's typed transition schema, deterministic `next_state` carry, working-state replay model, explicit access/authority filters, action-evidence decision enum, exact per-head verification, and provenance contract. I would initially deploy them in shadow/advisory mode.

I would replace HNGIX routing with one FAISS BinaryIVF index per HDC head for batch/static memory, or evaluate USearch for high-update workloads, then intersect/filter candidates and perform HNG's exact full-vector floors. Exact actor/access policy stays in the relational layer. Exact current-state keys should use a normal keyed store, not ANN.

For an **LLM assistant**, I would not use this release as the primary external memory. I would start with a current structured memory system plus lexical/semantic hybrid retrieval and a versioned event/profile store; HNG's evidence gate could remain an external advisory control component after calibration. For documents, use hybrid retrieval and a proven hierarchy (RAPTOR/SVD-RAG/GraphRAG-class according to workload), not HNG's present boundary detector.

The defensible contribution is the combination of deterministic semantic-state continuity, explicit multi-head evidence conjunction, and external action policy—not a new winning ANN, not proven personalization, and not a public-data document breakthrough.
