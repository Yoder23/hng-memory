#!/usr/bin/env python3
"""Prepare or execute the fixed-candidate holdout with a non-Qwen reader family."""

from __future__ import annotations

import argparse
import hashlib
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

DEFAULT_OUTPUT = ROOT / "breakthrough_eval" / "fixed_candidate_cross_family"
DEFAULT_MODEL = "mistral-small3.1:24b-instruct-2503-q4_K_M"
DEFAULT_DIGEST = "b9aaf0c2586a8ed8105feab808c0f034bd4d346203822f048e2366165a13f4ea"
PROTOCOL = "fixed_candidate_cross_family_llm_holdout"
SYSTEMS = ("ordinary_rag", "strong_structured", "hng")
FIXED_CASES = 30


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def git_is_clean_except_runtime(output: Path) -> bool:
    status = subprocess.check_output(
        [
            "git", "-c", f"safe.directory={ROOT.as_posix()}", "status", "--porcelain",
            "--untracked-files=all",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    try:
        relative_output = output.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        relative_output = ""
    allowed = {
        f"{relative_output}/raw/llm_events.jsonl",
        f"{relative_output}/LLM_RESULTS.json",
    } if relative_output else set()
    dirty_paths = {
        line[3:].split(" -> ")[-1].replace(chr(92), "/")
        for line in status.splitlines()
        if len(line) >= 4
    }
    return dirty_paths <= allowed


def prepared_payload(limit: int) -> dict[str, Any]:
    if limit != FIXED_CASES:
        raise ValueError(f"{PROTOCOL} is frozen at exactly {FIXED_CASES} cases")
    scenarios = [item for item in fixed.generate_scenarios() if item.split == "holdout"][:limit]
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
            "memory_context_chars": {
                system: len(contexts[system]) for system in SYSTEMS
            },
        })
    return {
        "schema_version": fixed.SCHEMA_VERSION,
        "protocol": PROTOCOL,
        "selection": "the same first 30 generated holdout scenarios as the frozen Qwen-family study",
        "seed": fixed.SEED,
        "sample_count": len(rows),
        "systems": list(SYSTEMS),
        "cases": rows,
    }


