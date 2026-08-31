"""Matched-data binary retrieval comparison for HNG, FAISS, and USearch.

This is deliberately representation-fair: every backend receives the same packed
binary vectors and Hamming queries.  FAISS BinaryFlat is the exact ground truth.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research_eval" / "vendor"))
sys.path.insert(0, str(ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"))

import faiss
import numpy as np
import psutil
from usearch.index import Index as USearchIndex

from hngfrontier.index import HDCIndex
from hngfrontier.vectors import hamming_similarity, pack_hv


class ArrayProvider:
    def __init__(self, packed: np.ndarray, dim: int):
        self.data = np.ascontiguousarray(packed, dtype=np.uint8)
        self.hv_dim = dim

    @property
    def count(self) -> int:
        return self.data.shape[0]

    def read_slots(self, slots: np.ndarray) -> np.ndarray:
        return self.data[np.asarray(slots, dtype=np.intp)]

    def read_range(self, start: int, end: int) -> np.ndarray:
        return self.data[start:end]

    def exact_topk(self, query, slots: np.ndarray, top_k: int):
        slots = np.asarray(slots, dtype=np.intp)
        if not slots.size:
            return []
        sims = hamming_similarity(self.data[slots], pack_hv(query, self.hv_dim), self.hv_dim)
        k = min(top_k, slots.size)
        ii = np.argpartition(sims, -k)[-k:]
        ii = ii[np.argsort(sims[ii])[::-1]]
        return [(int(slots[i]), float(sims[i])) for i in ii]


def percentile(xs: list[float], p: float) -> float:
    return float(np.percentile(np.asarray(xs, dtype=np.float64), p))


def timing(xs: list[float]) -> dict:
    return {
        "samples": len(xs),
        "median_ms": statistics.median(xs),
        "p95_ms": percentile(xs, 95),
        "p99_ms": percentile(xs, 99),
    }


def mutate_rows(source: np.ndarray, dim: int, frac: float, rng: np.random.Generator) -> np.ndarray:
    bits = np.unpackbits(source, axis=1, bitorder="little", count=dim)
    bits ^= (rng.random(bits.shape) < frac)
    return np.packbits(bits, axis=1, bitorder="little")


def dataset(n: int, dim: int, geometry: str, rng: np.random.Generator) -> np.ndarray:
    width = dim // 8
    if geometry == "independent":
        return rng.integers(0, 256, size=(n, width), dtype=np.uint8)
    families = min(2048, max(128, n // 64))
    bases = rng.integers(0, 256, size=(families, width), dtype=np.uint8)
    out = np.empty((n, width), dtype=np.uint8)
    frac = 0.055 if geometry == "clustered_hard_negatives" else 0.16
    batch = 4096
    for start in range(0, n, batch):
        end = min(n, start + batch)
        parent = bases[np.arange(start, end) % families]
        out[start:end] = mutate_rows(parent, dim, frac, rng)
    return out


def query_set(x: np.ndarray, dim: int, q: int, rng: np.random.Generator):
    targets = rng.choice(x.shape[0], size=q, replace=False)
    queries = mutate_rows(x[targets], dim, 0.02, rng)
    return targets, queries


def evaluate_ids(pred: list[np.ndarray], truth: np.ndarray) -> dict:
    r1 = []
    r10 = []
    agreement = []
    for p, t in zip(pred, truth):
        ids = [int(v) for v in np.asarray(p).ravel() if int(v) >= 0]
        gold = [int(v) for v in np.asarray(t).ravel() if int(v) >= 0]
        r1.append(bool(ids and gold and ids[0] == gold[0]))
        r10.append(bool(set(ids[:10]) & set(gold[:10])))
        agreement.append(bool(ids and gold and ids[0] == gold[0]))
    return {"recall_at_1": float(np.mean(r1)), "recall_at_10_overlap": float(np.mean(r10)),
            "exact_top1_agreement": float(np.mean(agreement))}


def bench(n: int, dim: int, geometry: str, qcount: int, work: Path) -> dict:
    rng = np.random.default_rng(20260831 + n + sum(map(ord, geometry)))
    process = psutil.Process()
    rss0 = process.memory_info().rss
    t = time.perf_counter(); x = dataset(n, dim, geometry, rng); data_s = time.perf_counter() - t
    targets, queries = query_set(x, dim, qcount, rng)

    faiss.omp_set_num_threads(1)
    flat = faiss.IndexBinaryFlat(dim)
    t = time.perf_counter(); flat.add(x); flat_build = time.perf_counter() - t
    truth = [];
    flat_ms = []
    for query in queries:
        t = time.perf_counter(); _d, ids = flat.search(query.reshape(1, -1), 10); flat_ms.append((time.perf_counter()-t)*1000)
        truth.append(ids[0].copy())
    truth_a = np.asarray(truth)

    provider = ArrayProvider(x, dim)
    t = time.perf_counter()
    hng = HDCIndex.build(provider, table_count=12, bits_per_table=12, sketch_bits=256, seed=0x484E4746)
    hng_build = time.perf_counter() - t
    hng_pred = []; hng_ms = []; hng_candidates = []
    for query in queries:
        query_bits = np.unpackbits(query, bitorder="little", count=dim)
        t = time.perf_counter(); result = hng.search(provider, query_bits, top_k=10, probe_radius=1, rerank_candidates=256)
        hng_ms.append((time.perf_counter()-t)*1000)
        hng_pred.append(np.asarray([i for i, _ in result.hits], dtype=np.int64))
        hng_candidates.append(result.stats.exact_fraction)
    hng_path = work / f"hng-{n}-{geometry}.npz"; hng.save(hng_path)

    quant = faiss.IndexBinaryFlat(dim)
    nlist = 256 if n <= 100_000 else 1024
    ivf = faiss.IndexBinaryIVF(quant, dim, nlist)
    train = x if n <= 100_000 else x[rng.choice(n, size=min(n, 200_000), replace=False)]
    t = time.perf_counter(); ivf.train(train); ivf.add(x); ivf_build = time.perf_counter() - t
    ivf_runs = {}
    for nprobe in (1, 4, 16, 64):
        ivf.nprobe = nprobe; pred=[]; lat=[]
        for query in queries:
            t=time.perf_counter(); _d, ids=ivf.search(query.reshape(1,-1),10); lat.append((time.perf_counter()-t)*1000); pred.append(ids[0].copy())
        ivf_runs[str(nprobe)] = {**evaluate_ids(pred, truth_a), **timing(lat), "candidate_fraction_estimate": nprobe/nlist}

    hnsw_result = {"status": "skipped_at_1m"}
    if n <= 100_000:
        hnsw = faiss.IndexBinaryHNSW(dim, 32)
        hnsw.hnsw.efConstruction = 80
        t=time.perf_counter(); hnsw.add(x); hnsw_build=time.perf_counter()-t
        runs={}
        for ef in (16,64,128):
            hnsw.hnsw.efSearch=ef; pred=[]; lat=[]
            for query in queries:
                t=time.perf_counter(); _d,ids=hnsw.search(query.reshape(1,-1),10);lat.append((time.perf_counter()-t)*1000);pred.append(ids[0].copy())
            runs[str(ef)]={**evaluate_ids(pred,truth_a),**timing(lat)}
        hnsw_result={"build_seconds":hnsw_build,"runs":runs,
                     "serialized_bytes":int(faiss.serialize_index_binary(hnsw).size)}

    usearch = USearchIndex(ndim=dim, metric="hamming", dtype="b1", connectivity=16,
                           expansion_add=128, expansion_search=64)
    t=time.perf_counter(); usearch.add(np.arange(n, dtype=np.uint64), x); usearch_build=time.perf_counter()-t
    usearch_runs={}
    for expansion in (16,64,128):
        usearch.expansion_search=expansion; pred=[]; lat=[]
        for query in queries:
            t=time.perf_counter(); matches=usearch.search(query,10);lat.append((time.perf_counter()-t)*1000);pred.append(np.asarray(matches.keys))
        usearch_runs[str(expansion)]={**evaluate_ids(pred,truth_a),**timing(lat)}
    usearch_path=work/f"usearch-{n}-{geometry}.usearch"; usearch.save(str(usearch_path))

    rss1 = process.memory_info().rss
    return {
        "config":{"n":n,"dim":dim,"geometry":geometry,"queries":qcount,"threads":1,"query_noise":0.02},
        "data_generation_seconds":data_s,
        "raw_vector_bytes":int(x.nbytes),
        "rss_delta_bytes_end_minus_start":int(rss1-rss0),
        "faiss_binary_flat":{"build_seconds":flat_build,"serialized_bytes":int(faiss.serialize_index_binary(flat).size),
                             **timing(flat_ms),"recall_at_1":1.0,"exact_top1_agreement":1.0},
        "hng":{"build_seconds":hng_build,"index_bytes":hng_path.stat().st_size,
               **timing(hng_ms),**evaluate_ids(hng_pred,truth_a),
               "median_exact_candidate_fraction":float(np.median(hng_candidates))},
        "faiss_binary_ivf":{"build_seconds":ivf_build,"nlist":nlist,
                            "serialized_bytes":int(faiss.serialize_index_binary(ivf).size),"runs":ivf_runs},
        "faiss_binary_hnsw":hnsw_result,
        "usearch":{"build_seconds":usearch_build,"index_bytes":usearch_path.stat().st_size,"runs":usearch_runs},
    }


def main() -> None:
    ap=argparse.ArgumentParser();ap.add_argument("--scales",default="100000,1000000");ap.add_argument("--dim",type=int,default=4096)
    ap.add_argument("--queries",type=int,default=80);ap.add_argument("--output",type=Path,default=ROOT/"research_eval/raw/retrieval_kernel.results.json")
    args=ap.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    scales=[int(x) for x in args.scales.split(",") if x.strip()]
    work=ROOT/"research_eval/run_data/retrieval_kernel";work.mkdir(parents=True,exist_ok=True)
    results=[]
    for n in scales:
        geometries=("independent","clustered_hard_negatives","correlated_families") if n<=100_000 else ("independent",)
        q=args.queries if n<=100_000 else min(30,args.queries)
        for geometry in geometries:
            print(f"running n={n} geometry={geometry}",flush=True)
            results.append(bench(n,args.dim,geometry,q,work))
    out={"versions":{"python":sys.version,"numpy":np.__version__,"faiss":faiss.__version__},"results":results}
    args.output.write_text(json.dumps(out,indent=2),encoding="utf-8");print(json.dumps(out,indent=2))


if __name__=="__main__": main()
