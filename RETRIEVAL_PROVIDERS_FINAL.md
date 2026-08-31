# Retrieval provider recommendation

All closure trials use the same 4,096-bit rows, 2% query noise, one FAISS thread, and exact source identity as the recall target. Raw files: `PROVIDERS_100K.json`, `PROVIDERS_1M.json`, and `PROVIDER_GEOMETRIES_100K.json`. The inherited feasible 10M run is preserved at `research_eval/raw/retrieval_kernel_10m.results.json` rather than repeated at material memory risk.

## 100K independent vectors

| Provider | Source top-1 | p50 ms | p95 ms | p99 ms | Build ms | Index MiB |
|---|---:|---:|---:|---:|---:|---:|
| FAISS Flat | 100% | 4.489 | 5.253 | 5.954 | 98.7 | 48.8 |
| FAISS IVF | 100% | 0.528 | 0.866 | 1.644 | 9,386 | 49.7 |
| FAISS HNSW | 97.5% | 1.299 | — | — | 45,685 | 74.8 |
| FAISS MultiHash | 100% | 0.160 | 0.244 | 1.088 | 360.6 | 52.1 |
| USearch Hamming | 87.5% | 8.375 | — | — | 23,514 | 63.0 |

MultiHash's independent-vector win did not generalize: at 100K correlated vectors with low leading-bit entropy it remained exact but slowed to 25.073 ms p50, versus IVF at 0.597 ms. This is why it is implemented as an explicit provider, not the automatic default.

## 1M independent vectors

| Provider | Source top-1 | p50 ms | p95 ms | p99 ms | Build s | Index MiB |
|---|---:|---:|---:|---:|---:|---:|
| FAISS Flat | 100% | 42.494 | 45.681 | 46.469 | 1.14 | 488.3 |
| FAISS IVF | 100% | 3.257 | 3.727 | 3.766 | 58.66 | 496.4 |
| FAISS MultiHash | 100% | 0.742 | 0.941 | 1.041 | 2.99 | 509.6 |

All tested providers exposed a fresh exact mutable tail before rebuild. Provider registration/update, RSS, and serialized byte values are in the raw JSON.

## Selection

- Below 50K or whenever exact exhaustive truth is required: FAISS BinaryFlat.
- 50K through multi-million, mixed/unknown geometry: FAISS BinaryIVF; this remains `faiss-auto`.
- Stable, benchmarked high-entropy geometry with a strict latency target: explicit MultiHash after workload-specific validation.
- HNSW: not recommended for the measured binary HDC workload; slower build and imperfect recall.
- USearch: supported cleanly for portability/experimentation, but not recommended by these recall/build results.
- 10M: retain the prior measured FAISS IVF recommendation; rerun only on a controlled high-memory host.
- Reference HNG: dependency-free correctness fallback and research baseline, not production ANN default.

