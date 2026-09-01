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
        "Exactly 250 frozen synthetic governance scenarios; refuses to overwrite an existing raw log.",
    )
    fresh_clone_deterministic = Command(
        "adversarial_250_isolated",
        py(
            str(SCRIPTS / "fixed_candidate_governance.py"),
            "--output", str(ROOT / ".hng-eval-proof" / "fixed_candidate"),
        ),
        "Exactly 250 frozen synthetic governance scenarios in a new ignored proof directory; frozen evidence remains immutable.",
    )
    compile_results = Command(
        "compile_results",
        py(str(SCRIPTS / "compile_breakthrough.py")),
        "Regenerate RESULTS.json/csv and SCOREBOARD.json/md from machine evidence.",
    )
    fresh_clone_tests = Command(
        "breakthrough_tests_dependency_free",
        py(
            "-m", "pytest", "-q", "breakthrough_eval/tests",
            "--ignore=breakthrough_eval/tests/test_locomo_hybrid_holdout.py",
            "--ignore=breakthrough_eval/tests/test_locomo_plus_pilot.py",
            "--ignore=breakthrough_eval/tests/test_locomo_reranker_holdout.py",
            "--ignore=breakthrough_eval/tests/test_locomo_retrieval_budget_holdout.py",
        ),
        "Owned tests available without the intentionally uncommitted external LoCoMo task_eval checkout; four exact exclusions are explicit.",
    )
    if args.command == "core":
        return [tests, deterministic, compile_results]
    if args.command == "adversarial":
        return [deterministic, tests, compile_results]
    if args.command == "fresh-clone-core":
        return [fresh_clone_tests, fresh_clone_deterministic, compile_results]
    if args.command == "identifiability":
        return [
            Command(
                "strong_hng_identifiability_audit",
                py(str(SCRIPTS / "identifiability_audit.py")),
                "Read-only hash audit of whether preserved Strong/HNG reader arms received distinct inputs.",
            ),
            compile_results,
        ]
    if args.command == "policy-differential":
        return [
            Command(
                "hng_strong_policy_differential_development",
                py(str(SCRIPTS / "policy_differential_search.py")),
                "Unlabeled bounded development grid; does not run a reader or create holdout evidence.",
            ),
            compile_results,
        ]
    if args.command == "million-write":
        argv = [sys.executable, str(SCRIPTS / "million_write_reliability.py")]
        if args.prepare_only:
            argv.append("--prepare-only")
        else:
            if not args.preregistered_commit:
                raise ValueError("million-write execution requires --preregistered-commit")
            argv.extend(["--preregistered-commit", args.preregistered_commit])
        return [Command(
            "million_write_storage_reliability",
            tuple(argv),
            "Fail-closed 1,000,000-write production SQLite store, restart, lifecycle, and backup/restore probe.",
        )]
    if args.command == "sustained-reliability":
        argv = [sys.executable, str(SCRIPTS / "sustained_reliability.py")]
        if args.prepare_only:
            argv.append("--prepare-only")
        else:
            if not args.preregistered_commit:
                raise ValueError(
                    "sustained-reliability execution requires "
                    "--preregistered-commit"
                )
            argv.extend([
                "--preregistered-commit", args.preregistered_commit,
            ])
        return [Command(
            "sustained_multiprocess_storage_reliability",
            tuple(argv),
            (
                "Fail-closed two-hour multi-process production-store run "
                "with worker rotation, repeated backup/restore, and resource "
                "sampling."
            ),
        )]
    if args.command == "sustained-reliability-v2":
        argv = [
            sys.executable,
            str(SCRIPTS / "sustained_reliability_v2.py"),
        ]
        if args.prepare_only:
            argv.append("--prepare-only")
        else:
            if not args.preregistered_commit:
                raise ValueError(
                    "sustained-reliability-v2 execution requires "
                    "--preregistered-commit"
                )
            argv.extend([
                "--preregistered-commit", args.preregistered_commit,
            ])
        return [Command(
            "sustained_write_quiesced_recovery_v2",
            tuple(argv),
            (
                "Failure-driven two-hour recovery run with transaction-"
                "boundary writer pause, live readers, monitored backup child, "
                "and hard resource/disk/time limits."
            ),
        )]
    if args.command == "handle-observer-diagnostic":
        argv = [
            sys.executable,
            str(SCRIPTS / "handle_observer_diagnostic.py"),
        ]
        if args.prepare_only:
            argv.append("--prepare-only")
        else:
            if not args.preregistered_commit:
                raise ValueError(
                    "handle-observer-diagnostic execution requires "
                    "--preregistered-commit"
                )
            argv.extend([
                "--preregistered-commit", args.preregistered_commit,
            ])
        return [Command(
            "child_handle_observer_effect_diagnostic",
            tuple(argv),
            (
                "Attribution-only quiet/external/quiet child self-sampling "
                "diagnostic; it cannot qualify HNG or reliability."
            ),
        )]
    if args.command == "handle-observer-diagnostic-v2":
        argv = [
            sys.executable,
            str(SCRIPTS / "handle_observer_diagnostic_v2.py"),
        ]
        if args.prepare_only:
            argv.append("--prepare-only")
        else:
            if not args.preregistered_commit:
                raise ValueError(
                    "handle-observer-diagnostic-v2 execution requires "
                    "--preregistered-commit"
                )
            argv.extend([
                "--preregistered-commit", args.preregistered_commit,
            ])
        return [Command(
            "child_handle_observer_effect_diagnostic_v2",
            tuple(argv),
            "Timing-corrected attribution-only diagnostic; no HNG claim.",
        )]
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
    if args.command == "tool-agent":
        return [
            Command(
                "tool_agent_advisory",
                py(str(SCRIPTS / "tool_agent_advisory_probe.py"), "--protocol-label", "reproduction"),
                "Executing synthetic advisory benchmark; existing evidence receives a timestamped revision.",
            ),
            tests,
            compile_results,
        ]
    if args.command == "real-hdc":
        argv = [sys.executable, str(SCRIPTS / "real_hdc_readiness.py")]
        if args.manifest is not None:
            argv.extend(["--manifest", str(args.manifest)])
        return [Command(
            "real_hdc_readiness",
            tuple(argv),
            "Fail-closed artifact and paired-invariant gate; this does not substitute for executing the real assistant.",
        )]
    if args.command == "latency":
        return [
            Command(
                "repeated_tool_agent_latency",
                py(str(SCRIPTS / "repeated_latency_probe.py"), "--repeats", str(args.repeats)),
                "Repeated independent-store latency runs with bootstrap intervals over per-run p50/p95/p99.",
            ),
            compile_results,
        ]
    if args.command == "retrieval-budget":
        argv = [sys.executable, str(SCRIPTS / "locomo_retrieval_budget_holdout.py")]
        if not args.execute_llm:
            argv.append("--prepare-only")
        return [
            Command(
                "locomo_disjoint_retrieval_budget_holdout",
                tuple(argv),
                "Disjoint public-data 16/32/64-turn retrieval budget sweep after the observed top-16 loss.",
            ),
            compile_results,
        ]
    if args.command == "hybrid-holdout":
        argv = [sys.executable, str(SCRIPTS / "locomo_hybrid_holdout.py")]
        if not args.execute_llm:
            argv.append("--prepare-only")
        return [
            Command(
                "locomo_disjoint_dense_hybrid_holdout",
                tuple(argv),
                "Disjoint public-data BM25/dense/RRF hybrid retrieval and fixed-candidate governance study.",
            ),
            compile_results,
        ]
    if args.command == "reranker-holdout":
        argv = [sys.executable, str(SCRIPTS / "locomo_reranker_holdout.py")]
        if not args.execute_llm:
            argv.append("--prepare-only")
        return [
            Command(
                "locomo_disjoint_neural_reranker_holdout",
                tuple(argv),
                "Fourth disjoint public-data window with BM25, dense, RRF, and a pinned Qwen3 cross-encoder reranker.",
            ),
            compile_results,
        ]
    if args.command == "cross-family":
        argv = [sys.executable, str(SCRIPTS / "fixed_candidate_cross_family.py")]
        if not args.execute_llm:
            argv.append("--prepare-only")
        else:
            if not args.preregistered_commit:
                raise ValueError("cross-family execution requires --preregistered-commit")
            argv.extend(["--preregistered-commit", args.preregistered_commit])
        return [
            Command(
                "fixed_candidate_cross_family_llm_holdout",
                tuple(argv),
                "Fixed-case Mistral-family replication of ordinary, Strong, and HNG contexts.",
            ),
            compile_results,
        ]
    if args.command == "cross-reader-holdout":
        argv = [sys.executable, str(SCRIPTS / "fixed_candidate_cross_reader_holdout.py")]
        if not args.execute_llm:
            argv.append("--prepare-only")
        else:
            if not args.preregistered_commit:
                raise ValueError("cross-reader-holdout execution requires --preregistered-commit")
            argv.extend(["--preregistered-commit", args.preregistered_commit])
        return [
            Command(
                "fixed_candidate_disjoint_cross_reader_holdout",
                tuple(argv),
                "Disjoint 30-case Qwen/Mistral holdout with balanced system execution orders.",
            ),
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
    subparsers.add_parser("fresh-clone-core", help="Run the dependency-free owned core from a clean checkout.")
    subparsers.add_parser("identifiability", help="Audit whether preserved Strong/HNG reader pairs had distinct inputs.")
    subparsers.add_parser("policy-differential", help="Run the unlabeled HNG/Strong development policy grid.")
    million = subparsers.add_parser("million-write", help="Prepare or run the preregistered million-write reliability probe.")
    million.add_argument("--prepare-only", action="store_true")
    million.add_argument("--preregistered-commit")
    sustained = subparsers.add_parser(
        "sustained-reliability",
        help="Prepare or run the preregistered two-hour reliability probe.",
    )
    sustained.add_argument("--prepare-only", action="store_true")
    sustained.add_argument("--preregistered-commit")
    sustained_v2 = subparsers.add_parser(
        "sustained-reliability-v2",
        help="Prepare or run the failure-driven two-hour recovery v2.",
    )
    sustained_v2.add_argument("--prepare-only", action="store_true")
    sustained_v2.add_argument("--preregistered-commit")
    handle_observer = subparsers.add_parser(
        "handle-observer-diagnostic",
        help="Prepare or run the attribution-only child-handle diagnostic.",
    )
    handle_observer.add_argument("--prepare-only", action="store_true")
    handle_observer.add_argument("--preregistered-commit")
    handle_observer_v2 = subparsers.add_parser(
        "handle-observer-diagnostic-v2",
        help="Prepare or run the timing-corrected attribution diagnostic.",
    )
    handle_observer_v2.add_argument("--prepare-only", action="store_true")
    handle_observer_v2.add_argument("--preregistered-commit")
    rag = subparsers.add_parser("rag-governance", help="Reproduce fixed-candidate governance results.")
    rag.add_argument("--execute-llm", action="store_true", help="Run the costly local 27B holdout.")
    rag.add_argument("--llm-limit", type=int, default=30)
    public = subparsers.add_parser("public-memory", help="Prepare or execute the public text pilot.")
    public.add_argument("--execute-llm", action="store_true", help="Run all local reader/judge calls.")
    subparsers.add_parser("belief-revision", help="Reproduce the synthetic belief-revision component study.")
    subparsers.add_parser("component-probes", help="Reproduce all packaged synthetic component studies.")
    subparsers.add_parser("scaled-isolation", help="Run the 100,000-principal scoped isolation probe.")
    subparsers.add_parser("tool-agent", help="Run the executing synthetic tool-agent advisory study.")
    hdc = subparsers.add_parser("real-hdc", help="Verify prerequisites for a real HDC assistant paired A/B.")
    hdc.add_argument("--manifest", type=Path, help="Manifest describing and hashing every real-assistant artifact.")
    latency = subparsers.add_parser("latency", help="Run repeated synthetic decision-latency measurements.")
    latency.add_argument("--repeats", type=int, default=20)
    budget = subparsers.add_parser("retrieval-budget", help="Prepare or run the disjoint LoCoMo retrieval-budget holdout.")
    budget.add_argument("--execute-llm", action="store_true", help="Run the costly local reader/judge calls.")
    hybrid = subparsers.add_parser("hybrid-holdout", help="Prepare or run the disjoint LoCoMo dense/hybrid holdout.")
    hybrid.add_argument("--execute-llm", action="store_true", help="Run the costly local reader/judge calls.")
    reranker = subparsers.add_parser("reranker-holdout", help="Prepare or run the disjoint LoCoMo neural-reranker holdout.")
    reranker.add_argument("--execute-llm", action="store_true", help="Run the costly local reader/judge calls.")
    cross = subparsers.add_parser("cross-family", help="Prepare or run the fixed-candidate Mistral reader replication.")
    cross.add_argument("--execute-llm", action="store_true", help="Run the 90 local Mistral holdout calls.")
    cross.add_argument("--preregistered-commit", help="Exact clean commit that froze the cross-family protocol.")
    cross_reader = subparsers.add_parser("cross-reader-holdout", help="Prepare or run the disjoint Qwen/Mistral holdout.")
    cross_reader.add_argument("--execute-llm", action="store_true", help="Run 180 pinned local-reader calls.")
    cross_reader.add_argument("--preregistered-commit", help="Exact clean commit that froze the disjoint protocol.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_commands(commands_for(args), dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
