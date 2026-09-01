#!/usr/bin/env python3
"""Reversible consolidation probe over the shipped production components."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(PACKAGE))

from hngfrontier import (  # noqa: E402
    EvidenceKind,
    EvidenceProvenance,
    HNGMemory,
    SemanticState,
    SemanticValue,
)


def hv(seed: int) -> SemanticValue:
    return SemanticValue.hdc(np.random.default_rng(seed).integers(0, 2, 256, dtype=np.uint8))


STATE = SemanticState({"state": hv(1), "goal": hv(2), "sequence": hv(3)})
ACTION = hv(4)


def frame_payload(frame: Any) -> dict[str, Any]:
    assessment = frame.assessment
    return {
        "decision": assessment.decision.value,
        "support_score": assessment.support_score,
        "challenge_score": assessment.challenge_score,
        "independent_support_count": assessment.independent_support_count,
        "independent_challenge_count": assessment.independent_challenge_count,
    }


def run(groups: int = 12, events_per_group: int = 5, copies_per_event: int = 4) -> dict[str, Any]:
    if min(groups, events_per_group, copies_per_event) <= 0:
        raise ValueError("all shape parameters must be positive")
    with tempfile.TemporaryDirectory(prefix="hng-consolidation-") as directory:
        memory = HNGMemory(Path(directory), semantic_backend="reference-hng")
        try:
            rare_event = f"group-000:event-{events_per_group - 1:03d}"
            for group in range(groups):
                for event in range(events_per_group):
                    source_event = f"group-{group:03d}:event-{event:03d}"
                    outcome = -1.0 if source_event == rare_event else 1.0
                    for copy in range(copies_per_event):
                        experience = f"{source_event}:copy-{copy:03d}"
                        memory.ingest_evidence(
                            content=f"consolidation event {source_event}",
                            semantics=STATE.merged({"action": ACTION}),
                            provenance=EvidenceProvenance("system_telemetry", source_event, 1.0, True),
                            kind=EvidenceKind.OUTCOME,
                            outcome_score=outcome,
                            confidence=1.0,
                            experience_id=experience,
                            source_event_id=source_event,
                            evidence_group_id=f"group-{group:03d}",
                        )
            raw_records = memory.store.all()
            raw_count = len(raw_records)
            raw_logical_bytes = len(json.dumps([
                {
                    "id": item.experience_id,
                    "group": item.evidence_group_id,
                    "event": item.source_event_id,
                    "outcome": item.outcome_score,
                    "content": item.content,
                    "source": item.provenance.as_dict(),
                }
                for item in raw_records
            ], sort_keys=True).encode("utf-8"))
            before = frame_payload(memory.evaluate_action(STATE, ACTION, conversation_id="consolidation"))
            pattern_ids = memory.consolidate()
            patterns = [memory.consolidation.pattern(pattern_id) for pattern_id in pattern_ids]
            after = frame_payload(memory.evaluate_action(STATE, ACTION, conversation_id="consolidation"))
            after_count = len(memory.store.all())
            pattern_logical_bytes = len(json.dumps(patterns, sort_keys=True).encode("utf-8"))
            rare_pattern = memory.consolidation.pattern("pattern:group-000")
            rare_preserved = bool(
                rare_pattern
                and rare_event in rare_pattern["independent_source_event_ids"]
                and rare_pattern["challenge_count"] == 1
            )
            duplicate_resistance = all(
                pattern is not None
                and len(pattern["independent_source_event_ids"]) == events_per_group
                and len(pattern["source_experience_ids"]) == events_per_group * copies_per_event
                for pattern in patterns
            )
            reversible = all(
                pattern is not None
                and pattern["reversible"] is True
                and all(memory.store.get(identifier) is not None for identifier in pattern["source_experience_ids"])
                for pattern in patterns
            )
            memory.consolidation.invalidate_pattern("pattern:group-000")
            invalidation_reversible = (
                memory.consolidation.pattern("pattern:group-000") is None
                and len(memory.store.all()) == raw_count
                and memory.store.get(f"{rare_event}:copy-000") is not None
            )
        finally:
            memory.close()
    expected_raw = groups * events_per_group * copies_per_event
    passed = all((
        raw_count == expected_raw,
        after_count == raw_count,
        len(pattern_ids) == groups,
        before == after,
        rare_preserved,
        duplicate_resistance,
        reversible,
        invalidation_reversible,
    ))
    return {
        "schema_version": 1,
        "benchmark": "synthetic_reversible_consolidation_probe",
        "status": "PASS" if passed else "FAIL",
        "claim_boundary": "synthetic production-component probe; patterns-only has no action-evaluation consumer in this release",
        "config": {
            "groups": groups,
            "independent_events_per_group": events_per_group,
            "copies_per_event": copies_per_event,
        },
        "raw_records": raw_count,
        "patterns": len(pattern_ids),
        "raw_logical_bytes": raw_logical_bytes,
        "pattern_logical_bytes": pattern_logical_bytes,
        "logical_size_ratio_patterns_to_raw": pattern_logical_bytes / raw_logical_bytes,
        "raw_only": before,
        "raw_plus_consolidation": after,
        "patterns_only": {
            "status": "NOT_EXECUTABLE",
            "reason": "Persisted consolidated patterns are not indexed as governed evidence or consumed by evaluate_action.",
        },
        "action_quality_changed": before != after,
        "raw_evidence_deleted": after_count != raw_count,
        "rare_event_preserved": rare_preserved,
        "duplicate_resistance_passed": duplicate_resistance,
        "provenance_reversible": reversible,
        "pattern_invalidation_preserves_raw": invalidation_reversible,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", type=int, default=12)
    parser.add_argument("--events-per-group", type=int, default=5)
    parser.add_argument("--copies-per-event", type=int, default=4)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "breakthrough_eval" / "consolidation" / "RESULTS.json",
    )
    args = parser.parse_args()
    result = run(args.groups, args.events_per_group, args.copies_per_event)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
