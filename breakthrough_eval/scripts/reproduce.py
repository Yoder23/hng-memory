#!/usr/bin/env python3
"""Small reproducibility command surface for the breakthrough evidence workspace."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "breakthrough_eval" / "scripts"


@dataclass(frozen=True)
class Command:
    name: str
    argv: tuple[str, ...]
    note: str

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "argv": list(self.argv), "note": self.note}


def py(*values: str) -> tuple[str, ...]:
    return (sys.executable, *values)


def commands_for(args: argparse.Namespace) -> list[Command]:
    tests = Command(
        "breakthrough_tests",
        py("-m", "pytest", "-q", "breakthrough_eval/tests"),
        "Local harness, invariants, governance, and public-adapter tests.",
    )
    deterministic = Command(
        "adversarial_250",
        py(str(SCRIPTS / "fixed_candidate_governance.py")),
        "Exactly 250 frozen synthetic governance scenarios; appends raw events.",
    )
    compile_results = Command(
        "compile_results",
        py(str(SCRIPTS / "compile_breakthrough.py")),
        "Regenerate RESULTS.json/csv and SCOREBOARD.json/md from machine evidence.",
    )
    if args.command == "core":
        return [tests, deterministic, compile_results]
    if args.command == "adversarial":
        return [deterministic, tests, compile_results]
    if args.command == "rag-governance":
        result = [deterministic]
        if args.execute_llm:
            result.append(Command(
                "fixed_llm_governance",
                py(str(SCRIPTS / "fixed_candidate_governance.py"), "--llm", "--llm-limit", str(args.llm_limit)),
                "Frozen local-LLM holdout; requires the recorded Ollama model digest.",
            ))
        result.append(compile_results)
        return result
    if args.command == "public-memory":
        longmem_argv = [sys.executable, str(SCRIPTS / "longmemeval_v2_text_pilot.py")]
        locomo_argv = [sys.executable, str(SCRIPTS / "locomo_plus_pilot.py")]
        personamem_argv = [sys.executable, str(SCRIPTS / "personamem_v2_pilot.py")]
        if not args.execute_llm:
            longmem_argv.append("--prepare-only")
            locomo_argv.append("--prepare-only")
            personamem_argv.append("--prepare-only")
        return [
            Command(
                "longmemeval_v2_text_pilot",
                tuple(longmem_argv),
                "Official pinned public data; noncanonical text-only local pilot.",
            ),
            Command(
                "locomo_plus_six_category_pilot",
                tuple(locomo_argv),
                "Official pinned public data/templates; noncanonical six-category local pilot.",
            ),
            Command(
                "personamem_v2_seven_stratum_pilot",
                tuple(personamem_argv),
                "Official pinned public data; noncanonical seven-stratum personalization pilot.",
            ),
            compile_results,
        ]
    if args.command == "belief-revision":
        return [
            Command(
                "belief_revision_component_probe",
                py(str(SCRIPTS / "belief_revision_probe.py")),
                "Synthetic five-event timelines against the shipped BeliefStore.",
            ),
            tests,
            compile_results,
        ]
    if args.command == "component-probes":
        return [
            Command("belief_revision", py(str(SCRIPTS / "belief_revision_probe.py")), "Synthetic belief-revision timelines."),
            Command("provenance_ablation", py(str(SCRIPTS / "provenance_ablation.py")), "Synthetic provenance-governance ablation."),
            Command("action_experience", py(str(SCRIPTS / "action_experience_probe.py")), "Synthetic executing action-experience probe."),
            Command("consolidation", py(str(SCRIPTS / "consolidation_probe.py")), "Synthetic reversible consolidation audit."),
            Command("hng_ablation_matrix", py(str(SCRIPTS / "hng_ablation_matrix.py")), "Synthetic 250-scenario component-ablation matrix."),
            tests,
            compile_results,
        ]
    if args.command == "scaled-isolation":
        return [
            Command(
                "multi_user_100k_isolation",
                py(str(SCRIPTS / "multi_user_isolation_probe.py")),
                "100,000-principal scoped storage and actor-policy isolation probe; approximately seven minutes on the recorded host.",
            ),
            tests,
            compile_results,
        ]
    raise AssertionError(f"unknown command: {args.command}")


def run_commands(commands: Sequence[Command], *, dry_run: bool) -> int:
    manifest = {
        "schema_version": 1,
        "working_directory": str(ROOT),
        "dry_run": dry_run,
        "commands": [item.as_dict() for item in commands],
    }
    print(json.dumps(manifest, indent=2))
    if dry_run:
        return 0
    for item in commands:
        print(f"\n== {item.name} ==", flush=True)
        completed = subprocess.run(item.argv, cwd=ROOT, check=False)
        if completed.returncode:
            print(json.dumps({
                "status": "failed",
                "command": item.name,
                "returncode": completed.returncode,
            }))
            return completed.returncode
    print(json.dumps({"status": "complete", "commands": len(commands)}))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print exact commands without executing them.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("core", help="Run breakthrough tests, deterministic 250, and compile results.")
    subparsers.add_parser("adversarial", help="Run the 250-scenario suite, tests, and compile results.")
    rag = subparsers.add_parser("rag-governance", help="Reproduce fixed-candidate governance results.")
    rag.add_argument("--execute-llm", action="store_true", help="Run the costly local 27B holdout.")
    rag.add_argument("--llm-limit", type=int, default=30)
    public = subparsers.add_parser("public-memory", help="Prepare or execute the public text pilot.")
    public.add_argument("--execute-llm", action="store_true", help="Run all local reader/judge calls.")
    subparsers.add_parser("belief-revision", help="Reproduce the synthetic belief-revision component study.")
    subparsers.add_parser("component-probes", help="Reproduce all packaged synthetic component studies.")
    subparsers.add_parser("scaled-isolation", help="Run the 100,000-principal scoped isolation probe.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_commands(commands_for(args), dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
