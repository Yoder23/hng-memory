#!/usr/bin/env python3
"""Fail-closed readiness gate for the real HDC assistant HNG-off/on experiment.

This verifier does not execute or import a production assistant. It validates the
artifact contract needed before a paired run may be called real-HDC evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "breakthrough_eval" / "real_hdc" / "READINESS.json"
REQUIRED_ARTIFACTS = (
    "interpreter",
    "checkpoint",
    "action_library",
    "workload_traces",
    "hng_off_config",
    "hng_on_config",
    "preregistration",
    "runner",
)
REQUIRED_INVARIANTS = (
    "same_interpreter",
    "same_checkpoint",
    "same_action_library",
    "same_reasoning_policy",
    "same_tools",
    "same_tasks",
    "same_retrieval_candidates",
    "only_memory_governance_changes",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str | None:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def evaluate_manifest(manifest: Mapping[str, Any] | None, *, manifest_path: Path | None) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    artifacts: dict[str, dict[str, Any]] = {}
    if manifest is None:
        failures.append({"code": "manifest_not_supplied", "detail": "No real-HDC experiment manifest was supplied."})
        manifest = {}

    if manifest.get("evidence_class") != "real":
        failures.append({"code": "evidence_class_not_real", "detail": "Manifest must declare evidence_class=real."})
    if manifest.get("synthetic_artifacts") is not False:
        failures.append({"code": "synthetic_exclusion_unconfirmed", "detail": "Manifest must explicitly declare synthetic_artifacts=false."})

    base = manifest_path.resolve().parent if manifest_path is not None else ROOT
    declared = manifest.get("artifacts")
    declared = declared if isinstance(declared, Mapping) else {}
    for name in REQUIRED_ARTIFACTS:
        item = declared.get(name)
        item = item if isinstance(item, Mapping) else {}
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            failures.append({"code": f"missing_{name}", "detail": f"No path declared for {name}."})
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = base / path
        path = path.resolve()
        if not path.is_file():
            failures.append({"code": f"unreadable_{name}", "detail": f"Required file is absent: {path}"})
            artifacts[name] = {"path": str(path), "exists": False}
            continue
        size = path.stat().st_size
        actual_digest = sha256_file(path)
        artifacts[name] = {"path": str(path), "exists": True, "bytes": size, "sha256": actual_digest}
        if size == 0:
            failures.append({"code": f"empty_{name}", "detail": f"Required file is empty: {path}"})
        expected = item.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            failures.append({"code": f"missing_digest_{name}", "detail": f"A full SHA-256 is required for {name}."})
        elif expected.lower() != actual_digest:
            failures.append({"code": f"digest_mismatch_{name}", "detail": f"Declared SHA-256 does not match {name}."})

    invariants = manifest.get("paired_invariants")
    invariants = invariants if isinstance(invariants, Mapping) else {}
    for name in REQUIRED_INVARIANTS:
        if invariants.get(name) is not True:
            failures.append({"code": f"invariant_unconfirmed_{name}", "detail": f"Paired invariant {name} must be true."})

    primary = manifest.get("primary_metrics")
    if not isinstance(primary, list) or not primary:
        failures.append({"code": "primary_metrics_missing", "detail": "At least one preregistered primary metric is required."})
    sample = manifest.get("minimum_sample_size")
    if not isinstance(sample, int) or isinstance(sample, bool) or sample < 1:
        failures.append({"code": "minimum_sample_size_missing", "detail": "A positive minimum_sample_size is required."})

    return {
        "schema_version": 1,
        "created_at": utc_now(),
        "status": "READY_FOR_PAIRED_EXECUTION" if not failures else "BLOCKED_EXTERNAL",
        "claim_boundary": (
            "Readiness verifies declared local artifacts and paired-design attestations only; "
            "it is not behavioral evidence and does not prove that declared traces are real."
        ),
        "git_commit": git_head(),
        "manifest_path": None if manifest_path is None else str(manifest_path.resolve()),
        "artifacts": artifacts,
        "required_artifacts": list(REQUIRED_ARTIFACTS),
        "required_paired_invariants": list(REQUIRED_INVARIANTS),
        "failure_count": len(failures),
        "failures": failures,
    }


def write_preserving(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    target = path
    if target.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = target.with_name(f"{target.stem}.{stamp}{target.suffix}")
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="Real-HDC experiment manifest JSON.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = None
    if args.manifest is not None:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = evaluate_manifest(manifest, manifest_path=args.manifest)
    target = write_preserving(args.output, result)
    print(json.dumps({"status": result["status"], "output": str(target), "failure_count": result["failure_count"]}, sort_keys=True))
    return 0 if result["status"] == "READY_FOR_PAIRED_EXECUTION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
