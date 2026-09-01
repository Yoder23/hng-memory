#!/usr/bin/env python3
"""Audit whether preserved Strong/HNG reader arms can identify an HNG-specific effect."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "breakthrough_eval"
DEFAULT_OUTPUT = EVAL / "identifiability" / "RESULTS.json"

STUDIES = {
    "longmemeval_v2": EVAL / "public" / "longmemeval_v2" / "raw" / "events.jsonl",
    "locomo_plus": EVAL / "public" / "locomo_plus" / "raw" / "events.jsonl",
    "locomo_plus_n30": EVAL / "public" / "locomo_plus_n30" / "raw" / "events.jsonl",
    "locomo_retrieval_budget": EVAL / "public" / "locomo_retrieval_budget_holdout" / "raw" / "events.jsonl",
    "locomo_hybrid": EVAL / "public" / "locomo_hybrid_holdout" / "raw" / "events.jsonl",
    "locomo_reranker": EVAL / "public" / "locomo_reranker_holdout" / "raw" / "events.jsonl",
    "personamem_v2": EVAL / "public" / "personamem_v2" / "raw" / "events.jsonl",
    "fixed_candidate_deterministic": EVAL / "fixed_candidate" / "raw" / "deterministic_events.jsonl",
    "fixed_candidate_qwen": EVAL / "fixed_candidate" / "raw" / "llm_events.jsonl",
    "fixed_candidate_mistral": EVAL / "fixed_candidate_cross_family" / "raw" / "llm_events.jsonl",
    "cross_reader_qwen": EVAL / "fixed_candidate_cross_reader_holdout" / "readers" / "qwen" / "raw" / "llm_events.jsonl",
    "cross_reader_mistral": EVAL / "fixed_candidate_cross_reader_holdout" / "readers" / "mistral" / "raw" / "llm_events.jsonl",
}

PUBLIC_STUDIES = {
    "longmemeval_v2",
    "locomo_plus",
    "locomo_plus_n30",
    "locomo_retrieval_budget",
    "locomo_hybrid",
    "locomo_reranker",
    "personamem_v2",
}


def read_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            rows.append(value)
    return rows


def arm_of(row: Mapping[str, Any]) -> str | None:
    value = row.get("arm", row.get("system"))
    return str(value) if value is not None else None


def unit_of(row: Mapping[str, Any]) -> str:
    for key in ("sample_id", "question_id", "case_id", "source_index"):
        if key in row:
            return f"{key}:{row[key]}"
    raise ValueError("row has no supported paired-unit identifier")


def unique_arm(arms: Iterable[str], token: str) -> str | None:
    matches = sorted(arm for arm in set(arms) if token in arm.lower())
    return matches[0] if len(matches) == 1 else None


def compare_value(left: Mapping[str, Any], right: Mapping[str, Any], key: str) -> str:
    if key not in left or key not in right:
        return "unavailable"
    return "equal" if left[key] == right[key] else "different"


def display_path(path: Path) -> str:
    try:
        return path.relative_to(EVAL).as_posix()
    except ValueError:
        return path.as_posix()


def audit_study(name: str, path: Path) -> dict[str, Any]:
    rows = read_rows(path)
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    arms: list[str] = []
    for row in rows:
        arm = arm_of(row)
        if arm is None or row.get("status") == "failed":
            continue
        arms.append(arm)
        latest[(unit_of(row), arm)] = row

    strong = unique_arm(arms, "strong")
    hng = unique_arm(arms, "hng")
    base: dict[str, Any] = {
        "path": display_path(path),
        "evidence_class": "public_noncanonical" if name in PUBLIC_STUDIES else "synthetic",
        "observed_arms": sorted(set(arms)),
        "strong_arm": strong,
        "hng_arm": hng,
    }
    if strong is None or hng is None:
        return {**base, "status": "NO_UNIQUE_STRONG_HNG_PAIR", "paired_units": 0}

    units = sorted({unit for unit, arm in latest if arm == strong} & {unit for unit, arm in latest if arm == hng})
    keys = (
        "candidate_pool_sha256",
        "selected_candidate_ids",
        "memory_context_sha256",
        "prompt_sha256",
        "prediction",
        "decision",
        "observed",
        "judge_score",
        "included_ids",
        "support_score",
        "challenge_score",
        "correct",
    )
    counts = {key: Counter() for key in keys}
    hng_reused = 0
    for unit in units:
        left, right = latest[(unit, strong)], latest[(unit, hng)]
        for key in keys:
            counts[key][compare_value(left, right, key)] += 1
        hng_reused += int(bool(right.get("evaluation_reused")))

    comparisons = {key: dict(sorted(counter.items())) for key, counter in counts.items()}
    prompt_available = counts["prompt_sha256"]["equal"] + counts["prompt_sha256"]["different"]
    context_available = counts["memory_context_sha256"]["equal"] + counts["memory_context_sha256"]["different"]
    distinguishing = counts["prompt_sha256"]["different"] or counts["memory_context_sha256"]["different"]
    policy_decision_distinguishing = counts["decision"]["different"] + counts["observed"]["different"]
    policy_score_distinguishing = counts["support_score"]["different"] + counts["challenge_score"]["different"]
    exact_prompt_reuse = bool(units) and prompt_available == len(units) and counts["prompt_sha256"]["equal"] == len(units)
    return {
        **base,
        "status": "PAIRED",
        "paired_units": len(units),
        "comparisons": comparisons,
        "hng_evaluation_reused_count": hng_reused,
        "reader_input_distinguishing_units": distinguishing,
        "policy_decision_distinguishing_units": policy_decision_distinguishing,
        "policy_score_distinguishing_values": policy_score_distinguishing,
        "exact_prompt_reuse_for_all_pairs": exact_prompt_reuse,
        "hng_effect_identifiable_from_reader_outputs": bool(distinguishing),
        "hash_coverage": {
            "prompt_pairs": prompt_available,
            "memory_context_pairs": context_available,
        },
    }


def build_report(studies: Mapping[str, Path] = STUDIES) -> dict[str, Any]:
    audited = {name: audit_study(name, path) for name, path in studies.items() if path.exists()}
    public_paired = [value for name, value in audited.items() if name in PUBLIC_STUDIES and value["status"] == "PAIRED"]
    public_identifiable = [value for value in public_paired if value["hng_effect_identifiable_from_reader_outputs"]]
    public_exact_reuse = [value for value in public_paired if value["exact_prompt_reuse_for_all_pairs"]]
    deterministic = audited.get("fixed_candidate_deterministic", {})
    return {
        "schema_version": 1,
        "status": "COMPLETE",
        "studies": audited,
        "summary": {
            "study_count": len(audited),
            "paired_study_count": sum(value["status"] == "PAIRED" for value in audited.values()),
            "public_paired_study_count": len(public_paired),
            "public_reader_input_identifiable_study_count": len(public_identifiable),
            "public_exact_prompt_reuse_study_count": len(public_exact_reuse),
            "deterministic_policy_paired_unit_count": deterministic.get("paired_units", 0),
            "deterministic_policy_decision_difference_count": deterministic.get("policy_decision_distinguishing_units", 0),
            "deterministic_policy_score_difference_count": deterministic.get("policy_score_distinguishing_values", 0),
        },
        "conclusion": (
            "An HNG-versus-Strong score tie cannot be treated as independent downstream evidence when both arms reuse the exact reader prompt. "
            "Synthetic fixed-candidate studies render distinct contexts, but their observed ties still do not establish HNG-specific superiority."
        ),
        "claim_boundary": "This audit measures experimental identifiability from preserved hashes and logs; it does not rescore benchmark answers or create new behavioral evidence.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
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
