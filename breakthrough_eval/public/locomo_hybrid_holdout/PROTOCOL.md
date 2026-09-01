# LoCoMo-Plus disjoint dense/hybrid retrieval holdout protocol

Status: **FROZEN BEFORE EXECUTION**

This failure-driven experiment addresses the missing strong-RAG gate after the separately frozen
BM25 16/32/64-turn holdout. It changes retrieval only; it does not add an HNG feature.

## Data separation

The development slice used SHA-ranked positions 1-5 per category and the retrieval-budget holdout
used positions 6-10. This holdout uses positions 11-15 in each of six categories: 30 public-data
samples with zero source-index overlap. `PREPARED.json` fixes all indices, input/corpus hashes,
embedding identity, ordered candidate payloads, scores, and hashes before reader/judge execution.
Answers and oracle judge evidence do not participate in selection, embedding, or fusion.

## Frozen retrieval and arms

The dense encoder is `qwen3-embedding:0.6b`, digest
`ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`, Q8_0, 1024
dimensions. The query instruction is frozen in `PREPARED.json`. Documents are individual dated
dialogue turns. Hybrid ranking is reciprocal-rank fusion of the complete BM25 and dense rankings:
`1/(60 + bm25_rank) + 1/(60 + dense_rank)`, with candidate ID as the final tie-breaker.

| Arm | Candidates | Purpose |
|---|---:|---|
| full_context | all | high-token reference |
| bm25_k64 | 64 | frozen lexical baseline |
| dense_k64 | 64 | genuine dense retrieval baseline |
| hybrid_k64 | 64 | BM25+dense RRF baseline |
| strong_hybrid_k64 | identical hybrid 64 | simple fixed-candidate governance control |
| hng_hybrid_k64 | identical hybrid 64 | HNG fixed-candidate governance control |

All retrieved arms use a 72,000-character ceiling; every prepared arm realizes exactly 64 turns.
BM25, dense, and hybrid ordered sets differ on all 30 samples. The reader/judge remains
`qwen3.8:27b-q4_K_M`, digest
`25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`, temperature zero,
seed 20260831, 32,768-token context, and 192 reader-token ceiling. This is noncanonical.

## Hypotheses and comparisons

Primary hypothesis: hybrid k64 improves official judge score over BM25 k64 on this disjoint
holdout. Primary comparison: `hybrid_k64` versus `bm25_k64` with paired bootstrap 95% interval and
exact McNemar test at judge score above 0.5.

Secondary comparisons are dense versus BM25, hybrid versus dense, hybrid versus full context, and
HNG versus hybrid/Strong on identical hybrid candidates and prompts. Report prompt tokens and
selected context characters. An interval containing zero is inconclusive. An exact fixed-candidate
tie is not an HNG win. This protocol does not claim a cross-encoder reranker baseline.

## Integrity and stopping

- Complete all 180 sample/arm events; no interim-score stopping.
- Reuse only within one sample when prompt and full inference-configuration hashes match; record it.
- Refuse an HNG event whose source identity is not `LoCoMo-Plus`.
- Restore frozen candidates directly from `PREPARED.json`; never re-embed during execution.
- Preserve setup failures and the append-only raw event log.
- Do not compare these local scores directly with official leaderboards or literature results.
