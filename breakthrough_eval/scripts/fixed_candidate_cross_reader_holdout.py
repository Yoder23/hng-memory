#!/usr/bin/env python3
"""Prepare the disjoint two-reader fixed-candidate holdout."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import subprocess
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
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
        "family": "qwen35",
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT, text=True, encoding="utf-8",
    ).strip()


def git_is_clean_except_runtime(output: Path) -> bool:
    status = subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT, text=True, encoding="utf-8",
    )
    try:
        relative = output.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        relative = ""
    allowed = {f"{relative}/RESULTS.json"} if relative else set()
    for reader in READERS:
        allowed.update({
            f"{relative}/readers/{reader}/LLM_RESULTS.json",
            f"{relative}/readers/{reader}/raw/llm_events.jsonl",
        })
    dirty = {
        line[3:].split(" -> ")[-1].replace(chr(92), "/")
        for line in status.splitlines() if len(line) >= 4
    }
    return dirty <= allowed


def installed_readers(endpoint: str, timeout: float) -> dict[str, dict[str, Any]]:
    with urllib.request.urlopen(endpoint.rstrip("/") + "/api/tags", timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = {}
    for reader, spec in READERS.items():
        matches = [item for item in payload.get("models", []) if item.get("name") == spec["model"]]
        if len(matches) != 1:
            raise RuntimeError(f"expected one installed {reader} reader, found {len(matches)}")
        item = matches[0]
        observed_family = str(item.get("details", {}).get("family", "")).lower()
        if item.get("digest") != spec["digest"] or observed_family != spec["family"]:
            raise RuntimeError(f"installed {reader} model provenance mismatch")
        result[reader] = item
    return result


def freeze_manifest(
    output: Path, *, endpoint: str, timeout: float
) -> dict[str, Any]:
    if output.resolve() != DEFAULT_OUTPUT.resolve():
        raise RuntimeError("preregistration manifest requires the default output path")
    prepared = prepare(output)
    installed = installed_readers(endpoint, timeout)
    mistral_qualification = ROOT / "breakthrough_eval" / "fixed_candidate_cross_family" / "MODEL_QUALIFICATION.json"
    qualification = json.loads(mistral_qualification.read_text(encoding="utf-8"))
    outer_hash = qualification["outer_prompt_template_sha256"]
    qwen_event_path = ROOT / "breakthrough_eval" / "fixed_candidate" / "raw" / "llm_events.jsonl"
    qwen_outer_hashes = {
        json.loads(line).get("outer_prompt_template_sha256")
        for line in qwen_event_path.read_text(encoding="utf-8").splitlines()
    }
    if qwen_outer_hashes != {outer_hash}:
        raise RuntimeError("Qwen and Mistral source prompt-template hashes differ")
    paths = [
        output / "PREPARED.json",
        output / "PROTOCOL.md",
        ROOT / "breakthrough_eval" / "scripts" / "fixed_candidate_cross_reader_holdout.py",
        ROOT / "breakthrough_eval" / "scripts" / "fixed_candidate_governance.py",
        ROOT / "breakthrough_eval" / "scripts" / "compile_breakthrough.py",
        ROOT / "breakthrough_eval" / "scripts" / "reproduce.py",
        ROOT / "breakthrough_eval" / "tests" / "test_fixed_candidate_cross_reader_holdout.py",
        ROOT / "breakthrough_eval" / "tests" / "test_fixed_candidate_governance.py",
        PRIOR_PREPARED,
        mistral_qualification,
        ROOT / "breakthrough_eval" / "fixed_candidate_cross_family" / "EXECUTION_MANIFEST.json",
        ROOT / "breakthrough_eval" / "fixed_candidate" / "LLM_RESULTS.json",
        qwen_event_path,
    ]
    payload = {
        "schema_version": fixed.SCHEMA_VERSION,
        "status": "PREREGISTERED_SCORE_BLIND",
        "protocol": PROTOCOL,
        "sample_count": FIXED_CASES,
        "expected_events": prepared["expected_events"],
        "systems": list(SYSTEMS),
        "readers": READERS,
        "installed_reader_metadata": installed,
        "outer_prompt_template_sha256": outer_hash,
        "primary_comparison": "hng_vs_ordinary_rag within each reader",
        "complexity_control": "hng_vs_strong_structured within each reader",
        "familywise_alpha": 0.05,
        "per_reader_alpha": 0.025,
        "joint_success_rule": "both reader deltas > 0, both bootstrap ci95_low > 0, and both exact McNemar p < 0.025",
        "frozen_files": {path.relative_to(ROOT).as_posix(): file_sha256(path) for path in paths},
    }
    path = output / "MANIFEST.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise RuntimeError("existing preregistration manifest no longer matches")
        return existing
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def verify_manifest(output: Path) -> dict[str, Any]:
    manifest = json.loads((output / "MANIFEST.json").read_text(encoding="utf-8"))
    expected = {
        "status": "PREREGISTERED_SCORE_BLIND",
        "protocol": PROTOCOL,
        "sample_count": FIXED_CASES,
        "expected_events": FIXED_CASES * len(SYSTEMS) * len(READERS),
        "readers": READERS,
    }
    mismatch = {key: manifest.get(key) for key, value in expected.items() if manifest.get(key) != value}
    if mismatch:
        raise RuntimeError(f"preregistration manifest metadata mismatch: {mismatch}")
    if not manifest.get("frozen_files"):
        raise RuntimeError("preregistration manifest has no frozen files")
    for relative, digest in manifest["frozen_files"].items():
        path = (ROOT / relative).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError as error:
            raise RuntimeError(f"manifest path escapes repository: {relative}") from error
        if file_sha256(path) != digest:
            raise RuntimeError(f"preregistered file digest mismatch: {relative}")
    return manifest


def validate_existing_log(
    path: Path, *, reader: str, preregistered_commit: str
) -> None:
    if not path.exists():
        return
    spec = READERS[reader]
    expected = {
        "protocol": PROTOCOL,
        "model": spec["model"],
        "model_digest": spec["digest"],
        "preregistered_commit": preregistered_commit,
    }
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        row = json.loads(line)
        mismatch = {key: row.get(key) for key, value in expected.items() if row.get(key) != value}
        if mismatch:
            raise RuntimeError(f"{reader} event provenance mismatch at line {line_number}: {mismatch}")


def comparison_pass(statistics: dict[str, Any]) -> bool:
    bootstrap = statistics["paired_bootstrap_accuracy"]
    mcnemar = statistics["mcnemar"]
    return bool(
        bootstrap["delta"] > 0
        and bootstrap["ci95_low"] > 0
        and mcnemar["exact_two_sided_p"] < 0.025
    )


def audit_events(
    prepared: dict[str, Any], output: Path, *, preregistered_commit: str,
    outer_prompt_template_sha256: str,
) -> dict[str, Any]:
    by_case = {row["case_id"]: row for row in prepared["cases"]}
    expected_keys = {
        (reader, case_id, system)
        for reader in READERS for case_id in by_case for system in SYSTEMS
    }
    completed_keys = []
    all_attempt_inputs = []
    all_completed_outer = []
    total_failures = 0
    total_rows = 0
    for reader, spec in READERS.items():
        path = output / "readers" / reader / "raw" / "llm_events.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        total_rows += len(rows)
        total_failures += sum(row.get("status") == "failed" for row in rows)
        for row in rows:
            case = by_case.get(row.get("case_id"))
            system = row.get("system")
            order = None if case is None else case["system_order"].get(reader)
            all_attempt_inputs.append(bool(
                case and system in SYSTEMS and order
                and row.get("candidate_ids") == case["candidate_ids"]
                and row.get("candidate_pool_sha256") == case["candidate_pool_sha256"]
                and row.get("memory_context_sha256") == case["memory_context_sha256"][system]
                and fixed.stable_hash(row.get("expected")) == case["expected_sha256"]
                and row.get("system_order") == order
                and row.get("execution_order_index") == order.index(system)
                and row.get("model") == spec["model"]
                and row.get("model_digest") == spec["digest"]
                and row.get("protocol") == PROTOCOL
                and row.get("preregistered_commit") == preregistered_commit
            ))
            if row.get("status") == "completed":
                completed_keys.append((reader, row["case_id"], system))
                all_completed_outer.append(
                    row.get("outer_prompt_template_sha256") == outer_prompt_template_sha256
                )
    counts = Counter(completed_keys)
    invariants = {
        "exact_expected_completed_keys": set(counts) == expected_keys,
        "one_completed_event_per_key": all(value == 1 for value in counts.values()),
        "all_attempt_inputs_and_orders_match_prepared": bool(all_attempt_inputs) and all(all_attempt_inputs),
        "all_completed_outer_prompts_match_frozen": bool(all_completed_outer) and all(all_completed_outer),
    }
    return {
        "expected_completed_events": len(expected_keys),
        "completed_events": len(completed_keys),
        "unique_completed_keys": len(counts),
        "total_attempt_rows": total_rows,
        "historical_failed_events": total_failures,
        "invariants": invariants,
        "all_invariants_pass": all(invariants.values()),
    }


def execute(
    output: Path, *, endpoint: str, timeout: float, preregistered_commit: str
) -> dict[str, Any]:
    prepared = prepare(output)
    manifest = verify_manifest(output)
    installed_readers(endpoint, timeout)
    if git_head() != preregistered_commit:
        raise RuntimeError("execution checkout must equal --preregistered-commit")
    if not git_is_clean_except_runtime(output):
        raise RuntimeError("checkout has changes outside append-only runtime outputs")
    scenarios = selected_scenarios()
    reader_results = {}
    for reader, spec in READERS.items():
        reader_output = output / "readers" / reader
        event_path = reader_output / "raw" / "llm_events.jsonl"
        validate_existing_log(event_path, reader=reader, preregistered_commit=preregistered_commit)
        orders = {
            row["case_id"]: tuple(row["system_order"][reader]) for row in prepared["cases"]
        }
        reader_results[reader] = fixed.run_llm(
            scenarios,
            reader_output,
            model=spec["model"],
            model_digest=spec["digest"],
            endpoint=endpoint,
            timeout=timeout,
            limit=FIXED_CASES,
            protocol=PROTOCOL,
            preregistered_commit=preregistered_commit,
            system_orders=orders,
        )
    audit = audit_events(
        prepared, output, preregistered_commit=preregistered_commit,
        outer_prompt_template_sha256=manifest["outer_prompt_template_sha256"],
    )
    primary = {
        reader: result["paired_statistics"]["hng_vs_ordinary_rag"]
        for reader, result in reader_results.items()
    }
    control = {
        reader: result["paired_statistics"]["hng_vs_strong_structured"]
        for reader, result in reader_results.items()
    }
    result = {
        "schema_version": fixed.SCHEMA_VERSION,
        "status": (
            "complete_with_recovered_failures"
            if audit["all_invariants_pass"] and audit["historical_failed_events"]
            else "complete" if audit["all_invariants_pass"] else "partial"
        ),
        "protocol": PROTOCOL,
        "evidence_class": "synthetic",
        "claim_boundary": "Disjoint generated-case replication across two pinned reader families; not public or real-assistant evidence.",
        "preregistered_commit": preregistered_commit,
        "prepared_file_sha256": file_sha256(output / "PREPARED.json"),
        "reader_results": reader_results,
        "primary_by_reader": primary,
        "complexity_control_by_reader": control,
        "primary_pass_by_reader": {reader: comparison_pass(value) for reader, value in primary.items()},
        "complexity_control_pass_by_reader": {reader: comparison_pass(value) for reader, value in control.items()},
        "structured_context_familywise_supported": all(comparison_pass(value) for value in primary.values()),
        "hng_specific_familywise_supported": all(comparison_pass(value) for value in control.values()),
        "created_at": utc_now(),
        **audit,
    }
    (output / "RESULTS.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--preregistered-commit", default="")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--freeze-manifest", action="store_true")
    args = parser.parse_args()
    if args.prepare_only:
        payload = prepare(args.output)
        print(json.dumps({
            "status": payload["status"], "samples": payload["sample_count"],
            "expected_events": payload["expected_events"], "order_balance": payload["order_balance"],
        }, indent=2, sort_keys=True))
        return 0
    if args.freeze_manifest:
        print(json.dumps(
            freeze_manifest(args.output, endpoint=args.endpoint, timeout=args.timeout),
            indent=2, sort_keys=True,
        ))
        return 0
    if not args.preregistered_commit:
        raise RuntimeError("--preregistered-commit is required for execution")
    result = execute(
        args.output, endpoint=args.endpoint, timeout=args.timeout,
        preregistered_commit=args.preregistered_commit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["all_invariants_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
