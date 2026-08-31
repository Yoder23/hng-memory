"""Public QMSum extraction/synopsis harness for HNG Frontier.

Usage:
    python benchmarks/qmsum_public_hdc.py /path/to/QMSum/data/ALL/jsonl/test.jsonl --limit 20

This benchmark intentionally uses a small deterministic, non-neural HDC text encoder. It is
NOT a substitute for the application's real HDC interpreter. Its purpose is to make the
publication protocol reproducible on public human-authored meetings and annotations.

Metrics:
- query span hit@k for QMSum specific queries with annotated relevant spans;
- ROUGE-1/2/L F1 for the extractive whole-meeting evidence rendering against the human general
  summary (a conservative evaluation because HNG is not generating abstractive prose);
- evidence budget, segment count and latency.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Iterable

import numpy as np

from hngfrontier import CallableDocumentAdapter, DocumentUnitEncoding, HDCDocumentMemory

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")


def tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text)]


class TextHDC:
    """Deterministic bag-of-token HDC encoder; no ML/LLM dependency."""
    def __init__(self, dim: int = 4096):
        self.dim = int(dim)
        self._cache: dict[tuple[str, str], np.ndarray] = {}

    def atom(self, token: str, space: str) -> np.ndarray:
        key = (space, token)
        out = self._cache.get(key)
        if out is not None:
            return out
        digest = hashlib.blake2b(f"{space}\0{token}".encode(), digest_size=8).digest()
        seed = int.from_bytes(digest, "little")
        out = np.random.default_rng(seed).choice(np.array([-1, 1], np.int8), size=self.dim)
        self._cache[key] = out
        return out

    def encode(self, text: str, *, space: str, bigrams: bool = True) -> np.ndarray:
        ts = tokens(text)
        feats = list(ts)
        if bigrams:
            feats.extend(f"{a}::{b}" for a, b in zip(ts, ts[1:]))
        if not feats:
            return np.ones(self.dim, dtype=np.int8)
        acc = np.zeros(self.dim, np.int32)
        # Repeated terms carry weight, as they should in a simple HDC bag representation.
        for f in feats:
            acc += self.atom(f, space)
        return np.where(acc >= 0, 1, -1).astype(np.int8)


def lcs_len(a: list[str], b: list[str]) -> int:
    # O(len(a)*len(b)) memory-reduced LCS. Truncate only for pathological reference lengths.
    if len(a) > 2500:
        a = a[:2500]
    if len(b) > 2500:
        b = b[:2500]
    if len(b) > len(a):
        a, b = b, a
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[-1]))
        prev = cur
    return prev[-1]


def rouge_n_f1(pred: str, ref: str, n: int) -> float:
    pt, rt = tokens(pred), tokens(ref)
    if len(pt) < n or len(rt) < n:
        return 0.0
    pc = Counter(tuple(pt[i:i+n]) for i in range(len(pt)-n+1))
    rc = Counter(tuple(rt[i:i+n]) for i in range(len(rt)-n+1))
    overlap = sum((pc & rc).values())
    p = overlap / max(1, sum(pc.values()))
    r = overlap / max(1, sum(rc.values()))
    return 2*p*r/(p+r) if p+r else 0.0


def rouge_l_f1(pred: str, ref: str) -> float:
    pt, rt = tokens(pred), tokens(ref)
    if not pt or not rt:
        return 0.0
    l = lcs_len(pt, rt)
    p, r = l/len(pt), l/len(rt)
    return 2*p*r/(p+r) if p+r else 0.0


def ranges_to_set(spans: Iterable[Iterable[str]]) -> set[int]:
    out: set[int] = set()
    for span in spans:
        a, b = map(int, span)
        out.update(range(a, b + 1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--dim", type=int, default=4096)
    ap.add_argument("--budget", type=int, default=32)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args()

    hdc = TextHDC(args.dim)
    rows = []
    with args.jsonl.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
            if len(rows) >= args.limit:
                break

    tmp = Path(tempfile.mkdtemp(prefix="hng-qmsum-"))
    results = []
    try:
        with HDCDocumentMemory(tmp, hv_dim=args.dim, space_id="qmsum-token-hdc-v1", auto_index=False,
                               index_options={"table_count": 16, "bits_per_table": 12, "sketch_bits": 256}) as docs:
            for doc_id, row in enumerate(rows, 1):
                transcripts = row["meeting_transcripts"]
                units = [(f'{u.get("speaker", "")}: {u.get("content", "")}', 0) for u in transcripts]

                def enc(text: str, *, context):
                    # Different deterministic spaces give independently addressable views.
                    return DocumentUnitEncoding(heads={
                        "topic": hdc.encode(text, space="topic"),
                        "claim": hdc.encode(text, space="claim"),
                        "entity": hdc.encode(text, space="entity", bigrams=False),
                        "evidence": hdc.encode(text, space="evidence"),
                        "role": hdc.encode(text, space="role", bigrams=False),
                    })

                t0 = time.perf_counter()
                docs.ingest(doc_id, units, CallableDocumentAdapter(enc))
                ingest_ms = (time.perf_counter() - t0) * 1000
            docs.rebuild_index()

            for doc_id, row in enumerate(rows, 1):
                t0 = time.perf_counter()
                frame = docs.summarize_document(doc_id, budget_units=args.budget, discover_structure=True)
                synopsis_ms = (time.perf_counter() - t0) * 1000
                pred = " ".join(r.source for r in frame.selected_records)
                ref = row.get("general_query_list", [{}])[0].get("answer", "")

                q_hits = []
                for q in row.get("specific_query_list", []):
                    gold = ranges_to_set(q.get("relevant_text_span", []))
                    if not gold:
                        continue
                    qtext = q.get("query", "")
                    query = {
                        "topic": hdc.encode(qtext, space="topic"),
                        "entity": hdc.encode(qtext, space="entity", bigrams=False),
                    }
                    recall = docs.query_document_adaptive(doc_id, query, top_k=args.top_k)
                    # Experience extra ordinal is zero-based QMSum transcript index.
                    predicted = {int(h.record.extra.get("ordinal", -1)) for h in recall.hits}
                    q_hits.append(bool(predicted & gold))

                results.append({
                    "document_id": doc_id,
                    "units": len(row["meeting_transcripts"]),
                    "segments": len(frame.segments),
                    "selected": len(frame.selected_records),
                    "ingest_ms": ingest_ms,
                    "synopsis_ms": synopsis_ms,
                    "rouge1_f1": rouge_n_f1(pred, ref, 1),
                    "rouge2_f1": rouge_n_f1(pred, ref, 2),
                    "rougeL_f1": rouge_l_f1(pred, ref),
                    "specific_query_span_hit_at_k": sum(q_hits)/len(q_hits) if q_hits else math.nan,
                    "specific_queries": len(q_hits),
                })
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    def mean(field):
        vals = [float(r[field]) for r in results if not math.isnan(float(r[field]))]
        return sum(vals)/len(vals) if vals else math.nan

    summary = {
        "dataset": "QMSum test",
        "documents": len(results),
        "encoder": "deterministic non-neural bag-of-token HDC",
        "dim": args.dim,
        "budget": args.budget,
        "top_k": args.top_k,
        "mean_rouge1_f1": mean("rouge1_f1"),
        "mean_rouge2_f1": mean("rouge2_f1"),
        "mean_rougeL_f1": mean("rougeL_f1"),
        "mean_specific_query_span_hit_at_k": mean("specific_query_span_hit_at_k"),
        "per_document": results,
    }
    text = json.dumps(summary, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
