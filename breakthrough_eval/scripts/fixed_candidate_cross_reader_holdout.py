#!/usr/bin/env python3
"""Prepare the disjoint two-reader fixed-candidate holdout."""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts import fixed_candidate_governance as fixed  # noqa: E402

DEFAULT_OUTPUT = ROOT / "breakthrough_eval" / "fixed_candidate_cross_reader_holdout"
PRIOR_PREPARED = ROOT / "breakthrough_eval" / "fixed_candidate_cross_family" / "PREPARED.json"
PROTOCOL = "fixed_candidate_disjoint_cross_reader_holdout"
FIXED_CASES = 30
SYSTEMS = ("ordinary_rag", "strong_structured", "hng")
READERS = {
    "qwen": {
        "model": "qwen3.8:27b-q4_K_M",
        "digest": "25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e",
        "family": "qwen3",
    },
    "mistral": {
        "model": "mistral-small3.1:24b-instruct-2503-q4_K_M",
        "digest": "b9aaf0c2586a8ed8105feab808c0f034bd4d346203822f048e2366165a13f4ea",
        "family": "mistral3",
    },
}
PERMUTATIONS = tuple(itertools.permutations(SYSTEMS))


def selected_scenarios() -> list[fixed.Scenario]:
    prior = json.loads(PRIOR_PREPARED.read_text(encoding="utf-8"))
    excluded = {row["case_id"] for row in prior["cases"]}
    selected = [
        scenario for scenario in fixed.generate_scenarios()
        if scenario.split == "holdout" and scenario.case_id not in excluded
    ][:FIXED_CASES]
    if len(selected) != FIXED_CASES or excluded & {item.case_id for item in selected}:
        raise RuntimeError("disjoint cross-reader case selection invariant failed")
    return selected


def counterbalanced_orders(
    scenarios: list[fixed.Scenario], reader: str
) -> dict[str, tuple[str, ...]]:
    ranked = sorted(
        scenarios,
        key=lambda scenario: fixed.stable_hash({
            "protocol": PROTOCOL,
            "reader": reader,
            "seed": fixed.SEED,
            "case_id": scenario.case_id,
        }),
    )
    return {
        scenario.case_id: PERMUTATIONS[index % len(PERMUTATIONS)]
        for index, scenario in enumerate(ranked)
    }


def prepared_payload() -> dict[str, Any]:
    scenarios = selected_scenarios()
    orders = {reader: counterbalanced_orders(scenarios, reader) for reader in READERS}
    rows = []
    for scenario in scenarios:
        decisions = {
            "ordinary_rag": fixed.raw_majority_decide(scenario),
            "strong_structured": fixed.strong_structured_decide(scenario),
            "hng": fixed.hng_decide(scenario),
        }
        contexts = {
            system: fixed.context_for(system, scenario, decisions[system])
            for system in SYSTEMS
        }
        rows.append({
            "case_id": scenario.case_id,
            "family": scenario.family,
            "split": scenario.split,
            "candidate_ids": list(scenario.candidate_ids),
            "candidate_pool_sha256": scenario.candidate_pool_sha256,
            "expected_sha256": fixed.stable_hash(scenario.expected),
            "memory_context_sha256": {
                system: fixed.stable_hash(contexts[system]) for system in SYSTEMS
            },
            "system_order": {
                reader: list(orders[reader][scenario.case_id]) for reader in READERS
            },
        })
    order_balance = {
        reader: {
            "|".join(order): count
            for order, count in sorted(Counter(orders[reader].values()).items())
        }
        for reader in READERS
    }
    return {
        "schema_version": fixed.SCHEMA_VERSION,
        "status": "PREPARED_NO_INFERENCE",
        "protocol": PROTOCOL,
        "seed": fixed.SEED,
        "selection": "first 30 generated holdout cases after excluding the prior cross-family PREPARED case IDs",
        "prior_prepared_sha256": __import__("hashlib").sha256(PRIOR_PREPARED.read_bytes()).hexdigest(),
        "sample_count": len(rows),
        "systems": list(SYSTEMS),
        "readers": READERS,
        "expected_events": len(rows) * len(SYSTEMS) * len(READERS),
        "order_balance": order_balance,
        "cases": rows,
    }


def prepare(output: Path) -> dict[str, Any]:
    payload = prepared_payload()
    path = output / "PREPARED.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if fixed.stable_hash(existing) != fixed.stable_hash(payload):
            raise RuntimeError("prepared disjoint cross-reader holdout changed")
        return existing
    output.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if not args.prepare_only:
        raise RuntimeError("execution is not enabled until the disjoint protocol is fully frozen")
    payload = prepare(args.output)
    print(json.dumps({
        "status": payload["status"],
        "samples": payload["sample_count"],
        "expected_events": payload["expected_events"],
        "order_balance": payload["order_balance"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
