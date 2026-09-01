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
    deterministic = load(EVAL / "fixed_candidate" / "DETERMINISTIC_RESULTS.json")
    llm = load(EVAL / "fixed_candidate" / "LLM_RESULTS.json")
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

    blocked = {
        "real_hdc_task_success": "Production HDC interpreter/checkpoint and real traces absent.",
        "longmemeval_v2": "Official dataset/harness not installed; canonical model/judge resources unresolved.",
        "locomo_plus": "Official dataset/harness not installed.",
        "personamem_v2": "Official dataset/harness not installed.",
    }
    for area, reason in blocked.items():
        results.append(row(
            area,
            "hng",
            "primary_metric",
            None,
            "fraction",
            "real" if area.startswith("real_hdc") else "public",
            "BLOCKED_EXTERNAL",
            "RESOURCE_INVENTORY.json",
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
            *[
                {
                    "area": area.replace("_", " ").title(),
                    "hng": None,
                    "baseline": None,
                    "delta": None,
                    "significance": None,
                    "evidence_class": "public",
                    "status": "BLOCKED_EXTERNAL",
                    "notes": blocked[area],
                }
                for area in ("longmemeval_v2", "locomo_plus", "personamem_v2")
            ],
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
            "github_status": "DISCONNECTED_PENDING_USER_ACCOUNT",
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

    markdown = [
        "# Breakthrough Scoreboard",
        "",
        "Machine source: SCOREBOARD.json. Generated by scripts/compile_breakthrough.py.",
        "",
        "| Area | HNG | Strongest baseline | Delta | Significant? | Evidence class | Status |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for item in scoreboard["rows"]:
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
    (EVAL / "SCOREBOARD.md").write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps({"results": len(results), "scoreboard_rows": len(scoreboard["rows"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
