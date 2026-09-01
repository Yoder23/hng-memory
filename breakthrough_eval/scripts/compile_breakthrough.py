"""Compile breakthrough evidence into machine-readable results and scoreboard artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "breakthrough_eval"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def row(
    area: str,
    system: str,
    metric: str,
    value: float | None,
    unit: str,
    evidence_class: str,
    status: str,
    source: str,
    notes: str = "",
) -> dict[str, object]:
    return {
        "area": area,
        "system": system,
        "metric": metric,
        "value": value,
        "unit": unit,
        "evidence_class": evidence_class,
        "status": status,
        "source": source,
        "notes": notes,
    }


def fmt(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "fraction":
        return f"{value * 100:.1f}%"
    if unit == "milliseconds":
        return f"{value:.3f} ms"
    if unit == "seconds":
        return f"{value:.3f} s"
    if unit == "count":
        return str(int(value))
    return f"{value:.4g}"


def main() -> int:
    baseline = load(EVAL / "baseline_070" / "BASELINE_STATUS.json")
    baseline_environment = load(EVAL / "baseline_070" / "ENVIRONMENT.json")
    resource_inventory = load(EVAL / "RESOURCE_INVENTORY.json")
    public_resources = load(EVAL / "PUBLIC_RESOURCES.json")
    deterministic = load(EVAL / "fixed_candidate" / "DETERMINISTIC_RESULTS.json")
    llm = load(EVAL / "fixed_candidate" / "LLM_RESULTS.json")
    longmem_path = EVAL / "public" / "longmemeval_v2" / "RESULTS.json"
    longmem = load(longmem_path) if longmem_path.exists() else None
    expanded_locomo_path = EVAL / "public" / "locomo_plus_n30" / "RESULTS.json"
    locomo_path = (
        expanded_locomo_path
        if expanded_locomo_path.exists()
        else EVAL / "public" / "locomo_plus" / "RESULTS.json"
    )
    locomo = load(locomo_path) if locomo_path.exists() else None
    budget_path = EVAL / "public" / "locomo_retrieval_budget_holdout" / "RESULTS.json"
    budget = load(budget_path) if budget_path.exists() else None
    hybrid_path = EVAL / "public" / "locomo_hybrid_holdout" / "RESULTS.json"
    hybrid = load(hybrid_path) if hybrid_path.exists() else None
    personamem_path = EVAL / "public" / "personamem_v2" / "RESULTS.json"
    personamem = load(personamem_path) if personamem_path.exists() else None
    reliability_path = EVAL / "reliability" / "STORAGE_PROBE.json"
    reliability = load(reliability_path) if reliability_path.exists() else None
    multitenant_path = EVAL / "reliability" / "MULTITENANT_100K_1K.json"
    multitenant = load(multitenant_path) if multitenant_path.exists() else None
    isolation_path = EVAL / "reliability" / "MULTI_USER_100K_ISOLATION.json"
    isolation = load(isolation_path) if isolation_path.exists() else None
    belief_path = EVAL / "belief_revision" / "RESULTS.json"
    belief = load(belief_path) if belief_path.exists() else None
    provenance_path = EVAL / "provenance_ablation" / "RESULTS.json"
    provenance = load(provenance_path) if provenance_path.exists() else None
    action_path = EVAL / "action_experience" / "RESULTS.json"
    action = load(action_path) if action_path.exists() else None
    consolidation_path = EVAL / "consolidation" / "RESULTS.json"
    consolidation = load(consolidation_path) if consolidation_path.exists() else None
    ablation_path = EVAL / "ablation_matrix" / "RESULTS.json"
    ablation = load(ablation_path) if ablation_path.exists() else None
    tool_before_path = EVAL / "tool_agent" / "BEFORE_RESULTS.json"
    tool_before = load(tool_before_path) if tool_before_path.exists() else None
    tool_after_path = EVAL / "tool_agent" / "RESULTS.json"
    tool_after = load(tool_after_path) if tool_after_path.exists() else None
    release_path = EVAL / "releases" / "0.7.0rc2" / "RELEASE_MANIFEST.json"
    release = load(release_path) if release_path.exists() else None
    real_hdc_path = EVAL / "real_hdc" / "READINESS.json"
    real_hdc = load(real_hdc_path) if real_hdc_path.exists() else None
    latency_path = EVAL / "latency" / "RESULTS.json"
    latency = load(latency_path) if latency_path.exists() else None
    results: list[dict[str, object]] = []

    for name, payload in deterministic["systems"].items():
        results.append(row(
            "fixed_candidate_deterministic",
            name,
            "decision_accuracy",
            float(payload["accuracy"]),
            "fraction",
            "synthetic",
            "EXECUTED",
            "fixed_candidate/DETERMINISTIC_RESULTS.json",
            "Same ordered candidate pool and metadata; policy decision, not downstream behavior.",
        ))
        for quantile in ("p50", "p95", "p99"):
            results.append(row(
                "fixed_candidate_deterministic",
                name,
                f"governance_latency_{quantile}",
                float(payload["latency_ms"][quantile]),
                "milliseconds",
                "local_synthetic",
                "EXECUTED",
                "fixed_candidate/DETERMINISTIC_RESULTS.json",
            ))

    for name, payload in llm["systems"].items():
        results.append(row(
            "fixed_candidate_llm_holdout",
            name,
            "answer_accuracy",
            None if payload["accuracy"] is None else float(payload["accuracy"]),
            "fraction",
            "synthetic",
            "EXECUTED",
            "fixed_candidate/LLM_RESULTS.json",
            f"Frozen {llm['model']} digest {llm['model_digest']}; {payload['total']} paired holdout cases.",
        ))
        results.append(row(
            "fixed_candidate_llm_holdout",
            name,
            "prompt_tokens_total",
            float(payload["prompt_tokens_total"]),
            "count",
            "synthetic",
            "EXECUTED",
            "fixed_candidate/LLM_RESULTS.json",
        ))
        for quantile in ("p50", "p95", "p99"):
            results.append(row(
                "fixed_candidate_llm_holdout",
                name,
                f"end_to_end_latency_{quantile}",
                float(payload["latency_seconds"][quantile]),
                "seconds",
                "local_synthetic",
                "EXECUTED",
                "fixed_candidate/LLM_RESULTS.json",
            ))

    if longmem is not None:
        for name, payload in longmem["summaries"].items():
            results.append(row(
                "longmemeval_v2_text_pilot",
                name,
                "answer_accuracy",
                None if payload["accuracy"] is None else float(payload["accuracy"]),
                "fraction",
                "public_noncanonical",
                "EXECUTED" if longmem["status"] == "complete" else "PARTIAL",
                "public/longmemeval_v2/RESULTS.json",
                "Official public data; stratified text-only pilot with local reader/judge, not a leaderboard score.",
            ))

    if locomo is not None:
        locomo_source = locomo_path.relative_to(EVAL).as_posix()
        locomo_area = f"locomo_plus_stratified_n{locomo['sample_count']}"
        for name, payload in locomo["summaries"].items():
            results.append(row(
                locomo_area,
                name,
                "judge_score_average",
                None if payload["average"] is None else float(payload["average"]),
                "fraction",
                "public_noncanonical",
                "EXECUTED" if locomo["status"] == "complete" else "PARTIAL",
                locomo_source,
                f"Official public data/templates; {locomo['sample_count']}-sample local reader/judge evaluation, not a leaderboard score.",
            ))
            results.append(row(
                locomo_area,
                name,
                "prompt_tokens_total",
                float(payload["prompt_tokens"]),
                "count",
                "public_noncanonical",
                "EXECUTED" if locomo["status"] == "complete" else "PARTIAL",
                locomo_source,
            ))

    if budget is not None:
        for name, payload in budget["summaries"].items():
            for metric, value, unit in (
                ("judge_score_average", payload["average"], "fraction"),
                ("prompt_tokens_total", payload["prompt_tokens"], "count"),
                ("mean_selected_context_chars", payload["mean_selected_context_chars"], "count"),
            ):
                results.append(row(
                    "locomo_plus_disjoint_retrieval_budget_n30",
                    name,
                    metric,
                    None if value is None else float(value),
                    unit,
                    "public_noncanonical",
                    "EXECUTED" if budget["status"] == "complete" else "PARTIAL",
                    "public/locomo_retrieval_budget_holdout/RESULTS.json",
                    "Preregistered disjoint holdout; retrieval budgets change candidates and do not isolate governance except at fixed k64.",
                ))

    if hybrid is not None:
        for name, payload in hybrid["summaries"].items():
            for metric, value, unit in (
                ("judge_score_average", payload["average"], "fraction"),
                ("prompt_tokens_total", payload["prompt_tokens"], "count"),
                ("mean_selected_context_chars", payload["mean_selected_context_chars"], "count"),
            ):
                results.append(row(
                    "locomo_plus_disjoint_dense_hybrid_n30",
                    name,
                    metric,
                    None if value is None else float(value),
                    unit,
                    "public_noncanonical",
                    "EXECUTED" if hybrid["status"] == "complete" else "PARTIAL",
                    "public/locomo_hybrid_holdout/RESULTS.json",
                    "Preregistered disjoint holdout; genuine Qwen3 dense retrieval and BM25/dense reciprocal-rank fusion. HNG and Strong reuse the exact hybrid context/output.",
                ))

    if personamem is not None:
        for name, payload in personamem["summaries"].items():
            results.extend([
                row(
                    "personamem_v2_seven_stratum_pilot",
                    name,
                    "mcq_accuracy",
                    payload["accuracy"],
                    "fraction",
                    "public_noncanonical",
                    "EXECUTED" if personamem["status"] == "complete" else "PARTIAL",
                    "public/personamem_v2/RESULTS.json",
                    "Seven-row local pilot; not comparable to official benchmark scores.",
                ),
                row(
                    "personamem_v2_seven_stratum_pilot",
                    name,
                    "prompt_tokens_total",
                    float(payload["prompt_tokens"]),
                    "count",
                    "public_noncanonical",
                    "EXECUTED" if personamem["status"] == "complete" else "PARTIAL",
                    "public/personamem_v2/RESULTS.json",
                ),
            ])

    if reliability is not None:
        results.extend([
            row(
                "bounded_storage_reliability",
                "sqlite_evidence_store",
                "records_preserved_after_backup",
                float(reliability["ledger"]["after_count"]),
                "count",
                "local",
                reliability["status"],
                "reliability/STORAGE_PROBE.json",
                reliability["claim_boundary"],
            ),
            row(
                "bounded_storage_reliability",
                "sqlite_evidence_store",
                "append_latency_p95",
                float(reliability["append_latency_ms"]["p95"]),
                "milliseconds",
                "local",
                reliability["status"],
                "reliability/STORAGE_PROBE.json",
                reliability["claim_boundary"],
            ),
        ])

    if multitenant is not None:
        results.extend([
            row(
                "bounded_multitenant_storage",
                "sqlite_evidence_store",
                "records_preserved_after_backup",
                float(multitenant["ledger"]["after_count"]),
                "count",
                "local",
                multitenant["status"],
                "reliability/MULTITENANT_100K_1K.json",
                "1,000 tenants with 100 records each; not a 100,000-user concurrency test or soak.",
            ),
            row(
                "bounded_multitenant_storage",
                "sqlite_evidence_store",
                "append_latency_p95",
                float(multitenant["append_latency_ms"]["p95"]),
                "milliseconds",
                "local",
                multitenant["status"],
                "reliability/MULTITENANT_100K_1K.json",
                multitenant["claim_boundary"],
            ),
            row(
                "bounded_multitenant_storage",
                "sqlite_evidence_store",
                "tenant_isolation",
                1.0 if multitenant["tenant_isolation_passed"] else 0.0,
                "fraction",
                "local",
                multitenant["status"],
                "reliability/MULTITENANT_100K_1K.json",
                "Exact per-tenant eligible-ID counts; no concurrent user workload was exercised.",
            ),
        ])

    if isolation is not None:
        exhaustive = isolation["exhaustive_scoped_queries"]
        actor = isolation["actor_policy"]
        results.extend([
            row(
                "scaled_multi_user_isolation",
                "sqlite_scoped_query_actor_policy",
                "synthetic_user_principals",
                float(isolation["config"]["synthetic_user_principals"]),
                "count",
                "local",
                isolation["status"],
                "reliability/MULTI_USER_100K_ISOLATION.json",
                isolation["claim_boundary"],
            ),
            row(
                "scaled_multi_user_isolation",
                "sqlite_scoped_query_actor_policy",
                "scoped_cross_tenant_leakage_rate",
                float(exhaustive["cross_tenant_leaks"]) / float(exhaustive["checks"]),
                "fraction",
                "local",
                isolation["status"],
                "reliability/MULTI_USER_100K_ISOLATION.json",
                isolation["claim_boundary"],
            ),
            row(
                "scaled_multi_user_isolation",
                "sqlite_scoped_query_actor_policy",
                "scoped_cross_user_leakage_rate",
                float(exhaustive["cross_user_leaks"]) / float(exhaustive["checks"]),
                "fraction",
                "local",
                isolation["status"],
                "reliability/MULTI_USER_100K_ISOLATION.json",
                isolation["claim_boundary"],
            ),
            row(
                "scaled_multi_user_isolation",
                "actor_policy",
                "role_authority_leakage_rate",
                float(actor["role_leaks"] + actor["authority_leaks"]) / float(actor["checks"] * 2),
                "fraction",
                "local",
                isolation["status"],
                "reliability/MULTI_USER_100K_ISOLATION.json",
                "Role and authority eligibility only; not an identity-provider test.",
            ),
            row(
                "scaled_multi_user_isolation",
                "sqlite_scoped_query",
                "authorized_query_latency_p95",
                float(exhaustive["query_latency_ms"]["p95"]),
                "milliseconds",
                "local",
                isolation["status"],
                "reliability/MULTI_USER_100K_ISOLATION.json",
                isolation["claim_boundary"],
            ),
            row(
                "scaled_multi_user_isolation",
                "sqlite_evidence_store",
                "concurrent_writes_completed",
                float(isolation["concurrent_global_writes"]["completed"]),
                "count",
                "local",
                isolation["status"],
                "reliability/MULTI_USER_100K_ISOLATION.json",
                "Bounded overlap with concurrent scoped readers; not an hours-long load test.",
            ),
        ])

    for phase, tool_result, source in (
        ("before_context_fix", tool_before, "tool_agent/BEFORE_RESULTS.json"),
        ("after_context_fix", tool_after, "tool_agent/RESULTS.json"),
    ):
        if tool_result is None:
            continue
        for name, summary in tool_result["summaries"].items():
            for metric, unit in (
                ("task_success_rate", "fraction"),
                ("repeated_tool_failures", "count"),
                ("irreversible_mistakes", "count"),
            ):
                results.append(row(
                    f"synthetic_tool_agent_{phase}",
                    name,
                    metric,
                    float(summary[metric]),
                    unit,
                    "synthetic",
                    "EXECUTED",
                    source,
                    tool_result["claim_boundary"],
                ))
            results.append(row(
                f"synthetic_tool_agent_{phase}",
                name,
                "decision_latency_p95",
                float(summary["decision_latency_ms"]["p95"]),
                "milliseconds",
                "synthetic",
                "EXECUTED",
                source,
                tool_result["claim_boundary"],
            ))

    if latency is not None:
        for arm, payload in latency["arms"].items():
            for statistic, interval in payload["across_repeat_bootstrap_95_ci_ms"].items():
                results.append(row(
                    "repeated_tool_agent_latency",
                    arm,
                    f"decision_latency_{statistic}_across_run_mean",
                    float(interval["mean"]),
                    "milliseconds",
                    "local_synthetic",
                    "EXECUTED",
                    "latency/RESULTS.json",
                    f"95% bootstrap CI [{interval['ci95_low']:.6f}, {interval['ci95_high']:.6f}] ms over {latency['repeat_count']} independent-store runs.",
                ))

    if release is not None:
        for metric in (
            "wheel_install_no_deps",
            "versioned_outcome_smoke",
            "sdist_contains_changelog",
            "sdist_contains_migration_guide",
        ):
            results.append(row(
                "release_070rc2",
                "hng_frontier_package",
                metric,
                1.0 if release["checks"][metric] else 0.0,
                "fraction",
                "local",
                release["status"],
                "releases/0.7.0rc2/RELEASE_MANIFEST.json",
                "Local release qualification; not a package-index publication.",
            ))

    if belief is not None:
        for name, payload in belief["arms"].items():
            results.append(row(
                "synthetic_belief_revision",
                name,
                "current_belief_accuracy",
                float(payload["current_belief_accuracy"]),
                "fraction",
                "synthetic",
                belief["status"],
                "belief_revision/RESULTS.json",
                belief["claim_boundary"],
            ))

    if provenance is not None:
        for name, payload in provenance["summaries"].items():
            results.append(row(
                "synthetic_provenance_ablation", name, "decision_accuracy",
                float(payload["accuracy"]), "fraction", "synthetic", provenance["status"],
                "provenance_ablation/RESULTS.json", provenance["claim_boundary"],
            ))

    if action is not None:
        for name, payload in action["summaries"].items():
            results.extend([
                row(
                    "synthetic_action_experience", name, "action_success_rate",
                    float(payload["action_success_rate"]), "fraction", "synthetic", action["status"],
                    "action_experience/RESULTS.json", action["claim_boundary"],
                ),
                row(
                    "synthetic_action_experience", name, "action_regret",
                    float(payload["action_regret"]), "count", "synthetic", action["status"],
                    "action_experience/RESULTS.json", "Failures relative to the deterministic oracle action.",
                ),
            ])

    if consolidation is not None:
        results.extend([
            row(
                "synthetic_consolidation", "raw_plus_consolidation", "logical_size_ratio",
                float(consolidation["logical_size_ratio_patterns_to_raw"]), "ratio", "synthetic",
                consolidation["status"], "consolidation/RESULTS.json", consolidation["claim_boundary"],
            ),
            row(
                "synthetic_consolidation", "raw_plus_consolidation", "action_quality_changed",
                1.0 if consolidation["action_quality_changed"] else 0.0, "fraction", "synthetic",
                consolidation["status"], "consolidation/RESULTS.json",
                "Patterns are persisted but not consumed by evaluate_action.",
            ),
        ])

    if ablation is not None:
        for name, payload in ablation["summaries"].items():
            results.append(row(
                "synthetic_hng_component_ablation",
                name,
                "decision_accuracy",
                float(payload["accuracy"]),
                "fraction",
                "synthetic",
                ablation["status"],
                "ablation_matrix/RESULTS.json",
                "One-at-a-time counterfactual transformation; not a production feature flag or public task.",
            ))

    baseline_rows = (
        ("release_pytest", "passed", 94.0, "count"),
        ("expanded_adversarial", "passed", 64.0, "count"),
        ("canonical_adversarial", "passed", 11.0, "count"),
        ("fault_concurrency", "passed", 10.0, "count"),
    )
    for area, metric, value, unit in baseline_rows:
        results.append(row(
            area,
            "hng_0.7.0rc1",
            metric,
            value,
            unit,
            "local",
            "EXECUTED",
            "baseline_070/BASELINE_STATUS.json",
            f"Exact frozen commit {baseline.get('baseline_commit', 'unknown')}.",
        ))

    hdc_reason = "Production HDC interpreter/checkpoint and real traces absent."
    hdc_source = "RESOURCE_INVENTORY.json"
    if real_hdc is not None:
        codes = [item["code"] for item in real_hdc.get("failures", [])]
        hdc_reason = (
            f"Fail-closed readiness gate reports {real_hdc['failure_count']} unmet checks: "
            + ", ".join(codes)
            + "."
        )
        hdc_source = "real_hdc/READINESS.json"
    blocked = {"real_hdc_task_success": hdc_reason}
    for area, reason in blocked.items():
        results.append(row(
            area,
            "hng",
            "primary_metric",
            None,
            "fraction",
            "real" if area.startswith("real_hdc") else "public",
            "BLOCKED_EXTERNAL",
            hdc_source if area == "real_hdc_task_success" else "RESOURCE_INVENTORY.json",
            reason,
        ))

    pending = {}
    if locomo is None:
        pending["locomo_plus"] = "Official data and six-category candidate pools are prepared; reader/judge execution is not complete."
    if longmem is None:
        pending["longmemeval_v2"] = "Official small text tier is validated; the noncanonical local pilot is in progress."
    if personamem is None:
        pending["personamem_v2"] = "Official 5,000-row text benchmark and all 1,998 32K histories are pinned; seven-stratum pilot is prepared or running."
    for area, reason in pending.items():
        results.append(row(
            area,
            "hng",
            "primary_metric",
            None,
            "fraction",
            "public",
            "IN_PROGRESS",
            "PUBLIC_RESOURCES.json",
            reason,
        ))

    det_hng = deterministic["systems"]["hng"]
    det_strong = deterministic["systems"]["strong_structured"]
    llm_hng = llm["systems"]["hng"]
    llm_raw = llm["systems"]["ordinary_rag"]
    llm_strong = llm["systems"]["strong_structured"]
    p_raw = llm["paired_statistics"]["hng_vs_ordinary_rag"]["mcnemar"]["exact_two_sided_p"]
    p_strong = llm["paired_statistics"]["hng_vs_strong_structured"]["mcnemar"]["exact_two_sided_p"]
    ci_raw = llm["paired_statistics"]["hng_vs_ordinary_rag"]["paired_bootstrap_accuracy"]

    public_scoreboard_rows: list[dict[str, object]] = []
    if longmem is not None:
        public_hng = longmem["summaries"]["hng"]["accuracy"]
        public_strong = longmem["summaries"]["strong_structured"]["accuracy"]
        public_scoreboard_rows.append({
            "area": "LongMemEval-V2 text pilot",
            "hng": public_hng,
            "baseline": public_strong,
            "delta": None if public_hng is None or public_strong is None else public_hng - public_strong,
            "significance": None,
            "evidence_class": "public_noncanonical",
            "status": "EXECUTED_NONCANONICAL" if longmem["status"] == "complete" else "PARTIAL",
            "notes": "Official data, local text-only reader/judge pilot; not comparable to leaderboard scores.",
        })
    else:
        public_scoreboard_rows.append({
            "area": "LongMemEval-V2 text pilot",
            "hng": None,
            "baseline": None,
            "delta": None,
            "significance": None,
            "evidence_class": "public_noncanonical",
            "status": "IN_PROGRESS",
            "notes": "Official small text tier validated; local pilot is running.",
        })
    if locomo is not None:
        locomo_hng = locomo["summaries"]["hng"]["average"]
        locomo_strong = locomo["summaries"]["strong_structured"]["average"]
        locomo_pair = locomo.get("paired_statistics", {}).get("hng_vs_strong_structured")
        locomo_significance = None
        if locomo_pair is not None:
            locomo_significance = {
                "test": "McNemar exact; official judge score > 0.5",
                "p": locomo_pair["mcnemar_judge_positive"]["exact_two_sided_p"],
                "paired_cases": locomo_pair["paired_cases"],
                "mean_score_ci95": [
                    locomo_pair["paired_bootstrap_mean_score"]["ci95_low"],
                    locomo_pair["paired_bootstrap_mean_score"]["ci95_high"],
                ],
            }
        public_scoreboard_rows.append({
            "area": f"LoCoMo-Plus stratified n={locomo['sample_count']}",
            "hng": locomo_hng,
            "baseline": locomo_strong,
            "delta": None if locomo_hng is None or locomo_strong is None else locomo_hng - locomo_strong,
            "significance": locomo_significance,
            "evidence_class": "public_noncanonical",
            "status": "EXECUTED_NONCANONICAL" if locomo["status"] == "complete" else "PARTIAL",
            "notes": f"Official data/templates, {locomo['sample_count']}-sample local reader/judge evaluation; not comparable to leaderboard scores.",
        })
    else:
        public_scoreboard_rows.append({
            "area": "LoCoMo-Plus",
            "hng": None,
            "baseline": None,
            "delta": None,
            "significance": None,
            "evidence_class": "public",
            "status": "IN_PROGRESS",
            "notes": pending["locomo_plus"],
        })
    if budget is not None:
        primary = budget["paired_statistics"]["bm25_k64_vs_bm25_k16_primary"]
        public_scoreboard_rows.append({
            "area": "LoCoMo-Plus disjoint retrieval budget n=30",
            "hng": budget["summaries"]["bm25_k64"]["average"],
            "baseline": budget["summaries"]["bm25_k16"]["average"],
            "delta": primary["paired_bootstrap_mean_score"]["delta"],
            "significance": {
                "test": "McNemar exact; official judge score > 0.5",
                "p": primary["mcnemar_judge_positive"]["exact_two_sided_p"],
                "paired_cases": primary["paired_cases"],
                "mean_score_ci95": [
                    primary["paired_bootstrap_mean_score"]["ci95_low"],
                    primary["paired_bootstrap_mean_score"]["ci95_high"],
                ],
            },
            "evidence_class": "public_noncanonical",
            "status": "EXECUTED_NONCANONICAL" if budget["status"] == "complete" else "PARTIAL",
            "notes": "Primary retrieval comparison: BM25 k64 versus k16. HNG, Strong, and BM25 are exact ties at fixed k64.",
        })
    if hybrid is not None:
        primary = hybrid["paired_statistics"]["hybrid_k64_vs_bm25_k64_primary"]
        public_scoreboard_rows.append({
            "area": "LoCoMo-Plus disjoint dense/hybrid retrieval n=30",
            "hng": hybrid["summaries"]["hng_hybrid_k64"]["average"],
            "baseline": hybrid["summaries"]["bm25_k64"]["average"],
            "delta": primary["paired_bootstrap_mean_score"]["delta"],
            "significance": {
                "test": "McNemar exact; official judge score > 0.5",
                "p": primary["mcnemar_judge_positive"]["exact_two_sided_p"],
                "paired_cases": primary["paired_cases"],
                "mean_score_ci95": [
                    primary["paired_bootstrap_mean_score"]["ci95_low"],
                    primary["paired_bootstrap_mean_score"]["ci95_high"],
                ],
            },
            "evidence_class": "public_noncanonical",
            "status": "EXECUTED_NONCANONICAL" if hybrid["status"] == "complete" else "PARTIAL",
            "notes": "Primary retrieval comparison: BM25/dense RRF hybrid versus BM25 at k64. Dense alone scores higher descriptively; HNG, Strong, and plain hybrid are exact ties.",
        })
    if personamem is not None:
        pm_hng = personamem["summaries"]["hng"]["accuracy"]
        pm_strong = personamem["summaries"]["strong_structured"]["accuracy"]
        public_scoreboard_rows.append({
            "area": "PersonaMem-v2 seven-stratum pilot",
            "hng": pm_hng,
            "baseline": pm_strong,
            "delta": None if pm_hng is None or pm_strong is None else pm_hng - pm_strong,
            "significance": None,
            "evidence_class": "public_noncanonical",
            "status": "EXECUTED_NONCANONICAL" if personamem["status"] == "complete" else "PARTIAL",
            "notes": "Official data, seven-row local MCQ pilot; dense and agentic baselines absent.",
        })
    else:
        public_scoreboard_rows.append({
            "area": "PersonaMem-v2",
            "hng": None,
            "baseline": None,
            "delta": None,
            "significance": None,
            "evidence_class": "public_noncanonical",
            "status": "IN_PROGRESS",
            "notes": pending["personamem_v2"],
        })

    scoreboard = {
        "schema_version": 1,
        "release_baseline_commit": baseline.get("baseline_commit"),
        "rows": [
            {
                "area": "Real HDC task success",
                "hng": None,
                "baseline": None,
                "delta": None,
                "significance": None,
                "evidence_class": "real",
                "status": "BLOCKED_EXTERNAL",
                "notes": blocked["real_hdc_task_success"],
            },
            {
                "area": "Fixed-candidate deterministic governance",
                "hng": det_hng["accuracy"],
                "baseline": det_strong["accuracy"],
                "delta": det_hng["accuracy"] - det_strong["accuracy"],
                "significance": {"test": "McNemar exact", "p": 1.0},
                "evidence_class": "synthetic",
                "status": "LOSS_TIE",
                "notes": "HNG ties the simpler baseline and loses on complexity/latency; 25 frozen duplicate-boundary misses.",
            },
            {
                "area": "Fixed-LLM governance vs ordinary candidates",
                "hng": llm_hng["accuracy"],
                "baseline": llm_raw["accuracy"],
                "delta": llm_hng["accuracy"] - llm_raw["accuracy"],
                "significance": {
                    "test": "McNemar exact plus paired bootstrap",
                    "p": p_raw,
                    "ci95": [ci_raw["ci95_low"], ci_raw["ci95_high"]],
                },
                "evidence_class": "synthetic",
                "status": "WIN_SYNTHETIC",
                "notes": "30 untouched holdout cases, fixed 27B model and candidate pools; not a public or real result.",
            },
            {
                "area": "Fixed-LLM HNG vs StrongStructuredBaseline",
                "hng": llm_hng["accuracy"],
                "baseline": llm_strong["accuracy"],
                "delta": llm_hng["accuracy"] - llm_strong["accuracy"],
                "significance": {"test": "McNemar exact", "p": p_strong},
                "evidence_class": "synthetic",
                "status": "LOSS_TIE",
                "notes": "No HNG-specific behavioral advantage; StrongStructuredBaseline uses fewer prompt tokens.",
            },
            *([] if reliability is None else [{
                "area": "Bounded storage reliability",
                "hng": 1.0 if reliability["status"] == "PASS" else 0.0,
                "baseline": None,
                "delta": None,
                "significance": None,
                "evidence_class": "local",
                "status": reliability["status"],
                "notes": (
                    f"{reliability['ledger']['after_count']} records; backup ledger identical; "
                    f"p95 append {reliability['append_latency_ms']['p95']:.3f} ms. "
                    + reliability["claim_boundary"]
                ),
            }]),
            *([] if multitenant is None else [{
                "area": "Bounded 100K-record / 1K-tenant storage",
                "hng": 1.0 if multitenant["status"] == "PASS" else 0.0,
                "baseline": None,
                "delta": None,
                "significance": None,
                "evidence_class": "local",
                "status": multitenant["status"],
                "notes": (
                    f"{multitenant['ledger']['after_count']} records; exact 100-per-tenant counts; "
                    f"backup ledger identical; p95 append {multitenant['append_latency_ms']['p95']:.3f} ms. "
                    "Not a 100K-user or concurrent load test."
                ),
            }]),
            *([] if isolation is None else [{
                "area": "100K-principal scoped isolation",
                "hng": 1.0 if isolation["scoped_zero_leakage"] else 0.0,
                "baseline": None,
                "delta": None,
                "significance": None,
                "evidence_class": "local",
                "status": isolation["status"],
                "notes": (
                    f"{isolation['config']['synthetic_user_principals']} tenant/user principals; "
                    f"{isolation['exhaustive_scoped_queries']['checks']} exhaustive scoped checks; "
                    f"{isolation['concurrent_read_queries']['checks']} concurrent read checks and "
                    f"{isolation['concurrent_global_writes']['completed']} writes; zero scoped or actor-policy leakage. "
                    "Raw get/get_many remain privileged and unscoped; external authentication was not tested."
                ),
            }]),
            *([] if tool_after is None else [{
                "area": "Synthetic tool-agent advisory",
                "hng": tool_after["summaries"]["hng_advisory"]["task_success_rate"],
                "baseline": tool_after["summaries"]["strong_structured_memory"]["task_success_rate"],
                "delta": (
                    tool_after["summaries"]["hng_advisory"]["task_success_rate"]
                    - tool_after["summaries"]["strong_structured_memory"]["task_success_rate"]
                ),
                "significance": {
                    "test": "McNemar exact",
                    "p": tool_after["paired_statistics"]["hng_vs_strong"]["mcnemar"]["exact_two_sided_p"],
                },
                "evidence_class": "synthetic",
                "status": "LOSS_TIE",
                "notes": (
                    "Context forwarding fixes the preserved 29.6% pre-change HNG loss: HNG reaches "
                    "63.9%, eliminates 18 irreversible mistakes, and ties StrongStructuredBaseline "
                    "exactly, but remains slower and establishes no HNG-specific advantage."
                ),
            }]),
            *([] if latency is None else [{
                "area": "Tool-agent decision latency p95",
                "hng": latency["arms"]["hng_advisory"]["across_repeat_bootstrap_95_ci_ms"]["p95"]["mean"],
                "baseline": latency["arms"]["strong_structured_memory"]["across_repeat_bootstrap_95_ci_ms"]["p95"]["mean"],
                "delta": (
                    latency["arms"]["hng_advisory"]["across_repeat_bootstrap_95_ci_ms"]["p95"]["mean"]
                    - latency["arms"]["strong_structured_memory"]["across_repeat_bootstrap_95_ci_ms"]["p95"]["mean"]
                ),
                "unit": "milliseconds",
                "significance": None,
                "evidence_class": "local_synthetic",
                "status": "LOSS_LATENCY",
                "notes": f"Mean per-run p95 over {latency['repeat_count']} independent-store repeats; both arms have identical behavior.",
            }]),
            *([] if belief is None else [{
                "area": "Synthetic belief revision",
                "hng": belief["arms"]["hng_belief_store_authority"]["current_belief_accuracy"],
                "baseline": belief["arms"]["strong_structured_authority"]["current_belief_accuracy"],
                "delta": belief["hng_vs_strong_structured"]["accuracy_delta"],
                "significance": None,
                "evidence_class": "synthetic",
                "status": "LOSS_TIE",
                "notes": "Authority policy plus HNG revision history ties the same strong structured policy; component study only.",
            }]),
            *([] if provenance is None else [{
                "area": "Synthetic provenance governance",
                "hng": provenance["summaries"]["hng_provenance_governance"]["accuracy"],
                "baseline": provenance["summaries"]["strong_structured_provenance_governance"]["accuracy"],
                "delta": provenance["hng_vs_strong_accuracy_delta"],
                "significance": None,
                "evidence_class": "synthetic",
                "status": "LOSS_TIE",
                "notes": "Governed provenance beats ignored/display-only provenance, but HNG ties StrongStructuredBaseline on 25 poison cases.",
            }]),
            *([] if action is None else [{
                "area": "Synthetic action experience",
                "hng": action["summaries"]["hng_governed_transitions"]["action_success_rate"],
                "baseline": max(
                    payload["action_success_rate"]
                    for name, payload in action["summaries"].items()
                    if name != "hng_governed_transitions"
                ),
                "delta": action["summaries"]["hng_governed_transitions"]["action_success_rate"]
                - max(
                    payload["action_success_rate"]
                    for name, payload in action["summaries"].items()
                    if name != "hng_governed_transitions"
                ),
                "significance": None,
                "evidence_class": "synthetic",
                "status": "LOSS",
                "notes": "HNG ties structured/graph/Strong at 68% and loses to nearest-experience retrieval at 75%.",
            }]),
            *([] if consolidation is None else [{
                "area": "Synthetic consolidation behavior",
                "hng": 1.0 if consolidation["raw_only"] == consolidation["raw_plus_consolidation"] else 0.0,
                "baseline": 1.0,
                "delta": 0.0 if consolidation["raw_only"] == consolidation["raw_plus_consolidation"] else -1.0,
                "significance": None,
                "evidence_class": "synthetic",
                "status": "LOSS_TIE",
                "notes": "Raw+consolidation exactly preserves raw action behavior; patterns-only action evaluation is unsupported.",
            }]),
            *public_scoreboard_rows,
        ],
    }
    payload = {
        "schema_version": 1,
        "integrity": {
            "literature_mixed_with_local": False,
            "candidate_pool_identity_verified": bool(
                deterministic["candidate_pool_identity_verified"]
                and llm["candidate_pool_identity_verified"]
            ),
            "llm_failed_events": llm["failed_events"],
            "github_status": "CONNECTED_VERIFIED_PRIVATE_YODER23_HNG_MEMORY",
            "public_candidate_invariants_verified": (
                None if longmem is None and locomo is None and personamem is None and budget is None and hybrid is None else bool(
                    (longmem is None or longmem["all_fixed_candidate_invariants_pass"])
                    and (locomo is None or locomo["all_fixed_candidate_invariants_pass"])
                    and (personamem is None or personamem["all_fixed_candidate_invariants_pass"])
                    and (budget is None or budget["all_fixed_candidate_k64_invariants_pass"])
                    and (hybrid is None or hybrid["all_fixed_candidate_hybrid_invariants_pass"])
                )
            ),
        },
        "results": results,
    }
    (EVAL / "RESULTS.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    fieldnames = list(results[0])
    with (EVAL / "RESULTS.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    (EVAL / "SCOREBOARD.json").write_text(json.dumps(scoreboard, indent=2, sort_keys=True), encoding="utf-8")
    environment = {
        "schema_version": 1,
        "purpose": "Breakthrough-program execution environment and pinned external resources",
        "release_baseline_commit": baseline.get("baseline_commit"),
        "frozen_baseline_environment": baseline_environment,
        "current_hardware": resource_inventory["hardware"],
        "current_models": resource_inventory["models"],
        "github": resource_inventory["github"],
        "current_release_artifacts": resource_inventory.get("release_artifacts"),
        "public_resources": public_resources,
    }
    (EVAL / "ENVIRONMENT.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    markdown = [
        "# Breakthrough Scoreboard",
        "",
        "Machine source: SCOREBOARD.json. Generated by scripts/compile_breakthrough.py.",
        "",
        "| Area | HNG | Strongest baseline | Delta | Significant? | Evidence class | Status |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for item in scoreboard["rows"]:
        if item.get("unit") == "milliseconds":
            hng = fmt(item["hng"], "milliseconds")
            baseline_value = fmt(item["baseline"], "milliseconds")
            delta = fmt(item["delta"], "milliseconds")
            if item["delta"] is not None and float(item["delta"]) >= 0:
                delta = "+" + delta
            significance = fmt(None, "fraction")
            markdown.append(
                f"| {item['area']} | {hng} | {baseline_value} | {delta} | {significance} | "
                f"{item['evidence_class']} | {item['status']}: {item['notes']} |"
            )
            continue
        hng = "—" if item["hng"] is None else f"{float(item['hng']) * 100:.1f}%"
        baseline_value = "—" if item["baseline"] is None else f"{float(item['baseline']) * 100:.1f}%"
        delta = "—" if item["delta"] is None else f"{float(item['delta']) * 100:+.1f} pp"
        significance = "—"
        if item["significance"]:
            significance = f"p={float(item['significance']['p']):.4g}"
        markdown.append(
            f"| {item['area']} | {hng} | {baseline_value} | {delta} | {significance} | "
            f"{item['evidence_class']} | {item['status']}: {item['notes']} |"
        )
    markdown.extend([
        "",
        "An em dash means not measured, never zero. Literature numbers are excluded from local result",
        "columns. Synthetic results do not satisfy real-assistant or public-benchmark gates.",
        "",
    ])
    rendered_scoreboard = "\n".join(markdown)
    (EVAL / "SCOREBOARD.md").write_text(rendered_scoreboard, encoding="utf-8")
    (EVAL / "BREAKTHROUGH_SCOREBOARD.md").write_text(rendered_scoreboard, encoding="utf-8")
    print(json.dumps({"results": len(results), "scoreboard_rows": len(scoreboard["rows"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
