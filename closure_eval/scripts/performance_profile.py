"""Repeated end-to-end profile of retrieval, governance, storage, and rendering."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "research_eval" / "vendor"),
                str(ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src")]

import numpy as np
from hngfrontier import EvidenceProvenance, HNGMemory, QueryIntent, SemanticState, SemanticValue


def value(row, dim):
    return SemanticValue.hdc(row, dimension=dim, model="profile-v1")


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--records", type=int, default=1000)
    ap.add_argument("--queries", type=int, default=300); ap.add_argument("--dim", type=int, default=2048)
    ap.add_argument("--output", type=Path, required=True); args = ap.parse_args()
    rng = np.random.default_rng(20260831); rows = rng.choice([-1, 1], size=(args.records, args.dim)).astype(np.int8)
    root = Path(tempfile.mkdtemp(prefix="hng-performance-profile-"))
    try:
        with HNGMemory(root, semantic_backend="faiss-flat", allow_reference_fallback=False) as memory:
            provenance = EvidenceProvenance("system_telemetry", "profile-harness", 1, True)
            for i, row in enumerate(rows):
                memory.ingest_evidence(content=f"profile record {i}", semantics=SemanticState({"topic": value(row, args.dim)}),
                                       provenance=provenance, outcome_score=1 if i % 2 == 0 else -1,
                                       experience_id=f"record:{i}", source_event_id=f"event:{i}")
            memory.rebuild_retrieval()
            for i in range(args.queries):
                query = SemanticState({"topic": value(rows[i % args.records], args.dim)})
                frame = memory.context("profile", query=query, intent=QueryIntent.DOCUMENT_EVIDENCE,
                                       lexical_query=f"profile record {i % args.records}")
                with memory.profiler.measure("frame_rendering"):
                    frame.to_prompt_context(max_tokens=1200)
            payload = {"config": vars(args), "components": memory.profiler.summary(),
                       "provider": memory.stats()["providers"]}
    finally:
        shutil.rmtree(root, ignore_errors=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
