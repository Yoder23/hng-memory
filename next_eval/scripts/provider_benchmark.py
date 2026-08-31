from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1"
sys.path.insert(0, str(ROOT / "research_eval" / "vendor"))
sys.path.insert(0, str(SOURCE / "src"))

import faiss  # noqa: E402
from hngfrontier import FaissBinaryRetriever, SemanticValue  # noqa: E402


def percentile(values, q): return float(np.percentile(np.asarray(values), q))


def main():
    n, dim, queries = 100_000, 4096, 80
    rng = np.random.default_rng(20260831)
    matrix = rng.integers(0, 256, size=(n, dim // 8), dtype=np.uint8)
    query_ids = rng.choice(n, size=queries, replace=False)
    query_matrix = matrix[query_ids].copy()
    for row in query_matrix:
        bits = rng.choice(dim, size=int(dim * .02), replace=False)
        row[bits >> 3] ^= (1 << (bits & 7)).astype(np.uint8)
    exact = faiss.IndexBinaryFlat(dim); exact.add(matrix)
    _, truth = exact.search(query_matrix, 1)
    provider = FaissBinaryRetriever(mode="faiss-ivf", nlist=256, nprobe=32)
    add_start = time.perf_counter()
    for i, vector in enumerate(matrix):
        provider.add(str(i), SemanticValue.hdc(np.unpackbits(vector, bitorder="little", count=dim)))
    add_seconds = time.perf_counter() - add_start
    provider.rebuild()
    allowed = {str(i) for i in range(n)}
    latencies, correct = [], 0
    for qi, vector in enumerate(query_matrix):
        value = SemanticValue.hdc(np.unpackbits(vector, bitorder="little", count=dim))
        start = time.perf_counter(); hits = provider.search(value, top_k=10, allowed_ids=allowed)
        latencies.append((time.perf_counter() - start) * 1000)
        correct += int(bool(hits) and hits[0].evidence_id == str(int(truth[qi, 0])))
    result = {
        "config": {"n": n, "dim": dim, "queries": queries, "threads": 1, "noise": .02},
        "backend": provider.stats(), "python_registration_seconds": add_seconds,
        "exact_top1_agreement": correct / queries,
        "median_ms": statistics.median(latencies), "p95_ms": percentile(latencies, 95), "p99_ms": percentile(latencies, 99),
        "note": "Provider timing includes Python wrapper/allowed-ID filtering; final control-plane exact floors are benchmarked separately.",
    }
    raw = ROOT / "next_eval" / "raw"; raw.mkdir(parents=True, exist_ok=True)
    (raw / "PROVIDER_100K.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
