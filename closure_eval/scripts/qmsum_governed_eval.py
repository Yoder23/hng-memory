"""Official QMSum retrieval evaluation through HNGMemory's final document path."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1"
sys.path[:0] = [str(ROOT / "research_eval" / "vendor"), str(SOURCE / "src"), str(SOURCE / "benchmarks")]

import numpy as np
from hngfrontier import (DocumentChunk, EvidenceProvenance, FaissBinaryRetriever,
                         HNGMemory, HybridDocumentRetriever, QueryIntent,
                         SemanticState, SemanticValue)
from qmsum_public_hdc import TextHDC, ranges_to_set


def summary(values: list[float]) -> dict[str, float]:
    return {"median_ms": statistics.median(values), "p95_ms": float(np.percentile(values, 95)),
            "p99_ms": float(np.percentile(values, 99)), "stdev_ms": statistics.pstdev(values)}


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("jsonl", type=Path)
    ap.add_argument("--limit", type=int, default=20); ap.add_argument("--dim", type=int, default=4096)
    ap.add_argument("--top-k", type=int, default=5); ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(); rows = []
    with args.jsonl.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip(): rows.append(json.loads(line))
            if len(rows) >= args.limit: break
    encoder = TextHDC(args.dim); root = Path(tempfile.mkdtemp(prefix="hng-qmsum-governed-"))
    hits = {"bm25": [], "hybrid_document": [], "governed_memory": []}
    latency = {key: [] for key in hits}; exclusions = 0; verified = 0; queries = 0; units = 0
    try:
        for document_number, row in enumerate(rows, 1):
            semantic_provider = FaissBinaryRetriever(mode="faiss-flat", exact_fallback=False)
            documents = HybridDocumentRetriever(semantic_provider)
            with HNGMemory(root / str(document_number), semantic_backend="faiss-flat",
                           allow_reference_fallback=False, document_retriever=documents) as memory:
                conversation = f"qmsum-{document_number}"
                for ordinal, unit in enumerate(row["meeting_transcripts"]):
                    text = f'{unit.get("speaker", "")}: {unit.get("content", "")}'
                    topic = SemanticValue.hdc(encoder.encode(text, space="topic"), dimension=args.dim,
                                              model="qmsum-token-hdc-v1")
                    chunk = DocumentChunk(f"{document_number}:{ordinal}", str(document_number), text,
                                          f"qmsum://test/{document_number}#{ordinal}", topic,
                                          {"ordinal": ordinal, "split": "test"})
                    memory.ingest_document_chunk(chunk, semantics=SemanticState({"topic": topic}),
                        provenance=EvidenceProvenance("external_document", "Yale-LILY/QMSum", .9, True),
                        conversation_id=conversation)
                    units += 1
                documents.rebuild(); memory.rebuild_retrieval()
                for item in row.get("specific_query_list", []):
                    gold = ranges_to_set(item.get("relevant_text_span", []))
                    if not gold: continue
                    queries += 1; query = item.get("query", "")
                    semantic = SemanticValue.hdc(encoder.encode(query, space="topic"), dimension=args.dim,
                                                 model="qmsum-token-hdc-v1")
                    start = time.perf_counter()
                    lexical = documents.search(query, top_k=args.top_k)
                    latency["bm25"].append((time.perf_counter() - start) * 1000)
                    hits["bm25"].append(bool({int(x.chunk.metadata["ordinal"]) for x in lexical} & gold))
                    start = time.perf_counter()
                    hybrid = memory.search_documents(query, semantic=semantic, top_k=args.top_k)
                    latency["hybrid_document"].append((time.perf_counter() - start) * 1000)
                    hits["hybrid_document"].append(bool({int(x.chunk.metadata["ordinal"]) for x in hybrid} & gold))
                    start = time.perf_counter()
                    frame = memory.context(conversation, query=SemanticState({"topic": semantic}),
                                           intent=QueryIntent.DOCUMENT_EVIDENCE, lexical_query=query)
                    latency["governed_memory"].append((time.perf_counter() - start) * 1000)
                    ranked = [trace.experience_id for trace in frame.assessment.original_candidates[:args.top_k]]
                    predicted = {int(value.rsplit(":", 1)[1]) for value in ranked if value.startswith("chunk:")}
                    hits["governed_memory"].append(bool(predicted & gold))
                    exclusions += len(frame.assessment.excluded)
                    verified += sum(x.record.provenance.verification_status == "verified"
                                    for x in frame.assessment.included)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    methods = {name: {"queries": len(values), "span_hit_at_5": float(np.mean(values)),
                      **summary(latency[name])} for name, values in hits.items()}
    payload = {"dataset": "official QMSum test split", "dataset_repository": "Yale-LILY/QMSum",
               "documents": len(rows), "transcript_units": units, "specific_queries": queries,
               "encoder": "deterministic non-neural bag-of-token HDC", "dim": args.dim,
               "top_k": args.top_k, "methods": methods, "governance": {"excluded_candidates": exclusions,
               "verified_included_evidence": verified}, "limitations": [
                   "This evaluates retrieval of annotated relevant spans, not generated-summary quality.",
                   "The deterministic encoder is a reproducible integration probe, not a learned production encoder."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8"); print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
