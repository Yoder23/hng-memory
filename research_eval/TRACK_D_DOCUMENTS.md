# Track D: long-document memory

## Verdict

The synthetic document breakthrough reproduces only under a highly separable, label-rich construction. Once baselines receive the same role/priority detections, a simple importance-first selector is perfect and much faster. On human-written QMSum, HNG's hierarchy collapses to one segment for every tested meeting, uniform sampling wins all three summary ROUGE measures, and BM25 wins relevant-span hit@5.

## Synthetic benchmark (Tier A)

Fresh shipped workload: 32 documents, 8,960 units, 16 themes per document, 2,048-bit heads, and a 40-unit evidence budget.

| Method | Theme | Key claims | Priority | Contradictions | Median ms |
|---|---:|---:|---:|---:|---:|
| HNG | 100% | 98.05% | 100% | 100% | 117.40 |
| Lead | 19.14% | 19.14% | 18.36% | 13.02% | 0.0053 |
| Uniform | 100% | 23.05% | 17.36% | 11.46% | 0.0691 |
| Semantic top-k | 21.48% | 21.48% | 14.24% | 15.63% | 0.2207 |
| Importance top-k, shipped information | 44.14% | 25.00% | 63.67% | 65.10% | 0.1739 |
| MMR | 100% | 57.23% | 98.96% | 100% | 6.557 |
| Oracle KMeans | 100% | 100% | 100% | 100% | 56.58 |

HNG boundary F1 is 1.0 and targeted HNG recall@5 is 1.0. Exact composite retrieval is also 1.0 on the targeted queries. The claimed HNG median near 23.6 ms did not reproduce; the fresh shipped run was 117.4 ms.

### Fairness audit

The generated `role` head identifies key claims, caveats, and contradictions. HNG and oracle KMeans use those detections in synopsis selection, while the original ordinary baselines do not receive equivalent information. A second run gave every selector the same role-head detections:

| Equal-information method | Theme | Key claims | Priority | Contradictions | Median ms |
|---|---:|---:|---:|---:|---:|
| HNG | 100% | 98.05% | 100% | 100% | 228.78 |
| MMR + same detections | 100% | 57.23% | 100% | 100% | 15.88 |
| Semantic + same detections | 61.72% | 19.73% | 100% | 100% | 16.49 |
| Importance-first + same detections | 100% | 100% | 100% | 100% | 16.91 |

The timing difference across the two HNG runs reflects system load and is not used as a controlled speedup claim. The correctness result is decisive: the special priority information, not the hierarchy, creates much of the apparent gain.

## QMSum public evaluation (Tier B)

The official QMSum repository/test data were used. This is a deterministic fixed first-20-document subset, 4,096-bit shipped-style encoder, 32 evidence units for every method, and 134 specific queries with top-k 5. No LLM was used; evidence text was scored directly so generation could not hide selection quality.

### Extractive general-summary evidence

| Method | ROUGE-1 F1 | ROUGE-2 F1 | ROUGE-L F1 |
|---|---:|---:|---:|
| Lead-32 | 0.1329 | 0.0240 | 0.0769 |
| Uniform-32 | **0.1471** | 0.0275 | **0.0834** |
| Semantic top-k | 0.1052 | 0.0290 | 0.0621 |
| MMR | 0.1360 | **0.0309** | 0.0792 |
| BM25 | 0.1182 | 0.0301 | 0.0712 |
| HNG | 0.1216 | 0.0231 | 0.0696 |

Uniform sampling beats HNG on every ROUGE measure. HNG is not best on any measure.

### Specific-query relevant-span hit@5

| Method | Hit@5 |
|---|---:|
| HNG | 41.79% |
| Exact topic Hamming | 42.54% |
| Exact multi-head Hamming | 41.79% |
| BM25 | **65.67%** |
| Hybrid lexical + HDC | 62.69% |

HNG query latency was 3.269 ms median (p95 5.274, p99 6.513). The tiny timing reported for the other selectors measures ranking of precomputed scores, not full score construction, so it is not presented as an end-to-end speed comparison.

### Hierarchy failure

Mean discovered segments = 1.0, and all 20 documents were single-segment. The boundary rule selects the strongest adjacent-similarity gap and applies a global threshold that did not produce a usable hierarchy on these meetings. This is direct evidence that synthetic boundary F1 does not transfer.

The shipped QMSum harness also reuses the final document's ingestion time in every output row. The independent harness fixes per-document timing.

## Evaluation-layer separation

- Memory-frame quality was measured directly through coverage and span hit@k.
- Rendered extractive evidence was measured with ROUGE under an equal 32-unit budget.
- A common LLM summarizer was not available, so no generated-summary factuality or answer-accuracy result is claimed.
- `to_hdc_context()` was exercised by shipped tests but no downstream HDC reasoner exists in the release; it remains an unvalidated semantic frame, distinct from `to_context_text()`.

## Systems not executed

GovReport, BillSum, RAPTOR, GraphRAG, and SVD-RAG were investigated but not run. RAPTOR/GraphRAG require model pipelines not frozen in the release. SVD-RAG was too recent and not locally integrated. Their published numbers remain Tier C and are not treated as comparable local results.

## Recommendation

Do not use the present HNG document boundary detector or synopsis selector in production. Start with BM25 + dense/HDC hybrid retrieval, explicit provenance, and a proven hierarchy such as RAPTOR for generator-backed trees or SVD-RAG for a deterministic hierarchy, then benchmark on the full target corpus. Preserve HNG's typed claim/caveat/contradiction roles only if they are produced independently rather than injected from ground truth.

