# LoCoMo-Plus disjoint neural-reranker holdout protocol

Status: **FROZEN BEFORE EXECUTION**

This failure-driven experiment addresses the remaining strong-RAG reranker gap after the
separately frozen retrieval-budget and dense/hybrid holdouts. It changes retrieval only; it does
not add an HNG feature.

## Data separation

The development, retrieval-budget, and dense/hybrid studies used SHA-ranked positions 1-15 per
category. This holdout uses positions 16-20 in each of six categories: 30 public-data samples with
zero source-index overlap. Its excluded set equals the exact 90 indices used by those three prior
windows. `PREPARED.json` fixes all indices, corpus hashes, model identities, first-stage union
hashes, ordered candidate payloads, reranker scores, and candidate hashes before reader/judge
execution. Answers and oracle judge evidence do not participate in selection, embedding,
reranking, or fusion and are absent as prepared-artifact fields.

## Frozen retrieval and arms

Dense retrieval uses `qwen3-embedding:0.6b`, digest
`ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`, Q8_0, 1024
dimensions. Hybrid retrieval uses reciprocal-rank fusion of complete BM25 and dense rankings with
constant 60. Neural reranking uses official `Qwen/Qwen3-Reranker-0.6B` revision
`e61197ed45024b0ed8a2d74b80b4d909f1255473`; `model.safetensors` SHA-256 is
`27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b`. It runs in float16 on
CUDA with SDPA, 512-token pair limit, batch size 16, and the instruction frozen in
`PREPARED.json`.

The cross-encoder scores the candidate-ID-sorted union of BM25-top-128 and dense-top-128, then
selects the top 64 by probability with candidate ID as the final tie-breaker. Documents are
individual dated dialogue turns. The first-stage unions contain 190-242 turns in this holdout.

| Arm | Candidates | Purpose |
|---|---:|---|
| full_context | all | high-token reference |
| bm25_k64 | 64 | frozen lexical baseline |
| dense_k64 | 64 | genuine dense baseline |
| hybrid_k64 | 64 | BM25+dense RRF baseline |
| reranked_k64 | 64 | genuine cross-encoder reranking baseline |
| strong_reranked_k64 | identical reranked 64 | simple fixed-candidate governance control |
| hng_reranked_k64 | identical reranked 64 | HNG fixed-candidate governance control |

All retrieved arms use a 72,000-character ceiling; every prepared arm realizes exactly 64 unique
turns. BM25/dense, BM25/hybrid, dense/reranked, and hybrid/reranked ordered sets differ on all 30
samples. Reader/judge is `qwen3.8:27b-q4_K_M`, digest
`25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`, temperature zero,
seed 20260831, 32,768-token context, and 192 reader-token ceiling. This is noncanonical.

## Hypotheses and comparisons

Primary hypothesis: cross-encoder reranked k64 improves official judge score over RRF hybrid k64
on this disjoint holdout. Primary comparison: `reranked_k64` versus `hybrid_k64` with a paired
bootstrap 95% interval and exact McNemar test at judge score above 0.5.

Secondary comparisons are reranked versus dense, BM25, and full context; dense versus BM25;
hybrid versus BM25; and HNG versus reranked/Strong on identical reranked candidates and prompts.
Report prompt tokens and selected context characters. An interval containing zero is inconclusive.
An exact fixed-candidate tie is not an HNG win.

## Integrity and stopping

- Complete all 210 sample/arm events; no interim-score stopping.
- Reuse only within one sample when prompt and full inference-configuration hashes match; record it.
- Refuse an HNG event whose source identity is not `LoCoMo-Plus`.
- Restore frozen candidates directly from `PREPARED.json`; never re-embed or rerank in execution.
- Preserve setup failures and the append-only raw event log.
- Do not compare these local scores directly with official leaderboards or literature results.
