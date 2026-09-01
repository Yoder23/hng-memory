# LoCoMo-Plus disjoint retrieval-budget holdout protocol

Status: **FROZEN BEFORE EXECUTION**

Frozen development evidence: `public/locomo_plus_n30/RESULTS.json`. That observed slice uses SHA
ranks 1-5 within each of six categories and shows full context at 61.7% versus BM25/HNG/Strong at
30.0% with top-16 retrieval.

This holdout uses ranks 6-10 in each category: 30 public-data samples with zero source-index
overlap. `PREPARED.json` fixes their indices, input hashes, retrieval-corpus hashes, candidate IDs,
and candidate hashes before model execution. Answers and oracle judge evidence do not participate
in ranking or retrieval.

## Frozen arms

| Arm | Retrieved turns | Character ceiling | Purpose |
|---|---:|---:|---|
| full_context | all | official input | accuracy ceiling and high-token reference |
| bm25_k16 | 16 | 18,000 | reproduce the development operating point on holdout |
| bm25_k32 | 32 | 36,000 | intermediate retrieval budget |
| bm25_k64 | 64 | 72,000 | wider retrieval budget motivated by current public implementations |
| strong_k64 | same 64 | same | fixed-candidate simple governance control |
| hng_k64 | same 64 | same | fixed-candidate HNG governance control |

The model is `qwen3.8:27b-q4_K_M`, digest
`25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`, with temperature
zero, seed 20260831, 32,768-token context, and 192 generated-token ceiling. The same frozen model
serves as reader and official-template judge, so the protocol remains noncanonical.

## Hypotheses and comparisons

Primary failure-driven hypothesis: the development loss is caused materially by top-16 retrieval
truncation. The primary comparison is `bm25_k64` versus `bm25_k16` on official judge score.

Secondary comparisons are k32 versus k16, k64 versus k32, each retrieval budget versus full
context, and HNG versus BM25/Strong at the identical k64 candidate/prompt point. Report paired
bootstrap 95% intervals over judge-score deltas and exact McNemar tests using judge score above 0.5
as positive. Also report reader prompt tokens, selected context characters, and score per 1,000
reader prompt tokens.

If k64 improves materially while preserving a token advantage, the architecture should adopt a
stronger retrieval operating point rather than adding HNG features. If k64 does not improve, wider
lexical retrieval alone does not explain the loss. If HNG and Strong receive identical clean
evidence, a tie is expected and must not be described as an HNG win.

## Integrity and stopping

- Complete all 180 sample/arm events; no interim-score stopping.
- Reuse a reader/judge result only within the same sample when prompt SHA-256 and the full
  inference-configuration SHA-256 are identical; record every reuse explicitly.
- Never alter selected indices, candidates, budgets, prompts, model, judge, or expected outcome
  after reading results.
- Preserve setup failures and raw append-only events.
- Do not compare these local numbers directly with official leaderboard or literature scores.
