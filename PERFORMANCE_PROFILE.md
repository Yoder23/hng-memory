# Performance profile

`closure_eval/scripts/performance_profile.py` ran 300 governed queries over 1,000 2,048-bit records and rendered every frame. Results are in `closure_eval/raw/PERFORMANCE_PROFILE.json`.

| Component | Median ms | p95 ms | p99 ms | Stddev ms |
|---|---:|---:|---:|---:|
| Retrieval (FAISS Flat + BM25/RRF) | 19.883 | 23.799 | 27.438 | 2.007 |
| Structured eligibility | 0.031 | 0.037 | 0.043 | 0.036 |
| Exact vector verification | 0.051 | 0.068 | 0.071 | 0.007 |
| Trust evaluation | 0.249 | 0.371 | 0.395 | 0.052 |
| Independence grouping | 0.055 | 0.070 | 0.075 | 0.007 |
| Temporal governance | 0.173 | 0.246 | 0.809 | 0.124 |
| Perspective policy | 0.354 | 0.470 | 0.962 | 0.104 |
| Evidence aggregation | 0.160 | 0.192 | 0.207 | 0.016 |
| Storage access | 0.139 | 0.171 | 0.183 | 0.038 |
| Frame rendering | 0.262 | 0.315 | 0.341 | 0.029 |

Policy bookkeeping is sub-millisecond per component; candidate retrieval dominates this 1,000-record mixed lexical/vector workload. Timings are one Windows host and one warm process, not cross-machine confidence intervals.

