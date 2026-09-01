# Scaling and retrieval infrastructure

Evidence source: the immutable 0.7.0rc1 baseline at
`e57db1b1e92329e9b8f2b173be9a506d2b898da8`. All measurements below are local, single-threaded,
4,096-bit synthetic binary-vector retrieval unless stated otherwise. They establish backend
behavior, not assistant intelligence or governed-record database scale.

## 100K vectors

| Backend | Exact-source top-1 | p50 | p95 | p99 | Build | Index bytes |
|---|---:|---:|---:|---:|---:|---:|
| FAISS BinaryFlat | 100.0% | 4.625 ms | 5.421 ms | 6.619 ms | 0.103 s | 51,200,033 |
| FAISS BinaryIVF | 100.0% | 0.624 ms | 0.779 ms | 1.678 ms | 23.899 s | 52,164,435 |
| FAISS BinaryHNSW | 97.5% | 1.332 ms | 1.678 ms | 2.425 ms | 47.277 s | 78,420,810 |
| FAISS BinaryMultiHash | 100.0% | 0.157 ms | 0.214 ms | 1.109 ms | 0.354 s | 54,593,286 |
| USearch Hamming | 85.0% | 9.031 ms | 10.773 ms | 12.561 ms | 24.272 s | 66,066,592 |

At this frozen operating point BinaryMultiHash is the local Pareto winner. USearch is not
competitive at the tested expansion setting and is not described as defeated beyond this exact
geometry/configuration.

## 1M vectors

| Backend | Exact-source top-1 | p50 | p95 | p99 | Build | Index bytes |
|---|---:|---:|---:|---:|---:|---:|
| FAISS BinaryFlat | 100.0% | 46.706 ms | 56.406 ms | 56.707 ms | 1.202 s | 512,000,033 |
| FAISS BinaryIVF | 100.0% | 3.156 ms | 3.684 ms | 3.852 ms | 141.050 s | 520,520,115 |
| FAISS BinaryMultiHash | 100.0% | 0.759 ms | 1.045 ms | 1.149 ms | 3.020 s | 534,359,526 |

Fresh post-build additions were visible in every 100K/1M provider arm. Update-add latency was
0.0034-0.0050 ms, but the first query that merged the fresh tail cost 6.9-142.8 ms depending on
scale/backend.

## 10M vectors

The inherited 10M experiment used independent random geometry and ten queries:

| Backend/configuration | Top-1 agreement | p50 | p95 | p99 | Bytes |
|---|---:|---:|---:|---:|---:|
| FAISS BinaryFlat | reference | 485.908 ms | 546.888 ms | 556.390 ms | 5,120,000,033 |
| HNG index | 100.0% | 50.565 ms | 56.258 ms | 57.517 ms | 800,394,920 index; 5,920,394,920 incl. raw |
| FAISS BinaryIVF nprobe=16 | 100.0% | 27.354 ms | 33.076 ms | 33.586 ms | 5,200,133,235 |

FAISS BinaryIVF is faster than the HNG index at matched top-1 agreement in this 10M run. This is a
successful backend-selection result: FAISS remains the preferred dependency where this geometry
matches deployment. USearch was not run at 10M because its 1M build took 374 seconds and had not
reached matched recall by `expansion_search=128`; the projected run would exceed an hour. That is a
resource-bound omission, not a claimed loss at 10M.

## Governance component profile

For 1,000 records and 300 queries at 2,048 dimensions, retrieval dominated end-to-end memory work:

| Component | p50 | p95 | p99 |
|---|---:|---:|---:|
| retrieval | 13.834 ms | 18.719 ms | 21.476 ms |
| perspective policy | 0.228 ms | 0.377 ms | 0.754 ms |
| trust evaluation | 0.174 ms | 0.245 ms | 0.377 ms |
| temporal governance | 0.116 ms | 0.223 ms | 0.712 ms |
| evidence aggregation | 0.109 ms | 0.173 ms | 0.218 ms |
| exact vector verification | 0.036 ms | 0.058 ms | 0.078 ms |
| independence grouping | 0.038 ms | 0.059 ms | 0.105 ms |
| frame rendering | 0.191 ms | 0.291 ms | 0.377 ms |

## Unmet scaling scope

The requested 10K/100K/1M/10M/100M **governed evidence-record** study is not complete. Existing
large-scale artifacts cover binary retrieval providers, not full metadata filtering, temporal
policy, provenance, updates, restart/rebuild, and storage footprint at every scale. No 100M result
is claimed. A future run must distinguish retrieval cardinality from the bounded candidate set that
the governance layer actually assesses.
