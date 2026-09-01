#!/usr/bin/env python3
"""Development-only search for genuine production-HNG versus Strong policy contrasts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "breakthrough_eval" / "policy_differential" / "DEVELOPMENT_RESULTS.json"
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts.fixed_candidate_governance import (  # noqa: E402
    TRUST_SOURCE,
    EvidenceKind,
    Scenario,
    hng_decide,
    make_record,
    profile,
    stable_hash,
    strong_structured_decide,
    structured_state,
)


def safe_token(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-")


def generate_cases() -> list[tuple[Scenario, dict[str, Any]]]:
    cases: list[tuple[Scenario, dict[str, Any]]] = []
    for kind in EvidenceKind:
        for source_type in sorted(TRUST_SOURCE):
            for verified in (False, True):
                for outcome in (-1, 1):
                    for independent_count in (1, 2):
                        case_id = "-".join((
                            "policy-dev",
                            safe_token(kind.value),
                            safe_token(source_type),
                            "verified" if verified else "unverified",
                            "support" if outcome > 0 else "challenge",
                            f"n{independent_count}",
                        ))
                        records = []
                        for index in range(independent_count):
                            record = make_record(
                                case_id,
                                index,
                                outcome=outcome,
                                event=f"{case_id}-source-{index}",
                                state="service-development",
                                goal="restore-development",
                                sequence="step-development",
                                action="action-development",
                                environment="v-development",
                                source_type=source_type,
                                trust=1.0,
                                verified=verified,
                            )
                            records.append(replace(record, kind=kind))
                        scenario = Scenario(
                            case_id=case_id,
                            family="policy_differential_development",
                            split="development",
                            query=structured_state(
                                "service-development",
                                "restore-development",
                                "step-development",
                                "action-development",
                                "v-development",
                            ),
                            actor=profile(),
                            candidates=tuple(records),
                            expected="UNLABELED_DEVELOPMENT",
                        )
                        cases.append((scenario, {
                            "kind": kind.value,
                            "source_type": source_type,
                            "verified": verified,
                            "outcome": outcome,
                            "independent_count": independent_count,
                        }))
    return cases


def build_report() -> dict[str, Any]:
    cases = generate_cases()
    rows = []
    decision_pairs: Counter[str] = Counter()
    decision_differences: Counter[str] = Counter()
    by_kind: defaultdict[str, int] = defaultdict(int)
    by_source: defaultdict[str, int] = defaultdict(int)
    for scenario, inputs in cases:
        strong = strong_structured_decide(scenario)
        hng = hng_decide(scenario)
        decision_different = strong["decision"] != hng["decision"]
        score_different = (
            strong["support_score"] != hng["support_score"]
            or strong["challenge_score"] != hng["challenge_score"]
        )
        included_set_different = set(strong["included"]) != set(hng["included"])
        decisive = {"support", "challenge", "conflicted"}
        strong_decisive_hng_nondecisive = strong["decision"] in decisive and hng["decision"] not in decisive
        hng_decisive_strong_nondecisive = hng["decision"] in decisive and strong["decision"] not in decisive
        pair = f"{strong['decision']}->{hng['decision']}"
        decision_pairs[pair] += 1
        if decision_different:
            decision_differences[pair] += 1
            by_kind[str(inputs["kind"])] += 1
            by_source[str(inputs["source_type"])] += 1
        rows.append({
            "case_id": scenario.case_id,
            "candidate_pool_sha256": scenario.candidate_pool_sha256,
            "inputs": inputs,
            "strong": {
                "decision": strong["decision"],
                "support_score": strong["support_score"],
                "challenge_score": strong["challenge_score"],
                "included_count": len(strong["included"]),
            },
            "hng": {
                "decision": hng["decision"],
                "support_score": hng["support_score"],
                "challenge_score": hng["challenge_score"],
                "included_count": len(hng["included"]),
            },
            "decision_different": decision_different,
            "score_different": score_different,
            "included_set_different": included_set_different,
            "strong_decisive_hng_nondecisive": strong_decisive_hng_nondecisive,
            "hng_decisive_strong_nondecisive": hng_decisive_strong_nondecisive,
        })
    definitions = [row["inputs"] for row in rows]
    return {
        "schema_version": 1,
        "status": "DEVELOPMENT_ONLY_COMPLETE",
        "case_definition_sha256": stable_hash(definitions),
        "summary": {
            "case_count": len(rows),
            "decision_difference_count": sum(row["decision_different"] for row in rows),
            "score_difference_count": sum(row["score_different"] for row in rows),
            "included_set_difference_count": sum(row["included_set_different"] for row in rows),
            "strong_decisive_hng_nondecisive_count": sum(row["strong_decisive_hng_nondecisive"] for row in rows),
            "hng_decisive_strong_nondecisive_count": sum(row["hng_decisive_strong_nondecisive"] for row in rows),
            "decision_pairs": dict(sorted(decision_pairs.items())),
            "decision_differences": dict(sorted(decision_differences.items())),
            "decision_differences_by_kind": dict(sorted(by_kind.items())),
            "decision_differences_by_source": dict(sorted(by_source.items())),
        },
        "cases": rows,
        "claim_boundary": (
            "This is an exhaustive bounded development grid over evidence kind, source type, verification, stance, and one/two independent groups. "
            "Cases have no outcome labels and are not holdout, public, LLM, or superiority evidence."
        ),
        "admission_rule": (
            "A future reader holdout requires defensible labels and disjoint case construction frozen before inference; unlabeled divergences alone are insufficient."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
