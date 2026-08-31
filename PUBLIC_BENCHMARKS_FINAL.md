# Public benchmarks final

## QMSum (executed Tier B)

The closure run uses the first 20 official QMSum test meetings, 11,674 transcript units, 134 annotated specific queries, 4,096-bit deterministic token HDC, and top-k 5. Every method receives the same transcript units and query split.

| Method | Span hit@5 | Median ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|
| BM25 | **64.93%** | 7.180 | 14.238 | 18.414 |
| BM25 + HDC RRF | 55.22% | 7.300 | 14.086 | 21.357 |
| Governed HNG candidates | 55.97% | 24.814 | 36.523 | 42.281 |

All 27,391 governed included evidence assessments retained verified external-document provenance; none were excluded by the configured policy. BM25 wins retrieval quality. The governed path adds policy/provenance, not a retrieval-quality claim.

The test evaluates annotated-span retrieval, not generated summary quality. The encoder is deterministic and reproducible, not learned. No LongMemEval-V2, LoCoMo, PersonaMem-v2, LaMP, GovReport, or common-LLM evaluation was executed; unavailable systems are not counted as losses or wins.

Machine output: `closure_eval/raw/QMSUM_GOVERNED_20.json`. Dataset source and license are preserved under `research_eval/external/QMSum/` locally and excluded from release artifacts.

