#!/usr/bin/env python3
"""Executing synthetic tool-agent benchmark using the production advisory adapter.

The same deterministic agent, candidate actions, task stream, tool environment,
mandatory non-memory safety guard, and observation noise are used for every arm.
Only the memory/advisory policy changes. Synthetic HDC vectors are used, so this
cannot satisfy the real-HDC or public-environment gates.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import inspect
import json
import math
import random
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(PACKAGE))

from hngfrontier import (  # noqa: E402
    Decision,
    DeploymentMode,
    EvidenceProvenance,
    GovernedProfile,
    GovernedShadowEvaluator,
    HNGMemory,
    PerspectiveField,
    SemanticState,
    SemanticValue,
    TemporalValidity,
    ToolAction,
    ToolAgentAdapter,
)


SEED = 20260901
SLOTS = 12
ACTIONS = 3
ARMS = (
    "agent_alone",
    "ordinary_recent_memory",
    "strong_structured_memory",
    "hng_advisory",
)
VERSIONS = ("v1", "v2", "v3")
ROLES = ("ic", "senior_ic", "manager", "operator")
AUTHORITIES = {"ic": 1, "senior_ic": 2, "manager": 3, "operator": 2}


def hv(seed: int) -> SemanticValue:
    return SemanticValue.hdc(
        np.random.default_rng(seed).integers(0, 2, 256, dtype=np.uint8)
    )


STATE_VALUES = tuple(hv(1000 + index) for index in range(SLOTS))
ACTION_VALUES = tuple(hv(2000 + index) for index in range(ACTIONS))
NEXT_VALUES = tuple(hv(3000 + index) for index in range(SLOTS))
GOAL = hv(4000)
SEQUENCE = hv(5000)


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def distribution(values: Sequence[float]) -> dict[str, float]:
    return {
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "mean": statistics.mean(values) if values else 0.0,
    }


def stable_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def version_for(episode: int, episodes: int) -> str:
    return VERSIONS[min(len(VERSIONS) - 1, episode * len(VERSIONS) // episodes)]


def identity(slot: int) -> tuple[str, str, str, int]:
    tenant = f"tenant-{slot % 3}"
    user = f"user-{tenant}-{slot:02d}"
    role = ROLES[slot % len(ROLES)]
    return tenant, user, role, AUTHORITIES[role]


def state_for(slot: int, version: str) -> SemanticState:
    return SemanticState(
        {
            "state": STATE_VALUES[slot],
            "goal": GOAL,
            "sequence": SEQUENCE,
            "environment_version": SemanticValue.structured(version),
            "policy_version": SemanticValue.structured("tool-policy-1"),
        }
    )


def correct_action(slot: int, version: str) -> int:
    _, _, role, _ = identity(slot)
    role_shift = ROLES.index(role) % ACTIONS
    return (slot + role_shift + VERSIONS.index(version)) % ACTIONS


def safety_guard_allows(slot: int, version: str, action: int) -> bool:
    expected = correct_action(slot, version)
    backup_ready = slot % 4 != 0 or expected == 2
    return action != 2 or backup_ready


def observation_success(actual_success: bool, episode: int, action: int) -> tuple[bool, str]:
    if actual_success and (episode + action) % 17 == 0:
        return False, "false_negative_tool_observation"
    if not actual_success and (episode + action) % 29 == 0:
        return True, "false_positive_tool_observation"
    return actual_success, "accurate_tool_observation"


@dataclass
class MemoryEvent:
    slot: int
    version: str
    tenant: str
    user: str
    role: str
    action: int
    observed_success: bool


class OrdinaryMemory:
    def __init__(self) -> None:
        self.events: list[MemoryEvent] = []

    def decision(self, slot: int, version: str, tenant: str, user: str, role: str, action: int) -> str:
        matches = [item for item in self.events if item.slot == slot and item.action == action]
        if not matches:
            return "insufficient_evidence"
        return "support" if matches[-1].observed_success else "challenge"

    def observe(self, event: MemoryEvent) -> None:
        self.events.append(event)


class StrongStructuredMemory:
    def __init__(self) -> None:
        self.events: dict[tuple[object, ...], list[MemoryEvent]] = {}

    @staticmethod
    def key(slot: int, version: str, tenant: str, user: str, role: str, action: int) -> tuple[object, ...]:
        return slot, version, tenant, user, role, action

    def decision(self, slot: int, version: str, tenant: str, user: str, role: str, action: int) -> str:
        matches = self.events.get(self.key(slot, version, tenant, user, role, action), [])
        if not matches:
            return "insufficient_evidence"
        positive = sum(item.observed_success for item in matches)
        negative = len(matches) - positive
        if positive and negative:
            return "conflicted"
        return "support" if positive else "challenge"

    def observe(self, event: MemoryEvent) -> None:
        self.events.setdefault(
            self.key(
                event.slot,
                event.version,
                event.tenant,
                event.user,
                event.role,
                event.action,
            ),
            [],
        ).append(event)


def veto(decision: str) -> bool:
    return decision in {
        Decision.CHALLENGE.value,
        Decision.UNTRUSTED_EVIDENCE.value,
        Decision.PROFILE_UNCERTAIN.value,
        Decision.INSUFFICIENT_STATE.value,
    }


def exact_binomial_two_sided(discordant_a: int, discordant_b: int) -> float:
    total = discordant_a + discordant_b
    if not total:
        return 1.0
    low = min(discordant_a, discordant_b)
    tail = sum(math.comb(total, index) for index in range(low + 1)) / (2**total)
    return min(1.0, 2.0 * tail)


def paired_statistics(
    events: list[dict[str, Any]], left: str, right: str, episodes: int
) -> dict[str, object]:
    left_rows = {
        int(row["episode"]): bool(row["task_success"])
        for row in events
        if row["arm"] == left
    }
    right_rows = {
        int(row["episode"]): bool(row["task_success"])
        for row in events
        if row["arm"] == right
    }
    left_only = sum(left_rows[index] and not right_rows[index] for index in range(episodes))
    right_only = sum(right_rows[index] and not left_rows[index] for index in range(episodes))
    rng = random.Random(SEED)
    deltas = []
    for _ in range(10_000):
        sample = [rng.randrange(episodes) for _ in range(episodes)]
        deltas.append(
            statistics.mean(left_rows[index] for index in sample)
            - statistics.mean(right_rows[index] for index in sample)
        )
    deltas.sort()
    return {
        "left": left,
        "right": right,
        "accuracy_delta": statistics.mean(left_rows.values())
        - statistics.mean(right_rows.values()),
        "mcnemar": {
            "left_only": left_only,
            "right_only": right_only,
            "exact_two_sided_p": exact_binomial_two_sided(left_only, right_only),
        },
        "paired_bootstrap_95_ci": [
            deltas[int(0.025 * len(deltas))],
            deltas[int(0.975 * len(deltas)) - 1],
        ],
    }


def summarize(events: list[dict[str, Any]], episodes: int) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for arm in ARMS:
        rows = [row for row in events if row["arm"] == arm]
        seen_failures: set[tuple[object, ...]] = set()
        repeated_failures = 0
        prior_failure: dict[tuple[object, ...], bool] = {}
        recovery_opportunities = 0
        recoveries = 0
        for row in rows:
            key = (row["slot"], row["version"], row["role"])
            action_key = (*key, row["action"])
            if prior_failure.get(key):
                recovery_opportunities += 1
                recoveries += int(bool(row["task_success"]))
                prior_failure[key] = False
            if not row["task_success"]:
                repeated_failures += int(action_key in seen_failures)
                seen_failures.add(action_key)
                prior_failure[key] = True
        output[arm] = {
            "episodes": len(rows),
            "task_successes": sum(bool(row["task_success"]) for row in rows),
            "task_success_rate": statistics.mean(bool(row["task_success"]) for row in rows),
            "wrong_action_rate": statistics.mean(not bool(row["task_success"]) for row in rows),
            "repeated_tool_failures": repeated_failures,
            "irreversible_mistakes": sum(bool(row["irreversible_mistake"]) for row in rows),
            "mandatory_guard_blocks": sum(int(row["guard_blocks"]) for row in rows),
            "advisory_warnings": sum(bool(row["advisory_warning"]) for row in rows),
            "useful_interventions": sum(bool(row["useful_intervention"]) for row in rows),
            "incorrect_challenges": sum(bool(row["incorrect_challenge"]) for row in rows),
            "ignored_challenges": sum(bool(row["ignored_challenge"]) for row in rows),
            "recovery_opportunities": recovery_opportunities,
            "recoveries": recoveries,
            "recovery_rate": (
                recoveries / recovery_opportunities if recovery_opportunities else 0.0
            ),
            "decision_latency_ms": distribution(
                [float(row["decision_latency_ms"]) for row in rows]
            ),
            "conflicting_observations": sum(
                row["observation_kind"] != "accurate_tool_observation" for row in rows
            ),
        }
    return output


def run(episodes: int = 108, protocol_label: str = "current") -> dict[str, Any]:
    if episodes <= 0 or episodes % (SLOTS * len(VERSIONS)):
        raise ValueError("episodes must be a positive multiple of 36")

    ordinary = OrdinaryMemory()
    strong = StrongStructuredMemory()
    events: list[dict[str, Any]] = []
    candidate_hashes: dict[int, set[str]] = {}
    execute_parameters = inspect.signature(ToolAgentAdapter.execute).parameters
    contextual_adapter = "validity" in execute_parameters

    with tempfile.TemporaryDirectory(prefix="hng-tool-agent-") as directory:
        root = Path(directory)
        memory = HNGMemory(root / "memory", semantic_backend="reference-hng")
        rollout = GovernedShadowEvaluator(
            root / "hng-rollout.jsonl", mode=DeploymentMode.ADVISORY_CHALLENGE
        )
        adapter = ToolAgentAdapter(memory, rollout)
        try:
            for slot in range(SLOTS):
                tenant, user, role, authority = identity(slot)
                memory.set_profile(
                    GovernedProfile(
                        user,
                        tenant,
                        {
                            "role": PerspectiveField(
                                role, 1.0, "system_identity", user_confirmed=True
                            ),
                            "authority_level": PerspectiveField(
                                authority, 1.0, "system_identity", user_confirmed=True
                            ),
                            "abstraction_level": PerspectiveField(
                                2, 1.0, "system_identity", user_confirmed=True
                            ),
                        },
                    )
                )
                memory.activate_profile(f"tool-session-{slot:02d}", user)

            for episode in range(episodes):
                slot = episode % SLOTS
                version = version_for(episode, episodes)
                tenant, user, role, authority = identity(slot)
                expected = correct_action(slot, version)
                candidates = [
                    {
                        "action": action,
                        "tool": "state_mutator",
                        "name": ("legacy_mutate", "versioned_mutate", "destructive_reconcile")[
                            action
                        ],
                        "arguments": {
                            "slot": slot,
                            "environment_version": version,
                            "tenant": tenant,
                            "user": user,
                            "role": role,
                        },
                    }
                    for action in range(ACTIONS)
                ]
                candidate_hash = stable_hash(candidates)
                candidate_hashes.setdefault(episode, set())

                for arm in ARMS:
                    candidate_hashes[episode].add(candidate_hash)
                    started = time.perf_counter()
                    decisions: dict[int, str] = {}
                    frames: dict[int, object] = {}
                    if arm == "hng_advisory":
                        for action in range(ACTIONS):
                            proposal = ToolAction(
                                "state_mutator",
                                str(candidates[action]["name"]),
                                ACTION_VALUES[action],
                                dict(candidates[action]["arguments"]),
                            )
                            assessment = adapter.assess(
                                proposal,
                                conversation_id=f"tool-session-{slot:02d}",
                                state=state_for(slot, version),
                            )
                            decisions[action] = assessment.frame.assessment.decision.value
                            frames[action] = assessment.frame
                    elif arm == "ordinary_recent_memory":
                        for action in range(ACTIONS):
                            decisions[action] = ordinary.decision(
                                slot, version, tenant, user, role, action
                            )
                    elif arm == "strong_structured_memory":
                        for action in range(ACTIONS):
                            decisions[action] = strong.decision(
                                slot, version, tenant, user, role, action
                            )
                    else:
                        decisions = {action: "not_consulted" for action in range(ACTIONS)}

                    guard_blocks = 0
                    selected = None
                    challenged = []
                    for action in range(ACTIONS):
                        if not safety_guard_allows(slot, version, action):
                            guard_blocks += 1
                            continue
                        if arm != "agent_alone" and veto(decisions[action]):
                            challenged.append(action)
                            continue
                        selected = action
                        break
                    ignored_challenge = False
                    if selected is None:
                        allowed = [
                            action
                            for action in range(ACTIONS)
                            if safety_guard_allows(slot, version, action)
                        ]
                        selected = allowed[-1]
                        ignored_challenge = selected in challenged
                    decision_latency = (time.perf_counter() - started) * 1000.0

                    actual_success = selected == expected
                    observed_success, observation_kind = observation_success(
                        actual_success, episode, selected
                    )
                    irreversible = (
                        selected == 2
                        and not actual_success
                        and safety_guard_allows(slot, version, selected)
                    )
                    result = {
                        "success": observed_success,
                        "actual_success": actual_success,
                        "irreversible": irreversible,
                        "slot": slot,
                        "version": version,
                        "action": selected,
                        "observation_kind": observation_kind,
                    }

                    if arm == "hng_advisory":
                        proposal = ToolAction(
                            "state_mutator",
                            str(candidates[selected]["name"]),
                            ACTION_VALUES[selected],
                            dict(candidates[selected]["arguments"]),
                        )
                        kwargs: dict[str, object] = {}
                        if contextual_adapter:
                            kwargs.update(
                                {
                                    "validity": TemporalValidity(
                                        environment_version=version,
                                        policy_version="tool-policy-1",
                                    ),
                                    "tenant_id": tenant,
                                    "user_id": user,
                                    "scope": "private",
                                    "role": role,
                                    "authority_level": authority,
                                    "abstraction_level": 2,
                                }
                            )
                        adapter.execute(
                            proposal,
                            conversation_id=f"tool-session-{slot:02d}",
                            state=state_for(slot, version),
                            executor=lambda _action, _arguments, payload=result: dict(payload),
                            outcome_semantics=lambda _result, current_slot=slot: NEXT_VALUES[
                                current_slot
                            ],
                            provenance=EvidenceProvenance(
                                "system_telemetry",
                                f"tool-event-{episode:04d}",
                                1.0,
                                True,
                                verifier="tool-agent-advisory-probe",
                                verification_status="verified",
                                identity="synthetic-tool-environment",
                            ),
                            **kwargs,
                        )
                    elif arm == "ordinary_recent_memory":
                        ordinary.observe(
                            MemoryEvent(
                                slot,
                                version,
                                tenant,
                                user,
                                role,
                                selected,
                                observed_success,
                            )
                        )
                    elif arm == "strong_structured_memory":
                        strong.observe(
                            MemoryEvent(
                                slot,
                                version,
                                tenant,
                                user,
                                role,
                                selected,
                                observed_success,
                            )
                        )

                    default_challenged = 0 in challenged
                    event = {
                        "schema_version": 1,
                        "protocol_label": protocol_label,
                        "episode": episode,
                        "arm": arm,
                        "slot": slot,
                        "version": version,
                        "tenant": tenant,
                        "user": user,
                        "role": role,
                        "candidate_pool_sha256": candidate_hash,
                        "candidate_actions": candidates,
                        "oracle_action": expected,
                        "action": selected,
                        "task_success": actual_success,
                        "observed_success": observed_success,
                        "observation_kind": observation_kind,
                        "irreversible_mistake": irreversible,
                        "guard_blocks": guard_blocks,
                        "advisory_warning": bool(challenged),
                        "useful_intervention": default_challenged and expected != 0,
                        "incorrect_challenge": default_challenged and expected == 0,
                        "ignored_challenge": ignored_challenge,
                        "decisions": {str(key): value for key, value in decisions.items()},
                        "selected_hng_trace": (
                            frames[selected].assessment.as_dict()
                            if arm == "hng_advisory" and selected in frames
                            else None
                        ),
                        "decision_latency_ms": decision_latency,
                    }
                    events.append(event)
        finally:
            memory.close()

    invariants = {
        "candidate_pool_identical_across_arms": all(
            len(values) == 1 for values in candidate_hashes.values()
        ),
        "same_episode_count_per_arm": all(
            sum(row["arm"] == arm for row in events) == episodes for arm in ARMS
        ),
        "hard_gate_disabled": True,
        "mandatory_guard_shared": True,
        "weights_changed": False,
    }
    summaries = summarize(events, episodes)
    return {
        "schema_version": 1,
        "benchmark": "synthetic_executing_tool_agent_advisory_probe",
        "status": "complete",
        "protocol_label": protocol_label,
        "seed": SEED,
        "episodes": episodes,
        "arms": list(ARMS),
        "adapter_outcome_context_mode": (
            "contextual_versioned" if contextual_adapter else "legacy_unscoped_unversioned"
        ),
        "claim_boundary": (
            "Executing deterministic synthetic tool environment and synthetic HDC vectors; "
            "production ToolAgentAdapter/HNGMemory path; not a public workload, real agent, "
            "security authority, or real-HDC result."
        ),
        "task_features": {
            "state_mutation": True,
            "recoverable_failures": True,
            "irreversible_effects": True,
            "api_version_changes": list(VERSIONS),
            "conflicting_observations": True,
            "role_specific_outcomes": True,
            "mandatory_non_memory_guard": True,
        },
        "invariants": invariants,
        "summaries": summaries,
        "paired_statistics": {
            "hng_vs_ordinary": paired_statistics(
                events, "hng_advisory", "ordinary_recent_memory", episodes
            ),
            "hng_vs_strong": paired_statistics(
                events, "hng_advisory", "strong_structured_memory", episodes
            ),
            "hng_vs_alone": paired_statistics(
                events, "hng_advisory", "agent_alone", episodes
            ),
        },
        "events": events,
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def revision_paths(output: Path, raw_log: Path) -> tuple[Path, Path]:
    if not output.exists() and not raw_log.exists():
        return output, raw_log
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    revised_output = output.with_name(f"{output.stem}.{stamp}{output.suffix}")
    revised_raw = raw_log.with_name(f"{raw_log.stem}.{stamp}{raw_log.suffix}")
    if revised_output.exists() or revised_raw.exists():
        raise FileExistsError("Timestamped tool-agent evidence path already exists")
    return revised_output, revised_raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=108)
    parser.add_argument("--protocol-label", default="current")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "breakthrough_eval" / "tool_agent" / "RESULTS.json",
    )
    parser.add_argument(
        "--raw-log",
        type=Path,
        default=ROOT / "breakthrough_eval" / "tool_agent" / "raw" / "events.jsonl",
    )
    args = parser.parse_args()
    output, raw_log = revision_paths(args.output, args.raw_log)
    result = run(args.episodes, args.protocol_label)
    raw_log.parent.mkdir(parents=True, exist_ok=True)
    with raw_log.open("x", encoding="utf-8") as handle:
        for event in result["events"]:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    result["raw_log"] = raw_log.resolve().relative_to(ROOT).as_posix()
    result["event_count"] = len(result["events"])
    del result["events"]
    write_json(output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "adapter_outcome_context_mode": result["adapter_outcome_context_mode"],
                "output": output.resolve().relative_to(ROOT).as_posix(),
                "raw_log": result["raw_log"],
                "summaries": result["summaries"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
