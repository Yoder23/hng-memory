# Public document knowledge

## Preserved QMSum loss

The frozen official QMSum test-split probe covers 20 documents, 11,674 transcript units, and 134
specific queries. It measures annotated-span hit@5, not generated-summary quality:

| Method | Span hit@5 | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| BM25 | 64.93% | 5.975 ms | 11.718 ms | 16.081 ms |
| hybrid document | 55.22% | 5.785 ms | 11.528 ms | 17.613 ms |
| governed memory | 55.97% | 18.408 ms | 30.667 ms | 32.601 ms |

BM25 wins retrieval accuracy and governed memory is slower. Governance excludes zero candidates,
so this corpus supplies no temporal/trust/provenance conflict for HNG to resolve. The correct
architecture is to retain BM25 for candidate discovery and test governance only after retrieval on
tasks with applicability conflicts.

GovReport, BillSum, long-document QA, GraphRAG/RAPTOR-style runnable baselines, and a separate
governed-understanding metric are not yet executed. QMSum alone neither proves nor disproves value
after strong retrieval; it directly disproves replacing BM25 with the frozen HDC text retriever.
