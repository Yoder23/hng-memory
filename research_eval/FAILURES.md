# Failures and limitations

1. No Git provenance and no runnable 0.3.1 artifact prevent the requested source-level historical regression.
2. Shipped examples and several benchmarks hard-code `/tmp` or `/mnt/data`; unchanged runs are not portable to Windows.
3. `SegmentedNpyVectorStore.sync()` raises `EBADF` on Windows. Durability claims were not validated here.
4. Fresh 15%-noise assistant accuracy is 98.958%, contradicting the 100% claim.
5. The assistant's changed-world success depends on supplying `sequence`; omit it and obsolete-action selection is 100%.
6. Perspective ground truth is directly determined by explicit persona/context fields. A normal dictionary and a dense multi-head equivalent also score 100%.
7. The synthetic document workload grants HNG role-head priority queries while ordinary baselines do not get equivalent priority information. Once equalized, priority-first importance selection scores 100% on all synthetic quality metrics, versus HNG's 98.05% key claims, and is much faster.
8. On 20 official QMSum test meetings, the boundary detector returns one segment for every document. Uniform sampling beats HNG on ROUGE-1/2/L; BM25 beats it on relevant-span hit@5.
9. The shipped QMSum harness stores the last ingestion time in every per-document row. The independent harness fixes this.
10. HNG ANN is slower than FAISS BinaryIVF at matched 100% recall at 100K and 1M.
11. Adversarial memory passes 5/11 cases. It over-supports an old majority over a recent failure, poisoned records, duplicates, missing required heads, permissive action thresholds, and incorrect authoritative profiles.
12. LongMemEval-V2, LoCoMo-Plus, PersonaMem-v2, LaMP, GovReport, BillSum, RAPTOR, GraphRAG, and full agent-memory competitors were not locally reproduced. No HNG win is inferred from their absence.
13. The package contains `OPEN_SOURCE_LICENSE_TODO.md` and no selected license, reducing redistribution/operational readiness.
14. QMSum results are a fixed first-20 test subset, not the entire test set, and use the deliberately simple shipped non-neural encoder.
15. Kernel latency distributions are repeated warm-process queries, not multiple independent process launches; confidence intervals, cold-cache runs, thread scaling, and sustained concurrent update tests remain undone.
16. No common LLM reader/summarizer was available, so downstream assistant success and generated-summary factuality were not evaluated. Retrieval improvements must not be interpreted as end-to-end gains.