def prepare(output: Path, limit: int) -> dict[str, Any]:
    payload = prepared_payload(limit)
    path = output / "PREPARED.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if fixed.stable_hash(existing) != fixed.stable_hash(payload):
            raise RuntimeError(f"prepared cross-family holdout changed: {path}")
        return existing
    output.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def installed_model(endpoint: str, model: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(endpoint.rstrip("/") + "/api/tags", timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    matches = [item for item in payload.get("models", []) if item.get("name") == model]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one installed model named {model!r}, found {len(matches)}")
    return matches[0]


def reader_family(installed: dict[str, Any]) -> str:
    family = str(installed.get("details", {}).get("family", "")).lower()
    if "mistral" not in family or "qwen" in family:
        raise RuntimeError(f"installed reader is not the preregistered Mistral family: {family!r}")
    return family


def validate_existing_log(
    path: Path, *, model: str, model_digest: str, preregistered_commit: str
) -> None:
    if not path.exists():
        return
    expected = {
        "protocol": PROTOCOL,
        "model": model,
        "model_digest": model_digest,
        "preregistered_commit": preregistered_commit,
    }
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        row = json.loads(line)
        mismatches = {key: row.get(key) for key, value in expected.items() if row.get(key) != value}
        if mismatches:
            raise RuntimeError(f"existing event log provenance mismatch at line {line_number}: {mismatches}")


def qualify_model(
    output: Path, *, model: str, model_digest: str, endpoint: str, timeout: float,
    installed: dict[str, Any],
) -> dict[str, Any]:
    qualification_path = output / "MODEL_QUALIFICATION.json"
    if qualification_path.exists():
        existing = json.loads(qualification_path.read_text(encoding="utf-8"))
        if (
            existing.get("status") != "QUALIFIED"
            or existing.get("model") != model
            or existing.get("model_digest") != model_digest
        ):
            raise RuntimeError("existing qualification has incompatible provenance")
        return existing
    scenario = next(item for item in fixed.generate_scenarios() if item.split == "development")
    context = fixed.context_for("ordinary_rag", scenario, fixed.raw_majority_decide(scenario))
    try:
        observed, metadata = fixed.ollama_decide(
            model, scenario, context, endpoint=endpoint, timeout=timeout
        )
    except Exception as error:
        fixed.append_jsonl(output / "MODEL_QUALIFICATION_FAILURES.jsonl", {
            "schema_version": fixed.SCHEMA_VERSION,
            "status": "FAILED",
            "model": model,
            "model_digest": model_digest,
            "smoke_case_id": scenario.case_id,
            "smoke_split": scenario.split,
            "error_type": type(error).__name__,
            "error": str(error),
            "failed_at": utc_now(),
        })
        raise
    payload = {
        "schema_version": fixed.SCHEMA_VERSION,
        "status": "QUALIFIED",
        "qualification_scope": "Endpoint, exact digest, system-message, JSON-schema, and enum-response smoke only; no holdout inference.",
        "model": model,
        "model_digest": model_digest,
        "installed_model_metadata": installed,
        "smoke_case_id": scenario.case_id,
        "smoke_split": scenario.split,
        "returned_decision": observed,
        "prompt_sha256": metadata["prompt_sha256"],
        "outer_prompt_template_sha256": metadata["outer_prompt_template_sha256"],
        "prompt_eval_count": metadata["prompt_eval_count"],
        "eval_count": metadata["eval_count"],
        "raw_response": metadata["raw_response"],
        "qualified_at": utc_now(),
    }
    output.mkdir(parents=True, exist_ok=True)
    qualification_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return payload


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_manifest(
    output: Path, *, model: str, model_digest: str, installed: dict[str, Any]
) -> dict[str, Any]:
    if output.resolve() != DEFAULT_OUTPUT.resolve():
        raise RuntimeError("the preregistration manifest can only freeze the default output")
    qualification_path = output / "MODEL_QUALIFICATION.json"
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    if (
        qualification.get("status") != "QUALIFIED"
        or qualification.get("smoke_split") != "development"
        or qualification.get("model") != model
        or qualification.get("model_digest") != model_digest
    ):
        raise RuntimeError("model qualification does not match the requested preregistration")
    source_event_path = ROOT / "breakthrough_eval" / "fixed_candidate" / "raw" / "llm_events.jsonl"
    source_rows = [
        json.loads(line) for line in source_event_path.read_text(encoding="utf-8").splitlines()
    ]
    source_outer_hashes = {row.get("outer_prompt_template_sha256") for row in source_rows}
    if len(source_outer_hashes) != 1 or qualification.get("outer_prompt_template_sha256") not in source_outer_hashes:
        raise RuntimeError("qualified outer prompt does not match the frozen Qwen-family study")
    paths = [
        output / "PREPARED.json",
        output / "PROTOCOL.md",
        qualification_path,
        ROOT / "breakthrough_eval" / "scripts" / "fixed_candidate_cross_family.py",
        ROOT / "breakthrough_eval" / "scripts" / "fixed_candidate_governance.py",
        ROOT / "breakthrough_eval" / "tests" / "test_fixed_candidate_cross_family.py",
        ROOT / "breakthrough_eval" / "tests" / "test_fixed_candidate_governance.py",
        source_event_path,
        ROOT / "breakthrough_eval" / "fixed_candidate" / "LLM_RESULTS.json",
    ]
    qualification_failures = output / "MODEL_QUALIFICATION_FAILURES.jsonl"
    if qualification_failures.exists():
        paths.append(qualification_failures)
    frozen_files = {
        path.relative_to(ROOT).as_posix(): file_sha256(path) for path in paths
    }
    payload = {
        "schema_version": fixed.SCHEMA_VERSION,
        "status": "PREREGISTERED_SCORE_BLIND",
        "protocol": PROTOCOL,
        "evidence_class": "synthetic",
        "model": model,
        "model_digest": model_digest,
        "model_family": reader_family(installed),
        "parameter_size": installed.get("details", {}).get("parameter_size"),
        "quantization_level": installed.get("details", {}).get("quantization_level"),
        "outer_prompt_template_sha256": qualification["outer_prompt_template_sha256"],
        "sample_count": FIXED_CASES,
        "systems": list(SYSTEMS),
        "expected_events": FIXED_CASES * len(SYSTEMS),
        "primary_comparison": "hng_vs_ordinary_rag",
        "complexity_control": "hng_vs_strong_structured",
        "success_rule": "positive delta, paired-bootstrap ci95_low > 0, and exact two-sided McNemar p < 0.05",
        "frozen_files": frozen_files,
    }
    path = output / "MANIFEST.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise RuntimeError("existing preregistration manifest no longer matches frozen files")
        return existing
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def verify_manifest(output: Path, *, model: str, model_digest: str) -> dict[str, Any]:
    path = output / "MANIFEST.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "status": "PREREGISTERED_SCORE_BLIND",
        "protocol": PROTOCOL,
        "model": model,
        "model_digest": model_digest,
        "sample_count": FIXED_CASES,
        "expected_events": FIXED_CASES * len(SYSTEMS),
    }
    mismatches = {key: manifest.get(key) for key, value in expected.items() if manifest.get(key) != value}
    if mismatches:
        raise RuntimeError(f"preregistration manifest metadata mismatch: {mismatches}")
    for relative, expected_digest in manifest.get("frozen_files", {}).items():
        frozen_path = (ROOT / relative).resolve()
        try:
            frozen_path.relative_to(ROOT.resolve())
        except ValueError as error:
            raise RuntimeError(f"manifest path escapes repository: {relative}") from error
        observed = file_sha256(frozen_path)
        if observed != expected_digest:
            raise RuntimeError(f"preregistered file digest mismatch: {relative}")
    if not manifest.get("frozen_files"):
        raise RuntimeError("preregistration manifest has no frozen files")
    return manifest


def audit_completed(
    prepared: dict[str, Any], event_path: Path, *, outer_prompt_template_sha256: str | None = None
) -> dict[str, Any]:
    rows = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]
    completed = [row for row in rows if row.get("status") == "completed"]
    prepared_by_case = {case["case_id"]: case for case in prepared["cases"]}
    expected_keys = {
        (case_id, system) for case_id in prepared_by_case for system in SYSTEMS
    }
    counts = Counter((row.get("case_id"), row.get("system")) for row in completed)
    actual_keys = set(counts)
    input_checks = []
    for row in rows:
        case = prepared_by_case.get(row.get("case_id"))
        system = row.get("system")
        input_checks.append(bool(
            case
            and system in SYSTEMS
            and row.get("candidate_ids") == case["candidate_ids"]
            and row.get("candidate_pool_sha256") == case["candidate_pool_sha256"]
            and row.get("memory_context_sha256") == case["memory_context_sha256"][system]
            and fixed.stable_hash(row.get("expected")) == case["expected_sha256"]
        ))
    invariants = {
        "exact_expected_completed_keys": actual_keys == expected_keys,
        "one_completed_event_per_key": all(value == 1 for value in counts.values()),
        "all_attempt_inputs_match_prepared": bool(input_checks) and all(input_checks),
        "all_completed_outer_prompts_match_frozen": bool(completed) and all(
            outer_prompt_template_sha256 is not None
            and row.get("outer_prompt_template_sha256") == outer_prompt_template_sha256
            for row in completed
        ) if outer_prompt_template_sha256 is not None else True,
    }
    return {
        "expected_completed_events": len(expected_keys),
        "completed_events": len(completed),
        "unique_completed_keys": len(actual_keys),
        "historical_failed_events": sum(row.get("status") == "failed" for row in rows),
        "fixed_candidate_invariants": invariants,
        "all_fixed_candidate_invariants_pass": all(invariants.values()),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-digest", default=DEFAULT_DIGEST)
    parser.add_argument("--preregistered-commit", default="")
    parser.add_argument("--llm-limit", type=int, default=FIXED_CASES)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=300.0)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--qualify-only", action="store_true")
    mode.add_argument("--freeze-manifest", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prepared = prepare(args.output, args.llm_limit)
    if args.prepare_only:
        print(json.dumps({"status": "prepared", "samples": prepared["sample_count"]}, indent=2))
        return 0
    if not args.model_digest:
        raise RuntimeError("--model-digest is required for cross-family execution")
    installed = installed_model(args.endpoint, args.model, args.timeout)
    observed_digest = str(installed["digest"])
    if observed_digest != args.model_digest:
        raise RuntimeError(
            f"installed model digest mismatch: expected {args.model_digest}, observed {observed_digest}"
        )
    reader_family(installed)
    if args.qualify_only:
        result = qualify_model(
            args.output, model=args.model, model_digest=args.model_digest,
            endpoint=args.endpoint, timeout=args.timeout, installed=installed,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.freeze_manifest:
        result = freeze_manifest(
            args.output, model=args.model, model_digest=args.model_digest, installed=installed
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if not args.preregistered_commit:
        raise RuntimeError("--preregistered-commit is required for cross-family execution")
    verify_manifest(args.output, model=args.model, model_digest=args.model_digest)
    if git_head() != args.preregistered_commit:
        raise RuntimeError("execution checkout must equal --preregistered-commit")
    if not git_is_clean_except_runtime(args.output):
        raise RuntimeError("execution checkout has changes outside the append-only runtime outputs")
    validate_existing_log(
        args.output / "raw" / "llm_events.jsonl",
        model=args.model,
        model_digest=args.model_digest,
        preregistered_commit=args.preregistered_commit,
    )
    result = fixed.run_llm(
        fixed.generate_scenarios(),
        args.output,
        model=args.model,
        model_digest=args.model_digest,
        endpoint=args.endpoint,
        timeout=args.timeout,
        limit=args.llm_limit,
        protocol=PROTOCOL,
        preregistered_commit=args.preregistered_commit,
    )
    qualification = json.loads(
        (args.output / "MODEL_QUALIFICATION.json").read_text(encoding="utf-8")
    )
    audit = audit_completed(
        prepared,
        args.output / "raw" / "llm_events.jsonl",
        outer_prompt_template_sha256=qualification["outer_prompt_template_sha256"],
    )
    result.update({
        "benchmark": PROTOCOL,
        "claim_boundary": "Synthetic fixed-candidate replication with a second reader family; not public or real-assistant evidence.",
        "primary_comparison": "hng_vs_ordinary_rag",
        "complexity_control": "hng_vs_strong_structured",
        "prepared_file_sha256": file_sha256(args.output / "PREPARED.json"),
        "created_at": utc_now(),
        **audit,
    })
    result["status"] = (
        "complete_with_recovered_failures"
        if audit["all_fixed_candidate_invariants_pass"] and audit["historical_failed_events"]
        else "complete"
        if audit["all_fixed_candidate_invariants_pass"]
        else "partial"
    )
    (args.output / "LLM_RESULTS.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if audit["all_fixed_candidate_invariants_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
