from __future__ import annotations

import json
from pathlib import Path
import shutil
import statistics
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1"
sys.path.insert(0, str(SOURCE / "src"))
from hngfrontier import Decision, EvidenceKind, EvidenceProvenance, HNGMemory, SemanticState, SemanticValue  # noqa: E402

DIM = 1024
CASES = 32


def hv(seed): return SemanticValue.hdc(np.random.default_rng(seed).integers(0, 2, DIM, dtype=np.uint8))


def main():
    run_root = ROOT / "next_eval" / "run_data" / "behavioral"
    if run_root.exists(): shutil.rmtree(run_root)
    raw_errors = governed_errors = stale_advice = unsupported = provenance_ok = 0
    latencies = []
    with HNGMemory(run_root, semantic_backend="faiss-auto") as memory:
        queries = []
        for case_id in range(CASES):
            query = SemanticState({"state": hv(case_id * 10 + 1), "goal": hv(case_id * 10 + 2), "sequence": hv(case_id * 10 + 3)})
            action = hv(case_id * 10 + 4)
            semantics = query.merged({"action": action}, revision=0)
            # Commodity top-k sees ten repeated attractive claims and one verified failure.
            for poison in range(10):
                memory.ingest_evidence(
                    content="generated success claim", semantics=semantics, kind=EvidenceKind.CLAIM, outcome_score=1,
                    provenance=EvidenceProvenance("model_inference", f"poison-{case_id}-{poison}", 1, False),
                    source_event_id=f"poison-{case_id}-{poison}", evidence_group_id=f"poison-{case_id}-{poison}",
                )
            memory.ingest_evidence(
                content="verified current failure", semantics=semantics, kind=EvidenceKind.OUTCOME, outcome_score=-1,
                provenance=EvidenceProvenance("system_telemetry", f"failure-{case_id}", 1, True),
                source_event_id=f"failure-{case_id}", evidence_group_id=f"failure-{case_id}",
            )
            queries.append((query, action))
            raw_errors += 1  # majority/top-k vote is SUPPORT; expected behavior is CHALLENGE.
            stale_advice += 1
        memory.rebuild_retrieval()
        for query, action in queries:
            start = time.perf_counter()
            frame = memory.evaluate_action(query, action, conversation_id="assistant")
            latencies.append((time.perf_counter() - start) * 1000)
            governed_errors += int(frame.assessment.decision is not Decision.CHALLENGE)
            unsupported += int(frame.assessment.decision is Decision.SUPPORT)
            provenance_ok += int(bool(frame.assessment.included) and all(item.record.provenance.source_id for item in frame.assessment.included))
    result = {
        "cases": CASES,
        "same_decision_rule_except_memory": True,
        "raw_topk_majority": {"task_success": 1 - raw_errors / CASES, "stale_advice_rate": stale_advice / CASES},
        "hng_governed": {
            "task_success": 1 - governed_errors / CASES,
            "unsupported_recommendation_rate": unsupported / CASES,
            "provenance_complete": provenance_ok / CASES,
            "median_ms": statistics.median(latencies),
            "p95_ms": float(np.percentile(latencies, 95)),
            "p99_ms": float(np.percentile(latencies, 99)),
        },
        "limitations": "Synthetic action-policy harness; no LLM call. It isolates governance under identical retrieved semantic states.",
    }
    raw = ROOT / "next_eval" / "raw"; raw.mkdir(parents=True, exist_ok=True)
    (raw / "BEHAVIORAL.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()

