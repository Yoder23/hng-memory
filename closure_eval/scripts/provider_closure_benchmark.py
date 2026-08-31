from __future__ import annotations

import argparse
import gc
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1"
VENDOR = ROOT / "research_eval" / "vendor"
sys.path[:0] = [str(VENDOR), str(SOURCE / "src")]

import numpy as np
from hngfrontier import FaissBinaryRetriever, SemanticKind, SemanticValue, USearchBinaryRetriever


def percentile(values, q):
    values = sorted(values); position = (len(values)-1)*q; low=math.floor(position); high=math.ceil(position)
    return values[low] if low == high else values[low]*(high-position)+values[high]*(position-low)


def rss_bytes():
    try:
        import psutil
        return psutil.Process().memory_info().rss
    except Exception: return 0


def provider_for(mode):
    if mode == "usearch": return USearchBinaryRetriever(expansion_search=128)
    return FaissBinaryRetriever(mode=mode, exact_fallback=False)


def run_mode(mode, *, n, dim, queries, noise, seed):
    try:
        import faiss
        faiss.omp_set_num_threads(1)
    except Exception:
        pass
    rng=np.random.default_rng(seed); packed=rng.integers(0,256,size=(n,dim//8),dtype=np.uint8)
    provider=provider_for(mode); before=rss_bytes(); start=time.perf_counter()
    for i in range(n): provider.add(str(i),SemanticValue(SemanticKind.HDC_BINARY,packed[i],dim,"benchmark"))
    registration=time.perf_counter()-start; provider.rebuild(); after=rss_bytes()
    chosen=rng.choice(n,size=queries,replace=False); lat=[]; correct=0
    for source in chosen:
        query=packed[source].copy(); flips=rng.choice(dim,size=max(1,int(dim*noise)),replace=False)
        query[flips//8] ^= (1 << (7-(flips%8))).astype(np.uint8)
        value=SemanticValue(SemanticKind.HDC_BINARY,query,dim,"benchmark")
        start=time.perf_counter(); hits=provider.search(value,top_k=1); lat.append((time.perf_counter()-start)*1000)
        correct += bool(hits and hits[0].evidence_id == str(source))
    update=SemanticValue(SemanticKind.HDC_BINARY,packed[0].copy(),dim,"benchmark")
    start=time.perf_counter(); provider.add("fresh",update); update_ms=(time.perf_counter()-start)*1000
    start=time.perf_counter(); fresh=provider.search(update,top_k=10); fresh_ms=(time.perf_counter()-start)*1000
    stats=dict(provider.stats()); index_bytes=0
    try:
        if mode == "usearch":
            with tempfile.TemporaryDirectory() as td:
                path=Path(td)/"index.usearch"; provider._index.save(str(path)); index_bytes=path.stat().st_size
        else:
            import faiss; index_bytes=int(faiss.serialize_index_binary(provider._index).size)
    except Exception: pass
    return {"mode":mode,"n":n,"dim":dim,"queries":queries,"noise":noise,
            "exact_source_top1":correct/queries,"p50_ms":statistics.median(lat),
            "p95_ms":percentile(lat,.95),"p99_ms":percentile(lat,.99),"stdev_ms":statistics.pstdev(lat),
            "registration_seconds":registration,"build_ms":stats.get("build_ms",0),
            "update_add_ms":update_ms,"fresh_query_ms":fresh_ms,
            "fresh_visible":any(hit.evidence_id=="fresh" for hit in fresh),
            "threads":1,"index_bytes":index_bytes,"rss_delta_bytes":max(0,after-before),"stats":stats}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--n",type=int,default=100_000)
    parser.add_argument("--dim",type=int,default=4096); parser.add_argument("--queries",type=int,default=80)
    parser.add_argument("--noise",type=float,default=.02); parser.add_argument("--seed",type=int,default=20260831)
    parser.add_argument("--modes",nargs="+",default=["faiss-flat","faiss-ivf","faiss-hnsw","faiss-multihash","usearch"])
    parser.add_argument("--output",required=True); args=parser.parse_args()
    results=[]
    for mode in args.modes:
        result=run_mode(mode,n=args.n,dim=args.dim,queries=args.queries,noise=args.noise,seed=args.seed)
        results.append(result); print(json.dumps(result)); gc.collect()
    payload={"config":vars(args),"results":results}
    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(payload,indent=2),encoding="utf-8")


if __name__ == "__main__": main()
