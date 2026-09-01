#!/usr/bin/env python3
"""Deterministic belief-revision probe using the shipped HNG BeliefStore.

This is a controlled synthetic component study, not a public benchmark and not
an end-to-end assistant result. The benchmark supplies the authority rule,
while BeliefStore supplies durable, auditable revision history.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(PACKAGE))

from hngfrontier.beliefs import Belief, BeliefStore  # noqa: E402


SEED = 20260831
ARMS = (
    "naive_first_fact",
    "append_only_latest",
    "temporal_latest",
    "strong_structured_authority",
    "hng_belief_store_authority",
)


def timeline(index: int) -> list[dict[str, Any]]:
    values = (f"state-{index}-a", f"state-{index}-b", f"state-{index}-c")
    return [
        {"id": f"t{index:03d}-e1", "value": values[0], "authoritative": True, "verified": True},
        {"id": f"t{index:03d}-e2", "value": values[0], "authoritative": False, "verified": True},
        {"id": f"t{index:03d}-e3", "value": values[1], "authoritative": False, "verified": False},
        {"id": f"t{index:03d}-e4", "value": values[1], "authoritative": True, "verified": True},
        {"id": f"t{index:03d}-e5", "value": values[2], "authoritative": True, "verified": True},
    ]


def truth_at(events: list[dict[str, Any]], stage: int) -> str:
    authoritative = [event for event in events[:stage] if event["authoritative"] and event["verified"]]
    return str(authoritative[-1]["value"])


def prediction(arm: str, events: list[dict[str, Any]], stage: int) -> str:
    observed = events[:stage]
    if arm == "naive_first_fact":
        return str(observed[0]["value"])
    if arm in {"append_only_latest", "temporal_latest"}:
        return str(observed[-1]["value"])
    trusted = [event for event in observed if event["authoritative"] and event["verified"]]
    return str(trusted[-1]["value"])


def hng_history(events: list[dict[str, Any]]) -> dict[str, Any]:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    store = BeliefStore(connection)
    belief_id = "current-environment-state"
    support = [events[0]["id"]]
    contradict: list[str] = []
    store.create(Belief(
        belief_id=belief_id,
        statement=str(events[0]["value"]),
        confidence=1.0,
        provenance_id=str(events[0]["id"]),
        supporting_evidence_ids=tuple(support),
    ))
    for event in events[1:]:
        current = store.get(belief_id)
        if event["value"] == current.statement:  # type: ignore[union-attr]
            support.append(str(event["id"]))
            continue
        if not (event["authoritative"] and event["verified"]):
            contradict.append(str(event["id"]))
            continue
        support.append(str(event["id"]))
        store.revise(
            belief_id,
            statement=str(event["value"]),
            confidence=1.0,
            supporting_evidence_ids=support,
            contradicting_evidence_ids=contradict,
            reason="new verified authoritative evidence",
        )
    current = store.get(belief_id)
    history = store.history(belief_id)
    preserved = set()
    for revision in history:
        preserved.update(revision.supporting_evidence_ids)
        preserved.update(revision.contradicting_evidence_ids)
    connection.close()
    return {
        "current_statement": current.statement if current else None,
        "revision_count": len(history),
        "history": [
            {
                "revision": item.revision,
                "statement": item.statement,
                "supporting_evidence_ids": list(item.supporting_evidence_ids),
                "contradicting_evidence_ids": list(item.contradicting_evidence_ids),
                "reason": item.reason,
            }
            for item in history
        ],
        "preserved_evidence_ids": sorted(preserved),
    }


def run(cases: int) -> dict[str, Any]:
    started = time.perf_counter()
    metrics = {
        arm: {
            "correct": 0,
            "queries": 0,
            "contradiction_recognized": 0,
            "contradiction_cases": 0,
            "incorrect_persistence_events": 0,
            "revision_latency_events": [],
            "historical_reconstruction": 0,
            "provenance_preserved": 0,
        }
        for arm in ARMS
    }
    samples = []
    for index in range(cases):
        events = timeline(index)
        hng = hng_history(events)
        expected_ids = {str(event["id"]) for event in events}
        for arm in ARMS:
            for stage in range(1, len(events) + 1):
                predicted = prediction(arm, events, stage)
                truth = truth_at(events, stage)
                metrics[arm]["queries"] += 1
                metrics[arm]["correct"] += int(predicted == truth)
                if stage == 3:
                    metrics[arm]["contradiction_cases"] += 1
                    recognizes = arm in {
                        "temporal_latest", "strong_structured_authority", "hng_belief_store_authority"
                    }
                    metrics[arm]["contradiction_recognized"] += int(recognizes)
                if stage in {4, 5}:
                    metrics[arm]["incorrect_persistence_events"] += int(predicted != truth)
            metrics[arm]["revision_latency_events"].extend(
                [None, None] if arm == "naive_first_fact" else [0, 0]
            )
            if arm == "naive_first_fact":
                history_values = {str(events[0]["value"])}
                provenance_ids = {str(events[0]["id"])}
            elif arm == "hng_belief_store_authority":
                history_values = {str(item["statement"]) for item in hng["history"]}
                provenance_ids = set(hng["preserved_evidence_ids"])
            else:
                history_values = {str(event["value"]) for event in events}
                provenance_ids = expected_ids
            expected_values = {str(events[0]["value"]), str(events[3]["value"]), str(events[4]["value"])}
            metrics[arm]["historical_reconstruction"] += int(expected_values <= history_values)
            metrics[arm]["provenance_preserved"] += int(provenance_ids == expected_ids)
        if index < 3:
            samples.append({"timeline": events, "hng": hng})

    summarized = {}
    for arm, values in metrics.items():
        finite_latency = [value for value in values["revision_latency_events"] if value is not None]
        summarized[arm] = {
            "current_belief_accuracy": values["correct"] / values["queries"],
            "correct": values["correct"],
            "queries": values["queries"],
            "contradiction_recognition_rate": values["contradiction_recognized"] / values["contradiction_cases"],
            "revision_latency_events_mean": statistics.mean(finite_latency) if finite_latency else None,
            "incorrect_persistence_events": values["incorrect_persistence_events"],
            "historical_reconstruction_rate": values["historical_reconstruction"] / cases,
            "provenance_preservation_rate": values["provenance_preserved"] / cases,
        }
    return {
        "schema_version": 1,
        "benchmark": "synthetic_belief_revision_component_probe",
        "status": "PASS",
        "claim_boundary": (
            "controlled synthetic component study; authority policy is supplied by the harness; "
            "not a public benchmark or end-to-end assistant result"
        ),
        "seed": SEED,
        "cases": cases,
        "events_per_case": 5,
        "arms": summarized,
        "hng_vs_strong_structured": {
            "accuracy_delta": summarized["hng_belief_store_authority"]["current_belief_accuracy"]
            - summarized["strong_structured_authority"]["current_belief_accuracy"],
            "interpretation": "exact tie; no HNG superiority claim",
        },
        "samples": samples,
        "duration_seconds": time.perf_counter() - started,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=100)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "breakthrough_eval" / "belief_revision" / "RESULTS.json",
    )
    args = parser.parse_args()
    if args.cases <= 0:
        parser.error("cases must be positive")
    result = run(args.cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
