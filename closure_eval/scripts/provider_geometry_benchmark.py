"""Distribution-sensitive FAISS provider comparison on matched binary vectors."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "research_eval" / "vendor"),
                str(ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src")]

import numpy as np
from hngfrontier import FaissBinaryRetriever, SemanticKind, SemanticValue


def mutate(rows: np.ndarray, dim: int, fraction: float, rng: np.random.Generator) -> np.ndarray:
    bits = np.unpackbits(rows, axis=1, bitorder="little", count=dim)
    bits ^= rng.random(bits.shape) < fraction
    return np.packbits(bits, axis=1, bitorder="little")


def make_data(n: int, dim: int, geometry: str, rng: np.random.Generator) -> np.ndarray:
    width = dim // 8
    if geometry == "independent":
        return rng.integers(0, 256, size=(n, width), dtype=np.uint8)
    families = min(2048, max(128, n // 64))
    bases = rng.integers(0, 256, size=(families, width), dtype=np.uint8)
    fraction = .055 if geometry == "clustered_hard_negatives" else .16
    out = np.empty((n, width), dtype=np.uint8)
    for start in range(0, n, 4096):
        end = min(n, start + 4096)
        out[start:end] = mutate(bases[np.arange(start, end) % families], dim, fraction, rng)
    if geometry == "correlated":
        # Deliberately lower entropy in the leading bits used by common hash schemes.
        out[:, :16] = bases[0, :16]
    return out


def timing(values: list[float]) -> dict[str, float]:
    values = sorted(values)
    def pct(q: float) -> float:
        p = (len(values) - 1) * q; lo = math.floor(p); hi = math.ceil(p)
        return values[lo] if lo == hi else values[lo] * (hi - p) + values[hi] * (p - lo)
    return {"median_ms": statistics.median(values), "p95_ms": pct(.95),
            "p99_ms": pct(.99), "stdev_ms": statistics.pstdev(values)}


def run(mode: str, data: np.ndarray, dim: int, qcount: int,
        rng: np.random.Generator) -> dict[str, object]:
    try:
        import faiss
        faiss.omp_set_num_threads(1)
    except ImportError:
        pass
    provider = FaissBinaryRetriever(mode=mode, exact_fallback=False)
    start = time.perf_counter()
    for i, row in enumerate(data):
        provider.add(str(i), SemanticValue(SemanticKind.HDC_BINARY, row, dim, "geometry-v1"))
    registration = time.perf_counter() - start
    provider.rebuild()
    targets = rng.choice(len(data), size=qcount, replace=False)
    latencies: list[float] = []; at1 = 0; at10 = 0
    for target in targets:
        query = mutate(data[target:target + 1], dim, .02, rng)[0]
        value = SemanticValue(SemanticKind.HDC_BINARY, query, dim, "geometry-v1")
        start = time.perf_counter(); hits = provider.search(value, top_k=10)
        latencies.append((time.perf_counter() - start) * 1000)
        ids = [hit.evidence_id for hit in hits]
        at1 += bool(ids and ids[0] == str(target)); at10 += str(target) in ids
    return {"mode": mode, "recall_source_at_1": at1 / qcount,
            "recall_source_at_10": at10 / qcount, "registration_seconds": registration,
            **timing(latencies), "provider": dict(provider.stats())}


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=100_000)
    ap.add_argument("--dim", type=int, default=4096); ap.add_argument("--queries", type=int, default=80)
    ap.add_argument("--output", type=Path, required=True); args = ap.parse_args()
    results = []
    for offset, geometry in enumerate(("independent", "clustered_hard_negatives", "correlated")):
        rng = np.random.default_rng(20260831 + offset); data = make_data(args.n, args.dim, geometry, rng)
        for mode in ("faiss-flat", "faiss-ivf", "faiss-multihash"):
            result = {"geometry": geometry, **run(mode, data, args.dim, args.queries, rng)}
            results.append(result); print(json.dumps(result))
    payload = {"config": {"n": args.n, "dim": args.dim, "queries": args.queries,
                           "query_noise": .02, "threads": 1}, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
