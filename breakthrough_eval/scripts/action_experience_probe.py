#!/usr/bin/env python3
"""Synthetic state+action->outcome and cross-session accumulation probe.

The simulator executes actions and records outcomes. It uses deterministic
synthetic vectors and therefore cannot satisfy the real-HDC or public benchmark
gates. The HNG arm calls the shipped HNGMemory action evaluator and store.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(PACKAGE))

from hngfrontier import (  # noqa: E402
    Decision,
    EvidenceKind,
    EvidenceProvenance,
    HNGMemory,
    SemanticState,
    SemanticValue,
    TemporalValidity,
)


SEED = 20260831
STATES = 10
ACTIONS = 4
ARMS = (
    "semantic_action_router",
    "nearest_neighbor_experience",
    "weighted_multi_vector",
    "structured_database",
    "graph_memory",
    "strong_structured",
    "hng_governed_transitions",
)


def hv(seed: int) -> SemanticValue:
    return SemanticValue.hdc(np.random.default_rng(seed).integers(0, 2, 256, dtype=np.uint8))


STATE_VALUES = tuple(hv(1000 + index) for index in range(STATES))
ACTION_VALUES = tuple(hv(2000 + index) for index in range(ACTIONS))
GOAL = hv(3000)
SEQUENCE = hv(4000)


def semantic_state(state_index: int, environment: str) -> SemanticState:
    return SemanticState({
        "state": STATE_VALUES[state_index],
        "goal": GOAL,
        "sequence": SEQUENCE,
        "environment_version": SemanticValue.structured(environment),
    })


def oracle_action(state_index: int, environment: str) -> int:
    shift = 1 if environment == "v1" else 2
    return (state_index + shift) % ACTIONS


class HistoryPolicy:
    def __init__(self, mode: str):
        self.mode = mode
        self.events: list[dict[str, Any]] = []

    def choose(self, state: int, environment: str) -> tuple[int, bool, str]:
        if self.mode == "semantic":
            return 0, False, "fixed semantic-theory action"
        matches = [event for event in self.events if event["state"] == state]
        if self.mode != "nearest":
            matches = [event for event in matches if event["environment"] == environment]
        if not matches:
            return 0, True, "no applicable experience"
        if self.mode in {"nearest", "weighted"}:
            latest = matches[-1]
            if latest["success"]:
                return int(latest["action"]), False, "repeat latest successful experience"
            return (int(latest["action"]) + 1) % ACTIONS, False, "advance after latest failure"
        successful = [event for event in matches if event["success"]]
        if successful:
            return int(successful[-1]["action"]), False, "reuse successful structured transition"
        tried = {int(event["action"]) for event in matches}
        for action in range(ACTIONS):
            if action not in tried:
                return action, False, "explore action without recorded outcome"
        return 0, True, "all known actions failed"

    def observe(self, event: dict[str, Any]) -> None:
        self.events.append(dict(event))


class HNGPolicy:
    def __init__(self, root: Path):
        self.memory = HNGMemory(root, semantic_backend="reference-hng")

    def choose(self, state: int, environment: str) -> tuple[int, bool, str, dict[str, str]]:
        query = semantic_state(state, environment)
        decisions = {}
        frames = {}
        for action in range(ACTIONS):
            frame = self.memory.evaluate_action(
                query, ACTION_VALUES[action], conversation_id="action-experience"
            )
            frames[action] = frame
            decisions[str(action)] = frame.assessment.decision.value
        supported = [action for action, frame in frames.items() if frame.assessment.decision is Decision.SUPPORT]
        if supported:
            return supported[0], False, "reuse governed supported transition", decisions
        eligible = [action for action, frame in frames.items() if frame.assessment.decision is not Decision.CHALLENGE]
        if eligible:
            return eligible[0], True, "no supported action; abstain then deterministic exploration", decisions
        return 0, True, "all candidate actions challenged", decisions

    def observe(self, event: dict[str, Any]) -> None:
        state = semantic_state(int(event["state"]), str(event["environment"]))
        action = int(event["action"])
        event_id = f"hng-action-{event['attempt']:04d}"
        self.memory.ingest_evidence(
            content=f"state={event['state']} action={action} outcome={'success' if event['success'] else 'failure'}",
            semantics=state.merged({"action": ACTION_VALUES[action]}),
            provenance=EvidenceProvenance("system_telemetry", event_id, 1.0, True),
            kind=EvidenceKind.OUTCOME,
            outcome_score=1.0 if event["success"] else -1.0,
            confidence=1.0,
            experience_id=event_id,
            source_event_id=event_id,
            evidence_group_id=event_id,
            validity=TemporalValidity(environment_version=str(event["environment"])),
            metadata={"action_label": str(action), "simulator_seed": SEED},
        )

    def close(self) -> None:
        self.memory.close()


def summarize(events: list[dict[str, Any]], attempts: int) -> dict[str, Any]:
    summaries = {}
    for arm in ARMS:
        rows = [event for event in events if event["arm"] == arm]
        failures_seen: set[tuple[int, str, int]] = set()
        repeated_failures = 0
        first_success_failures: dict[tuple[int, str], int] = {}
        failures_before_success: dict[tuple[int, str], int] = {}
        previously_supported: set[tuple[int, str]] = set()
        abstention_opportunities = 0
        correct_abstentions = 0
        for row in rows:
            key = (int(row["state"]), str(row["environment"]))
            if key not in previously_supported:
                abstention_opportunities += 1
                correct_abstentions += int(bool(row["abstained"]))
            failure_key = (*key, int(row["action"]))
            if not row["success"]:
                repeated_failures += int(failure_key in failures_seen)
                failures_seen.add(failure_key)
                failures_before_success[key] = failures_before_success.get(key, 0) + 1
            elif key not in first_success_failures:
                first_success_failures[key] = failures_before_success.get(key, 0)
                previously_supported.add(key)
        bins = []
        width = 20
        for start in range(0, attempts, width):
            selected = [row for row in rows if start <= int(row["attempt"]) < min(start + width, attempts)]
            bins.append({
                "attempt_start": start + 1,
                "attempt_end": min(start + width, attempts),
                "success_rate": statistics.mean(bool(row["success"]) for row in selected),
            })
        summaries[arm] = {
            "attempts": len(rows),
            "successes": sum(bool(row["success"]) for row in rows),
            "action_success_rate": statistics.mean(bool(row["success"]) for row in rows),
            "action_regret": sum(not bool(row["success"]) for row in rows),
            "repeated_failure_count": repeated_failures,
            "abstention_count": sum(bool(row["abstained"]) for row in rows),
            "correct_abstention_count": correct_abstentions,
            "abstention_opportunity_count": abstention_opportunities,
            "correct_abstention_coverage": correct_abstentions / abstention_opportunities,
            "solved_state_environments": len(first_success_failures),
            "unsolved_state_environments": STATES * 2 - len(first_success_failures),
            "first_success_failure_count_mean": statistics.mean(first_success_failures.values()),
            "performance_curve": bins,
        }
    return summaries


def run(attempts: int = 100) -> dict[str, Any]:
    if attempts <= 0 or attempts % 20:
        raise ValueError("attempts must be a positive multiple of 20")
    policies = {
        "semantic_action_router": HistoryPolicy("semantic"),
        "nearest_neighbor_experience": HistoryPolicy("nearest"),
        "weighted_multi_vector": HistoryPolicy("weighted"),
        "structured_database": HistoryPolicy("structured"),
        "graph_memory": HistoryPolicy("structured"),
        "strong_structured": HistoryPolicy("structured"),
    }
    events = []
    with tempfile.TemporaryDirectory(prefix="hng-action-experience-") as directory:
        hng = HNGPolicy(Path(directory))
        try:
            for attempt in range(attempts):
                state = attempt % STATES
                environment = "v1" if attempt < attempts // 2 else "v2"
                expected = oracle_action(state, environment)
                for arm in ARMS:
                    trace: dict[str, str] = {}
                    if arm == "hng_governed_transitions":
                        action, abstained, reason, trace = hng.choose(state, environment)
                    else:
                        action, abstained, reason = policies[arm].choose(state, environment)
                    event = {
                        "attempt": attempt,
                        "arm": arm,
                        "state": state,
                        "environment": environment,
                        "action": action,
                        "oracle_action": expected,
                        "success": action == expected,
                        "abstained": abstained,
                        "reason": reason,
                        "hng_decisions": trace,
                    }
                    events.append(event)
                    if arm == "hng_governed_transitions":
                        hng.observe(event)
                    else:
                        policies[arm].observe(event)
        finally:
            hng.close()
    summaries = summarize(events, attempts)
    strong = summaries["strong_structured"]
    hng_summary = summaries["hng_governed_transitions"]
    return {
        "schema_version": 1,
        "benchmark": "synthetic_executing_action_experience_probe",
        "status": "PASS",
        "claim_boundary": (
            "deterministic synthetic action simulator with synthetic binary vectors; production HNG store/evaluator; "
            "not a public benchmark, real assistant, or real-HDC result"
        ),
        "seed": SEED,
        "attempts": attempts,
        "model_weights_changed": False,
        "environment_change_attempt": attempts // 2 + 1,
        "summaries": summaries,
        "hng_vs_strong": {
            "success_rate_delta": hng_summary["action_success_rate"] - strong["action_success_rate"],
            "regret_delta": hng_summary["action_regret"] - strong["action_regret"],
            "interpretation": "tie if both deltas are zero; simpler baseline preferred on equal behavior",
        },
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=100)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "breakthrough_eval" / "action_experience" / "RESULTS.json",
    )
    args = parser.parse_args()
    result = run(args.attempts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "summaries": result["summaries"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
