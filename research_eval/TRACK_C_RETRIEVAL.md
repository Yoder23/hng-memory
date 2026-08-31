# Track C: retrieval kernel

## Verdict

HNGIX does not justify replacing an established ANN library. It is compact and builds quickly, but FAISS BinaryIVF is faster at matched 100% exact top-1 agreement at 100K, 1M, and 10M on the tested 4,096-bit vectors. HNG should retain its high-level per-head semantics and use FAISS internally.

## Protocol

- Same packed binary vectors and Hamming ground truth for every system.
- One CPU thread: `OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1`.
- Query = a corpus vector with 2% bits flipped.
- Ground truth = FAISS `IndexBinaryFlat` exact nearest neighbor.
- Synthetic geometries at 100K: independent random, clustered hard negatives, correlated families.
- Independent random at 1M and 10M.
- Match on exact top-1 agreement, not default search settings.
- 80 queries at 100K, 30 at 1M, and 10 at 10M. Tail percentiles at 10M are directional because the sample is small.

No real HDC trace corpus was bundled. The synthetic results characterize the kernel, not application quality.

## Matched-recall results (Tier A)

### 100K vectors

| Geometry / index | Exact top-1 | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|
| Independent: HNG | 100% | 1.270 | 1.699 | 1.949 |
| Independent: FAISS BinaryIVF, nprobe 16 | 100% | 0.296 | 0.581 | 0.722 |
| Independent: FAISS BinaryHNSW, ef 128 | 100% | 1.270 | 1.720 | 1.900 |
| Independent: FAISS BinaryFlat | 100% | 4.338 | 5.114 | 6.044 |
| Independent: USearch, expansion 128 | 87.5% | 1.919 | 2.616 | 2.845 |
| Clustered: HNG | 100% | 1.324 | 1.968 | 2.486 |
| Clustered: FAISS BinaryIVF, nprobe 1 | 100% | 0.0318 | 0.0741 | 0.0844 |
| Clustered: FAISS BinaryHNSW, ef 64 | 100% | 0.2226 | 0.3389 | 0.3720 |
| Clustered: USearch, expansion 64 | 100% | 0.4370 | 0.7791 | 1.1235 |
| Correlated: HNG | 100% | 1.442 | 2.527 | 3.166 |
| Correlated: FAISS BinaryIVF, nprobe 1 | 100% | 0.0312 | 0.0617 | 0.1167 |
| Correlated: FAISS BinaryHNSW, ef 64 | 100% | 0.364 | 0.528 | 0.584 |
| Correlated: USearch, expansion 64 | 100% | 0.674 | 1.103 | 1.244 |

HNG exactly rescored a median 0.256% of the 100K corpus. For independent data it built in 0.392 s and used 8.40 MB for routing plus the shared 51.2 MB raw vectors. FAISS BinaryIVF took 18.2 s to train/build and serialized to 52.13 MB including vectors. The tradeoff is therefore fast build and small auxiliary index versus query speed.

### 1M vectors, independent

| Index | Exact top-1 | p50 ms | p95 ms | p99 ms | Build s | Stored bytes |
|---|---:|---:|---:|---:|---:|---:|
| HNG | 100% | 6.744 | 9.513 | 9.952 | 5.25 | 80.40 MB index + 512 MB raw |
| FAISS BinaryIVF, nprobe 64 | 100% | 2.858 | 3.301 | 3.352 | 146.07 | 520.53 MB total |
| FAISS BinaryFlat | 100% | 49.046 | 54.156 | 57.522 | 0.097 | 512.00 MB total |
| USearch, expansion 128 | 20% | 2.498 | 2.987 | 3.253 | 374.24 | 660.58 MB total |

HNG exactly rescored 0.0256% of the corpus. USearch is not a matched-recall competitor in this geometry at the tested settings.

### 10M vectors, independent

| Index | Exact top-1 | p50 ms | p95 ms | p99 ms | Build s | Total storage |
|---|---:|---:|---:|---:|---:|---:|
| HNG | 100% | 45.882 | 46.657 | 46.742 | 84.89 | 5.920 GB |
| FAISS BinaryIVF, nprobe 16 | 100% | 28.014 | 28.972 | 28.987 | 90.38 | 5.200 GB |
| FAISS BinaryFlat | 100% | 424.170 | 434.845 | 436.899 | 0.793 | 5.120 GB |

HNG rescored 0.00256% of the corpus and used about 800 MB of routing index. Peak measured process RSS after building FAISS IVF was 16.36 GB. USearch was not run at 10M because its 1M build took 374 s and recall was only 20% at expansion 128; this is an unavailable comparison, not an HNG win.

## Multi-head semantics

The engine's valuable behavior happens above ANN:

1. exact metadata eligibility;
2. candidate routing per independent head;
3. configurable union/fusion;
4. exact full-HV similarity for every required head;
5. fail-closed per-head floors.

A standard replacement can preserve this exactly: maintain one FAISS binary index per head, retrieve a calibrated candidate set from each, union or intersect IDs, apply relational eligibility, and compute exact Hamming similarity before the final decision. The local structured baseline already shows that exhaustive independent-head conjunction reproduces HNG correctness.

Weighted fusion and reciprocal-rank fusion are useful ranking baselines but are not semantically identical: a high score on one head can compensate for an incompatible required head. They should route candidates only; exact floors should remain final constraints. Milvus and Weaviate can orchestrate multiple vectors, but were not installed because a local service comparison would not improve the direct low-level result.

## Unmeasured or incomplete dimensions

- BinaryHash and BinaryMultiHash were researched but not executed; BinaryIVF already falsified the low-level superiority claim.
- No statistically robust insertion/update-latency, thread-scaling, or cold-cache matrix was completed.
- HNG's unindexed tail is searched exactly by design and shipped tests cover visibility, but freshness under concurrent sustained writes was not stress-tested.
- HNG persists raw slabs and disposable indexes separately; FAISS sizes above are serialized index sizes and include stored vectors. Totals are reported to avoid a misleading index-only comparison.
- Qdrant binary quantization is not native supplied-bit Hamming, and DiskANN lacked a clean like-for-like packed-Hamming path here; neither absence counts as a win.

## Recommended kernel

Use FAISS BinaryIVF per head for static or batch-built HDC memory. Keep a small exact mutable tail for newly committed items, merge/rebuild in the background, and perform exact full-vector floors after candidate collection. Evaluate USearch only if incremental mutation and its API are more important than independent-random recall. HNGIX may remain as a dependency-free fallback, not the default production kernel.

