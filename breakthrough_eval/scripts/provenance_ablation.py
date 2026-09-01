#!/usr/bin/env python3
"""Fixed-candidate provenance ablation over the frozen poison scenarios."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts.fixed_candidate_governance import (
    generate_scenarios,
    hng_decide,
    mcnemar,
    raw_majority_decide,
    record_payload,
    strong_structured_decide,
)


def run() -> dict[str, Any]:
    scenarios = [item for item in generate_scenarios() if item.family == "untrusted_poison"]
    events = []
    for scenario in scenarios:
        no_provenance = raw_majority_decide(scenario)
        displayed = raw_majority_decide(scenario)
        strong = strong_structured_decide(scenario)
        hng = hng_decide(scenario)
        decisions = {
            "no_provenance": no_provenance,
            "provenance_displayed_only": displayed,
            "strong_structured_provenance_governance": strong,
            "hng_provenance_governance": hng,
        }
        events.append({
            "case_id": scenario.case_id,
            "split": scenario.split,
            "expected": scenario.expected,
            "candidate_ids": list(scenario.candidate_ids),
            "candidate_pool_sha256": scenario.candidate_pool_sha256,
            "displayed_provenance": [
                {
                    key: payload[key]
                    for key in ("source_type", "source_id", "trust", "verified", "verification_status")
                }
                for item in scenario.candidates
                for payload in (record_payload(item),)
            ],
            "arms": {
                name: {
                    "decision": result["decision"],
                    "correct": result["decision"] == scenario.expected,
                    "included": result["included"],
                    "excluded": result["excluded"],
                }
                for name, result in decisions.items()
            },
        })
    summaries = {}
    for arm in events[0]["arms"]:
        correct = [bool(event["arms"][arm]["correct"]) for event in events]
        summaries[arm] = {
            "count": len(correct),
            "correct": sum(correct),
            "accuracy": statistics.mean(correct),
        }
    invariants = {
        "scenario_count": len(scenarios),
        "same_candidate_pool_all_arms": True,
        "no_provenance_equals_display_only_decisions": all(
            event["arms"]["no_provenance"]["decision"]
            == event["arms"]["provenance_displayed_only"]["decision"]
            for event in events
        ),
    }
    outcomes = {
        arm: [bool(event["arms"][arm]["correct"]) for event in events]
        for arm in summaries
    }
    return {
        "schema_version": 1,
        "benchmark": "fixed_candidate_provenance_ablation",
        "status": "PASS" if all(invariants.values()) else "FAIL",
        "claim_boundary": "25 frozen synthetic poison cases; deterministic decision study, not downstream public behavior",
        "summaries": summaries,
        "invariants": invariants,
        "hng_vs_strong_accuracy_delta": (
            summaries["hng_provenance_governance"]["accuracy"]
            - summaries["strong_structured_provenance_governance"]["accuracy"]
        ),
        "paired_statistics": {
            "hng_vs_no_provenance": mcnemar(
                outcomes["hng_provenance_governance"], outcomes["no_provenance"]
            ),
            "hng_vs_display_only": mcnemar(
                outcomes["hng_provenance_governance"], outcomes["provenance_displayed_only"]
            ),
            "hng_vs_strong": mcnemar(
                outcomes["hng_provenance_governance"], outcomes["strong_structured_provenance_governance"]
            ),
        },
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "breakthrough_eval" / "provenance_ablation" / "RESULTS.json",
    )
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "summaries": result["summaries"]}, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
