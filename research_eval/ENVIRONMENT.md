# Environment

| Item | Value |
|---|---|
| Machine | MSI Stealth GS66 12UH |
| CPU | Intel Core i9-12900H, 14 cores / 20 logical |
| RAM | 68,473,409,536 bytes (~63.8 GiB) |
| OS | Windows 11 Pro 64-bit, build 26200 |
| Python | 3.10.0, MSC v.1929, `C:\Python310\python.exe` |
| NumPy | 2.2.6 |
| pytest | 9.0.2 |
| scikit-learn | 1.7.1 |
| FAISS CPU | 1.15.0, isolated under `research_eval/vendor` |
| USearch | 2.26.1, isolated under `research_eval/vendor` |
| Benchmark threads | `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1` for controlled kernel runs |

Latency comparisons in the kernel runs used the same process, vectors, queries, CPU, and one-thread settings. Index build implementations may still create their own internal workers. The initial QMSum and shipped runs were functional reproductions, not isolated laboratory timing runs; quality metrics are the primary evidence there.

Raw machine and Python metadata are in `raw/hardware.json` and `raw/environment_python.json`.
