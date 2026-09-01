#!/usr/bin/env python3
"""Counterfactual HNG component ablations on the frozen Adversarial-250 suite."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "breakthrough_eval"
OUTPUT = EVAL / "ablation_matrix"
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts.fixed_candidate_governance import (  # noqa: E402
    PLAN,
    NOW,
    Scenario,
    decision_confidence,
    generate_scenarios,
    hng_decide,
    stable_hash,
)
from hngfrontier.aggregation import EvidenceAggregator  # noqa: E402
from hngfrontier.query_planner import QueryIntent, QueryPlanV2  # noqa: E402
from hngfrontier.semantic import EvidenceRequirement  # noqa: E402

SCHEMA_VERSION = 1
PROTOCOL_REVISION = 2
Transform = Callable[[Scenario], Scenario]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def no_temporal_validity(scenario: Scenario) -> Scenario:
    environment = str(scenario.query.fields["environment_version"].value)
    records = tuple(replace(
        item,
        validity=replace(item.validity, valid_until=None, environment_version=environment),
    ) for item in scenario.candidates)
    return replace(scenario, candidates=records)


def no_supersession(scenario: Scenario) -> Scenario:
    return replace(scenario, candidates=tuple(
        replace(item, superseded_by=None) for item in scenario.candidates
    ))


def no_evidence_independence(scenario: Scenario) -> Scenario:
    records = []
    for item in scenario.candidates:
        unique = f"{item.source_event_id}:{item.experience_id}"
        records.append(replace(item, source_event_id=unique, evidence_group_id=unique))
    return replace(scenario, candidates=tuple(records))


def no_provenance_or_trust(scenario: Scenario) -> Scenario:
    records = []
    for item in scenario.candidates:
        provenance = replace(
            item.provenance,
            source_type="system_telemetry",
            source_id=f"trusted-ablation:{item.experience_id}",
            trust_score=1.0,
            verified=True,
            verification_status="verified",
            identity="trusted-ablation",
        )
        records.append(replace(item, provenance=provenance))
    return replace(scenario, candidates=tuple(records))


def no_perspective(scenario: Scenario) -> Scenario:
    role = str(scenario.actor.value("role"))
    authority = int(scenario.actor.value("authority_level"))
    return replace(scenario, candidates=tuple(
        replace(
            item,
            tenant_id=scenario.actor.tenant_id,
            user_id=scenario.actor.user_id,
            role=role,
            authority_level=authority,
        )
        for item in scenario.candidates
    ))


def no_exact_semantic_floors(scenario: Scenario) -> Scenario:
    return replace(scenario, candidates=tuple(
        replace(item, semantics=scenario.query) for item in scenario.candidates
    ))


def no_outcome_memory(scenario: Scenario) -> Scenario:
    return replace(scenario, candidates=tuple(
        replace(item, outcome_score=0.0) for item in scenario.candidates
    ))


TRANSFORMS: dict[str, Transform] = {
    "minus_outcome_memory": no_outcome_memory,
    "minus_exact_semantic_floors": no_exact_semantic_floors,
    "minus_temporal_validity": no_temporal_validity,
    "minus_supersession": no_supersession,
    "minus_evidence_independence": no_evidence_independence,
    "minus_provenance_and_trust": no_provenance_or_trust,
    "minus_perspective": no_perspective,
}

NO_REQUIRED_STATE_PLAN = QueryPlanV2(
    QueryIntent.ACTION_EVALUATION,
    EvidenceRequirement((), min_similarity={}),
    critical=False,
)


def decide_with_plan(scenario: Scenario, plan: QueryPlanV2) -> dict[str, object]:
    assessment = EvidenceAggregator().assess(
        scenario.candidates,
        scenario.query,
        plan,
        profile=scenario.actor,
        now=NOW,
    )
    return {
        "decision": assessment.decision.value,
        "included": [item.record.experience_id for item in assessment.included],
        "excluded": [{"id": item.experience_id, "reason": item.reason} for item in assessment.excluded],
        "support_score": assessment.support_score,
        "challenge_score": assessment.challenge_score,
        "confidence": decision_confidence(assessment.support_score, assessment.challenge_score),
    }


def completed_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    result = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if (
                    row.get("event") == "ablation_decision"
                    and row.get("protocol_revision") == PROTOCOL_REVISION
                    and not row.get("error")
                ):
                    result.add((str(row["ablation"]), str(row["case_id"])))
    return result


def execute(scenarios: Sequence[Scenario], raw_path: Path) -> None:
    completed = completed_keys(raw_path)
    variants = ("full_hng", *TRANSFORMS, "minus_required_state_contracts")
    for scenario in scenarios:
        for variant in variants:
            if (variant, scenario.case_id) in completed:
                continue
            event: dict[str, object] = {
                "schema_version": SCHEMA_VERSION,
                "protocol_revision": PROTOCOL_REVISION,
                "event": "ablation_decision",
                "created_at": utc_now(),
                "ablation": variant,
                "case_id": scenario.case_id,
                "family": scenario.family,
                "split": scenario.split,
                "expected": scenario.expected,
                "candidate_ids": list(scenario.candidate_ids),
                "candidate_pool_sha256": scenario.candidate_pool_sha256,
            }
            try:
                if variant == "full_hng":
                    result = hng_decide(scenario)
                elif variant == "minus_required_state_contracts":
                    result = decide_with_plan(scenario, NO_REQUIRED_STATE_PLAN)
                else:
                    result = hng_decide(TRANSFORMS[variant](scenario))
                event.update(result)
                event["correct"] = result["decision"] == scenario.expected
            except Exception as exc:
                event["error"] = f"{type(exc).__name__}: {exc}"
            append_jsonl(raw_path, event)


def compile_results(scenarios: Sequence[Scenario], raw_path: Path) -> dict[str, object]:
    latest: dict[tuple[str, str], dict[str, object]] = {}
    failures = []
    with raw_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("protocol_revision") != PROTOCOL_REVISION:
                continue
            if row.get("error"):
                failures.append(row)
            else:
                latest[(str(row["ablation"]), str(row["case_id"]))] = row
    variants = ("full_hng", *TRANSFORMS, "minus_required_state_contracts")
    summaries: dict[str, object] = {}
    for variant in variants:
        rows = [row for (name, _case), row in latest.items() if name == variant]
        by_family = {}
        for family in sorted({scenario.family for scenario in scenarios}):
            typed = [row for row in rows if row["family"] == family]
            by_family[family] = {
                "count": len(typed),
                "correct": sum(bool(row["correct"]) for row in typed),
                "accuracy": sum(bool(row["correct"]) for row in typed) / len(typed) if typed else None,
            }
        summaries[variant] = {
            "count": len(rows),
            "correct": sum(bool(row["correct"]) for row in rows),
            "accuracy": sum(bool(row["correct"]) for row in rows) / len(rows) if rows else None,
            "decision_changes_from_full": None,
            "by_family": by_family,
        }
    full_rows = {
        case: row for (variant, case), row in latest.items() if variant == "full_hng"
    }
    full_accuracy = summaries["full_hng"]["accuracy"]
    for variant in variants[1:]:
        rows = {case: row for (name, case), row in latest.items() if name == variant}
        summaries[variant]["decision_changes_from_full"] = sum(
            rows[case]["decision"] != full_rows[case]["decision"]
            for case in rows.keys() & full_rows.keys()
        )
        accuracy = summaries[variant]["accuracy"]
        summaries[variant]["accuracy_delta_vs_full"] = (
            None if accuracy is None else round(accuracy - full_accuracy, 12)
        )

    executed_ranking = sorted(
        (
            {"ablation": name, "accuracy_delta_vs_full": payload["accuracy_delta_vs_full"]}
            for name, payload in summaries.items()
            if name != "full_hng"
        ),
        key=lambda item: item["accuracy_delta_vs_full"],
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "status": "complete" if all(summaries[name]["count"] == len(scenarios) for name in variants) else "partial",
        "protocol": "counterfactual component ablations on frozen Adversarial-250; synthetic",
        "protocol_revision": PROTOCOL_REVISION,
        "candidate_scenario_manifest_sha256": stable_hash([
            {"case_id": item.case_id, "candidate_pool_sha256": item.candidate_pool_sha256}
            for item in scenarios
        ]),
        "scenario_count": len(scenarios),
        "summaries": summaries,
        "executed_ranking_most_harmful_removal_first": executed_ranking,
        "not_isolated": {
            "deterministic_state_carry": "No multi-turn state-carry intervention exists in Adversarial-250.",
            "profile_uncertainty": "The frozen actor profiles have no varied uncertainty field.",
            "consolidation": "Measured separately in consolidation/RESULTS.json; raw+patterns does not change action behavior.",
            "belief_graph": "Measured separately in belief_revision/RESULTS.json; HNG ties the strong authority policy.",
        },
        "limitations": [
            "counterfactual record/plan transformations, not internal production feature flags",
            "synthetic governance decisions rather than public or real assistant behavior",
            "provenance and trust are jointly removed because the frozen policy couples them",
            "component interactions are not identified by one-at-a-time ablations",
        ],
        "failure_count": len(failures),
        "failures": failures,
        "raw_log": raw_path.relative_to(ROOT).as_posix(),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "RESULTS.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    scenarios = generate_scenarios()
    raw_path = OUTPUT / "raw" / "events.jsonl"
    execute(scenarios, raw_path)
    result = compile_results(scenarios, raw_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "complete" and result["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
