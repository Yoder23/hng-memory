> **Closure note (0.7.0rc1):** This file preserves the 0.6 benchmark narrative. Final provider, public QMSum, assistant, fault, and profiling results are in [RETRIEVAL_PROVIDERS_FINAL.md](RETRIEVAL_PROVIDERS_FINAL.md), [PUBLIC_BENCHMARKS_FINAL.md](PUBLIC_BENCHMARKS_FINAL.md), [REAL_ASSISTANT_ABLATION.md](REAL_ASSISTANT_ABLATION.md), and [CLOSURE_AUDIT.md](CLOSURE_AUDIT.md).

# HNG 0.6.0rc1 benchmarks

All values are local Tier A unless identified as the previously reproduced QMSum Tier B subset. Hardware and dependencies are recorded in `research_eval/ENVIRONMENT.md`.

## Compatibility regression

| Benchmark | 0.6.0rc1 result |
|---|---:|
| Inherited tests | 30/30 |
| Complete tests | 72/72 |
| Assistant readiness continuity | 100% |
| Retrieval-only ambiguous turn | 0% |
| Cross-chat episode recall | 100% |
| Historical action top-1 | 100% |
| Action support/challenge/unseen | 100% |
| Changed sequence supplied | 100% |
| 15% noise action accuracy | 98.958% |
| Perspective-conditioned top-1 | 100% |
| Perspective violations | 0% |
| Privacy checks | 0/2 leaks |
| 20K-turn state after restart | correct |
| 20K throughput | 2,594.5 turns/s |

The 15% value matches the independent fresh 0.5.1 reproduction; it does not reproduce the older 100% documentation claim. This is not presented as a regression.

## Canonical adversarial suite

| Architecture | Passed |
|---|---:|
| 0.5.1 | 5/11 |
| 0.6.0rc1 | **11/11** |

## FAISS provider

Same 100K independent 4,096-bit vectors, 2% noise, 80 queries, one thread, FAISS BinaryFlat truth:

| Provider | Exact top-1 | p50 | p95 | p99 | Build |
|---|---:|---:|---:|---:|---:|
| 0.6 FAISS BinaryIVF, nlist 256 / nprobe 32 | 100% | 0.679 ms | 0.900 ms | 2.520 ms | 13.91 s |
| 0.5 HNGIX independent benchmark | 100% | 1.270 ms | 1.699 ms | 1.949 ms | 0.392 s |

FAISS query latency wins; HNGIX still builds faster and remains the reference/fallback. The independent evaluation also established FAISS wins at matched exact top-1 at 1M and 10M. Those earlier raw results are preserved rather than rerun as if new.

## Governed behavioral isolation harness

32 action cases contain ten attractive unverified model claims and one verified current telemetry failure under identical semantic states.

| Memory decision path | Task success | Stale/unsupported behavior |
|---|---:|---:|
| Raw top-k majority | 0% | 100% stale-support errors |
| HNG governed | 100% | 0% unsupported recommendations |

HNG provenance completeness was 100%. End-to-end evaluation latency was p50 3.987 ms, p95 4.715 ms, p99 5.409 ms. This is synthetic and uses no LLM; it isolates evidence governance rather than language reasoning.

## Documents and RAG

The production architecture now adopts BM25-first hybrid retrieval and does not claim the old document hierarchy improved. The preserved Tier B QMSum first-20 result remains:

- HNG relevant-span hit@5: 41.79%;
- BM25 hit@5: 65.67%;
- hybrid lexical + HDC: 62.69%;
- HNG produced one segment for all 20 documents.

No new public document score is claimed. `HybridDocumentRetriever` is covered for BM25, semantic-provider composition, and exact metadata filtering; a full QMSum/GovReport rerun remains required.

## Limitations

- No common LLM/model/prompt behavioral A/B was run.
- No public LongMemEval-V2 or PersonaMem-v2 score exists yet.
- Provider 100K timing is one warm process, not multi-host confidence intervals.
- Multi-process writer strategy and live cross-process index synchronization remain future work; SQLite truth is durable and indexes rebuild on reopen.
- The source tree path retains `0.5.1a1` for baseline provenance even though package metadata is 0.6.0rc1.

