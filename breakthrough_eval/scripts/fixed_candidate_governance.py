"""Fixed-candidate evidence-governance benchmark.

This benchmark deliberately generates synthetic evidence. It is not a public benchmark and is
not a real-assistant result. Every system receives the same ordered candidate pool and metadata.
The HNG path calls the production 0.7 EvidenceAggregator. StrongStructuredBaseline is an
independent, ordinary typed-filter implementation with the same information and policy budget.

Optional LLM evaluation uses one frozen Ollama model and one prompt template. Only the rendered
memory context changes. Raw outputs are append-only JSONL event logs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(PACKAGE))

from hngfrontier.aggregation import EvidenceAggregator  # noqa: E402
from hngfrontier.governance import (  # noqa: E402
    Decision,
    EvidenceKind,
    EvidenceProvenance,
    EvidenceRecordV2,
    TemporalValidity,
)
from hngfrontier.profiles import EffectiveProfile, PerspectiveField  # noqa: E402
from hngfrontier.query_planner import QueryIntent, QueryPlanV2  # noqa: E402
from hngfrontier.semantic import EvidenceRequirement, SemanticState, SemanticValue  # noqa: E402

SCHEMA_VERSION = 1
SEED = 20260831
NOW = "2026-08-31T12:00:00+00:00"
DEFAULT_MODEL = "qwen3.8:27b-q4_K_M"
DEFAULT_DIGEST = "25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e"
DECISION_VALUES = ("support", "challenge", "conflicted", "insufficient_evidence")

TRUST_SOURCE = {
    "system_telemetry": 1.0,
    "authoritative_database": 1.0,
    "human_confirmed": 0.95,
    "tool_result": 0.90,
    "external_document": 0.75,
    "user_assertion": 0.65,
    "model_inference": 0.35,
    "unverified_text": 0.25,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def structured_state(state: str, goal: str, sequence: str, action: str, environment: str) -> SemanticState:
    return SemanticState({
        "state": SemanticValue.structured(state),
        "goal": SemanticValue.structured(goal),
        "sequence": SemanticValue.structured(sequence),
        "action": SemanticValue.structured(action),
        "environment_version": SemanticValue.structured(environment),
    })


def profile(tenant: str = "tenant-a", role: str = "ic", authority: int = 2) -> EffectiveProfile:
    confirmed = dict(confidence=1.0, source="system_identity", user_confirmed=True)
    return EffectiveProfile(
        "user-a",
        tenant,
        {
            "role": PerspectiveField(role, **confirmed),
            "authority_level": PerspectiveField(authority, **confirmed),
        },
        1,
    )


@dataclass(frozen=True)
class Scenario:
    case_id: str
    family: str
    split: str
    query: SemanticState
    actor: EffectiveProfile
    candidates: tuple[EvidenceRecordV2, ...]
    expected: str

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(item.experience_id for item in self.candidates)

    @property
    def candidate_pool_sha256(self) -> str:
        return stable_hash([record_payload(item) for item in self.candidates])


def record_payload(record: EvidenceRecordV2) -> dict[str, object]:
    return {
        "id": record.experience_id,
        "event": record.source_event_id,
        "content": record.content,
        "outcome": record.outcome_score,
        "tenant": record.tenant_id,
        "user": record.user_id,
        "scope": record.scope,
        "role": record.role,
        "authority": record.authority_level,
        "source_type": record.provenance.source_type,
        "source_id": record.provenance.source_id,
        "trust": record.provenance.trust_score,
        "verified": record.provenance.verified,
        "verification_status": record.provenance.verification_status,
        "validity": record.validity.as_dict(),
        "superseded_by": record.superseded_by,
        "invalidated_at": record.invalidated_at,
        "semantics": {
            name: value.value
            for name, value in record.semantics.fields.items()
            if value.kind.value == "structured"
        },
    }


def make_record(
    case_id: str,
    index: int,
    *,
    outcome: int,
    event: str,
    state: str,
    goal: str,
    sequence: str,
    action: str,
    environment: str,
    tenant: str = "tenant-a",
    role: str = "ic",
    authority: int = 2,
    source_type: str = "system_telemetry",
    trust: float = 1.0,
    verified: bool = True,
    superseded_by: str | None = None,
    valid_until: str | None = None,
) -> EvidenceRecordV2:
    label = "succeeded" if outcome > 0 else "failed" if outcome < 0 else "was inconclusive"
    experience_id = f"{case_id}-e{index:02d}"
    return EvidenceRecordV2(
        experience_id=experience_id,
        evidence_group_id=event,
        source_event_id=event,
        episode_id=f"{case_id}-episode",
        conversation_id=f"{case_id}-conversation",
        kind=EvidenceKind.OUTCOME,
        content=f"Action {action} {label} in {environment}.",
        semantics=structured_state(state, goal, sequence, action, environment),
        provenance=EvidenceProvenance(
            source_type,
            f"{source_type}:{event}",
            trust,
            verified,
            NOW,
            "actor",
            verification_status="verified" if verified else "unverified",
            identity="benchmark-source",
            verifier="benchmark-fixture" if verified else "",
        ),
        validity=TemporalValidity(
            valid_from="2026-01-01T00:00:00+00:00",
            valid_until=valid_until,
            environment_version=environment,
        ),
        outcome_score=float(outcome),
        confidence=1.0,
        tenant_id=tenant,
        user_id="user-a" if tenant == "tenant-a" else "other-user",
        scope="tenant",
        role=role,
        authority_level=authority,
        profile_revision=1,
        superseded_by=superseded_by,
    )


def generate_scenarios() -> tuple[Scenario, ...]:
    rng = random.Random(SEED)
    scenarios: list[Scenario] = []
    families = (
        "duplicate_attack",
        "stale_environment",
        "wrong_tenant",
        "wrong_role",
        "untrusted_poison",
        "superseded",
        "true_conflict",
        "irrelevant_state",
        "sparse_verified",
        "authority_mismatch",
    )
    for variant in range(25):
        for family_index, family in enumerate(families):
            case_id = f"{family}-{variant:02d}"
            state = f"service-{variant % 5}"
            goal = f"restore-{variant % 3}"
            sequence = f"step-{variant % 4}"
            action = f"action-{variant % 7}"
            env = f"v{2 + variant % 2}"
            query = structured_state(state, goal, sequence, action, env)
            actor = profile()
            rows: list[EvidenceRecordV2] = []

            def add(count: int = 1, **kwargs) -> None:
                for _ in range(count):
                    values = dict(kwargs)
                    rows.append(make_record(
                        case_id,
                        len(rows),
                        state=values.pop("state", state),
                        goal=values.pop("goal", goal),
                        sequence=values.pop("sequence", sequence),
                        action=values.pop("action", action),
                        environment=values.pop("environment", env),
                        **values,
                    ))

            if family == "duplicate_attack":
                add(6, outcome=1, event=f"{case_id}-copied-event")
                add(1, outcome=-1, event=f"{case_id}-failure-a")
                add(1, outcome=-1, event=f"{case_id}-failure-b")
                expected = Decision.CHALLENGE.value
            elif family == "stale_environment":
                add(5, outcome=1, event=f"{case_id}-old", environment="v1")
                add(1, outcome=-1, event=f"{case_id}-current-failure")
                expected = Decision.CHALLENGE.value
            elif family == "wrong_tenant":
                add(5, outcome=1, event=f"{case_id}-other", tenant="tenant-b")
                add(1, outcome=-1, event=f"{case_id}-local-failure")
                expected = Decision.CHALLENGE.value
            elif family == "wrong_role":
                add(5, outcome=1, event=f"{case_id}-manager", role="manager")
                add(1, outcome=-1, event=f"{case_id}-ic-failure")
                expected = Decision.CHALLENGE.value
            elif family == "untrusted_poison":
                for poison in range(6):
                    add(
                        1,
                        outcome=1,
                        event=f"{case_id}-poison-{poison}",
                        source_type="model_inference",
                        trust=0.99,
                        verified=False,
                    )
                add(1, outcome=-1, event=f"{case_id}-telemetry-failure")
                expected = Decision.CHALLENGE.value
            elif family == "superseded":
                add(5, outcome=1, event=f"{case_id}-old", superseded_by=f"{case_id}-new")
                add(1, outcome=-1, event=f"{case_id}-new")
                expected = Decision.CHALLENGE.value
            elif family == "true_conflict":
                add(1, outcome=1, event=f"{case_id}-support-a")
                add(1, outcome=1, event=f"{case_id}-support-b")
                add(1, outcome=-1, event=f"{case_id}-challenge-a")
                add(1, outcome=-1, event=f"{case_id}-challenge-b")
                expected = Decision.CONFLICTED.value
            elif family == "irrelevant_state":
                add(4, outcome=1, event=f"{case_id}-other", state=f"other-{state}")
                expected = Decision.INSUFFICIENT_EVIDENCE.value
            elif family == "sparse_verified":
                add(1, outcome=1, event=f"{case_id}-verified")
                for poison in range(6):
                    add(
                        1,
                        outcome=-1,
                        event=f"{case_id}-rumor-{poison}",
                        source_type="unverified_text",
                        trust=1.0,
                        verified=False,
                    )
                expected = Decision.SUPPORT.value
            else:
                add(5, outcome=1, event=f"{case_id}-admin", authority=4)
                add(1, outcome=-1, event=f"{case_id}-local")
                expected = Decision.CHALLENGE.value

            rng.shuffle(rows)
            split = "development" if variant < 5 else "holdout"
            scenarios.append(Scenario(case_id, family, split, query, actor, tuple(rows), expected))
    return tuple(scenarios)


PLAN = QueryPlanV2(
    QueryIntent.ACTION_EVALUATION,
    EvidenceRequirement(
        ("state", "goal", "sequence", "action"),
        min_similarity={"state": 1.0, "goal": 1.0, "sequence": 1.0, "action": 1.0},
        strict_action_floor=1.0,
    ),
    critical=False,
)


def hng_decide(scenario: Scenario) -> dict[str, object]:
    assessment = EvidenceAggregator().assess(
        scenario.candidates,
        scenario.query,
        PLAN,
        profile=scenario.actor,
        now=NOW,
    )
    return {
        "decision": assessment.decision.value,
        "included": [item.record.experience_id for item in assessment.included],
        "excluded": [
            {"id": item.experience_id, "reason": item.reason}
            for item in assessment.excluded
        ],
        "support_score": assessment.support_score,
        "challenge_score": assessment.challenge_score,
        "confidence": decision_confidence(assessment.support_score, assessment.challenge_score),
        "component_ms": dict(assessment.component_ms),
    }


def record_trust(record: EvidenceRecordV2) -> float:
    source = TRUST_SOURCE.get(record.provenance.source_type, 0.40)
    verified_factor = 1.0 if record.provenance.verified else 0.75
    return min(record.provenance.trust_score, source) * verified_factor


def strong_structured_decide(scenario: Scenario) -> dict[str, object]:
    """Independent simple baseline: typed filters + exact equality + event GROUP BY."""
    included: dict[str, tuple[float, EvidenceRecordV2]] = {}
    excluded: list[dict[str, str]] = []
    query_fields = scenario.query.fields
    environment = str(query_fields["environment_version"].value)
    role = str(scenario.actor.value("role"))
    authority = int(scenario.actor.value("authority_level"))
    for record in scenario.candidates:
        reason = ""
        if record.superseded_by is not None:
            reason = "superseded"
        elif record.invalidated_at is not None:
            reason = "invalidated"
        else:
            active, temporal_reason = record.validity.active(
                at=NOW,
                environment_version=environment,
            )
            if not active:
                reason = temporal_reason
        if not reason and record.tenant_id and record.tenant_id != scenario.actor.tenant_id:
            reason = "tenant_mismatch"
        if not reason and record.role and record.role != role:
            reason = "role_mismatch"
        if not reason and record.authority_level is not None and authority < record.authority_level:
            reason = "authority_mismatch"
        if not reason:
            for head in ("state", "goal", "sequence", "action"):
                evidence = record.semantics.fields.get(head)
                query = query_fields.get(head)
                if evidence is None or query is None or evidence.value != query.value:
                    reason = f"exact_mismatch:{head}"
                    break
        trust = record_trust(record)
        minimum = 0.45 if record.provenance.verified else 0.60
        if not reason and trust < minimum:
            reason = "untrusted"
        if reason:
            excluded.append({"id": record.experience_id, "reason": reason})
            continue
        quality = trust * record.confidence * min(1.0, abs(record.outcome_score) or 1.0)
        previous = included.get(record.source_event_id)
        if previous is None or quality > previous[0]:
            if previous is not None:
                excluded.append({"id": previous[1].experience_id, "reason": "duplicate_event"})
            included[record.source_event_id] = (quality, record)
        else:
            excluded.append({"id": record.experience_id, "reason": "duplicate_event"})
    support = sum(quality for quality, record in included.values() if record.outcome_score > 0)
    challenge = sum(quality for quality, record in included.values() if record.outcome_score < 0)
    if support and challenge and min(support, challenge) >= 0.5 * max(support, challenge):
        decision = Decision.CONFLICTED.value
    elif challenge >= 0.60 and challenge > support:
        decision = Decision.CHALLENGE.value
    elif support >= 0.60 and support > challenge:
        decision = Decision.SUPPORT.value
    elif not included:
        decision = Decision.INSUFFICIENT_EVIDENCE.value
    else:
        decision = Decision.INSUFFICIENT_EVIDENCE.value
    return {
        "decision": decision,
        "included": [record.experience_id for _, record in included.values()],
        "excluded": excluded,
        "support_score": support,
        "challenge_score": challenge,
        "confidence": decision_confidence(support, challenge),
        "component_ms": {},
    }


def raw_majority_decide(scenario: Scenario) -> dict[str, object]:
    support = sum(1 for item in scenario.candidates if item.outcome_score > 0)
    challenge = sum(1 for item in scenario.candidates if item.outcome_score < 0)
    if support == challenge and support:
        decision = Decision.CONFLICTED.value
    elif support > challenge:
        decision = Decision.SUPPORT.value
    elif challenge > support:
        decision = Decision.CHALLENGE.value
    else:
        decision = Decision.INSUFFICIENT_EVIDENCE.value
    return {
        "decision": decision,
        "included": list(scenario.candidate_ids),
        "excluded": [],
        "support_score": float(support),
        "challenge_score": float(challenge),
        "confidence": decision_confidence(float(support), float(challenge)),
        "component_ms": {},
    }


def decision_confidence(support: float, challenge: float) -> float:
    total = support + challenge
    if total <= 0:
        return 0.0
    return abs(support - challenge) / total


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


def bootstrap_delta(
    left: Sequence[bool],
    right: Sequence[bool],
    *,
    samples: int = 10000,
    seed: int = SEED,
) -> dict[str, float]:
    if len(left) != len(right) or not left:
        raise ValueError("paired non-empty inputs required")
    rng = random.Random(seed)
    n = len(left)
    observed = statistics.mean(left) - statistics.mean(right)
    draws: list[float] = []
    for _ in range(samples):
        indexes = [rng.randrange(n) for _ in range(n)]
        draws.append(
            statistics.mean(left[index] for index in indexes)
            - statistics.mean(right[index] for index in indexes)
        )
    return {
        "delta": observed,
        "ci95_low": percentile(draws, 0.025),
        "ci95_high": percentile(draws, 0.975),
    }


def exact_binomial_two_sided(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    tail = min(k, n - k)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(tail + 1)) / (2 ** n))


def mcnemar(left: Sequence[bool], right: Sequence[bool]) -> dict[str, object]:
    left_only = sum(a and not b for a, b in zip(left, right))
    right_only = sum(b and not a for a, b in zip(left, right))
    return {
        "left_correct_right_wrong": left_only,
        "right_correct_left_wrong": right_only,
        "discordant": left_only + right_only,
        "exact_two_sided_p": exact_binomial_two_sided(left_only, left_only + right_only),
    }


def calibration(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    buckets = [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0000001)]
    result = []
    for low, high in buckets:
        selected = [row for row in rows if low <= float(row["confidence"]) < high]
        result.append({
            "range": [low, min(high, 1.0)],
            "count": len(selected),
            "mean_confidence": statistics.mean(float(row["confidence"]) for row in selected) if selected else None,
            "accuracy": statistics.mean(bool(row["correct"]) for row in selected) if selected else None,
        })
    return result


def context_for(system: str, scenario: Scenario, result: Mapping[str, object]) -> str:
    if system == "ordinary_rag":
        payload = {
            "candidate_pool": [record_payload(item) for item in scenario.candidates],
            "note": "These are retrieval candidates, not automatically applicable facts.",
        }
    else:
        by_id = {item.experience_id: record_payload(item) for item in scenario.candidates}
        payload = {
            "decision": result["decision"],
            "support_score": result["support_score"],
            "challenge_score": result["challenge_score"],
            "applicable_evidence": [by_id[item] for item in result["included"]],
            "excluded_evidence": result["excluded"],
        }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def ollama_decide(
    model: str,
    scenario: Scenario,
    memory_context: str,
    *,
    endpoint: str,
    timeout: float,
) -> tuple[str, dict[str, object]]:
    fields = scenario.query.fields
    task = {
        "state": fields["state"].value,
        "goal": fields["goal"].value,
        "sequence": fields["sequence"].value,
        "action": fields["action"].value,
        "environment_version": fields["environment_version"].value,
        "tenant": scenario.actor.tenant_id,
        "role": scenario.actor.value("role"),
        "authority_level": scenario.actor.value("authority_level"),
    }
    system_prompt = (
        "You are an action advisor. Decide whether historical evidence supports trying the "
        "specified action now. Use only applicable, independent, trusted evidence for the exact "
        "tenant, role, authority, state, goal, sequence, action and environment version. Ignore "
        "duplicates, stale/superseded evidence, wrong actors, and untrusted claims. Return exactly "
        "one decision: support, challenge, conflicted, or insufficient_evidence."
    )
    user_prompt = (
        "CURRENT TASK\n"
        + json.dumps(task, sort_keys=True, separators=(",", ":"))
        + "\nMEMORY CONTEXT\n"
        + memory_context
    )
    request = {
        "model": model,
        "stream": False,
        "think": False,
        "format": {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": list(DECISION_VALUES),
                }
            },
            "required": ["decision"],
        },
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "temperature": 0,
            "seed": SEED,
            "num_predict": 32,
            "num_ctx": 32768,
        },
        "keep_alive": "30m",
    }
    raw = json.dumps(request).encode()
    http_request = urllib.request.Request(
        endpoint.rstrip("/") + "/api/chat",
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(http_request, timeout=timeout) as response:
        payload = json.loads(response.read().decode())
    elapsed = time.perf_counter() - started
    content = payload.get("message", {}).get("content", "")
    parsed = json.loads(content)
    decision = str(parsed["decision"])
    if decision not in DECISION_VALUES:
        raise ValueError(f"unsupported model decision: {decision!r}")
    metadata = {
        "elapsed_seconds": elapsed,
        "prompt_eval_count": payload.get("prompt_eval_count"),
        "eval_count": payload.get("eval_count"),
        "total_duration_ns": payload.get("total_duration"),
        "load_duration_ns": payload.get("load_duration"),
        "raw_response": payload,
        "prompt_sha256": stable_hash({"system": system_prompt, "user": user_prompt}),
        "outer_prompt_template_sha256": stable_hash(system_prompt + "\n{TASK}\n{MEMORY_CONTEXT}"),
    }
    return decision, metadata


def append_jsonl(path: Path, row: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(row), sort_keys=True) + "\n")


def run_deterministic(scenarios: Sequence[Scenario], output: Path) -> dict[str, object]:
    systems = {
        "ordinary_raw_majority": raw_majority_decide,
        "strong_structured": strong_structured_decide,
        "hng": hng_decide,
    }
    event_path = output / "raw" / "deterministic_events.jsonl"
    if event_path.exists():
        raise FileExistsError(f"refusing to overwrite {event_path}")
    rows: list[dict[str, object]] = []
    for scenario in scenarios:
        for system, decide in systems.items():
            started = time.perf_counter()
            result = decide(scenario)
            elapsed_ms = (time.perf_counter() - started) * 1000
            row = {
                "schema_version": SCHEMA_VERSION,
                "event_type": "memory_system_result",
                "evidence_class": "synthetic",
                "case_id": scenario.case_id,
                "family": scenario.family,
                "split": scenario.split,
                "system": system,
                "candidate_ids": list(scenario.candidate_ids),
                "candidate_pool_sha256": scenario.candidate_pool_sha256,
                "candidate_count": len(scenario.candidates),
                "expected": scenario.expected,
                "observed": result["decision"],
                "correct": result["decision"] == scenario.expected,
                "confidence": result["confidence"],
                "included_ids": result["included"],
                "excluded": result["excluded"],
                "support_score": result["support_score"],
                "challenge_score": result["challenge_score"],
                "latency_ms": elapsed_ms,
                "component_ms": result["component_ms"],
                "seed": SEED,
                "generated_at": utc_now(),
            }
            append_jsonl(event_path, row)
            rows.append(row)
    summary: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_class": "synthetic",
        "benchmark": "fixed_candidate_governance_250",
        "scenario_count": len(scenarios),
        "candidate_pool_identity_verified": all(
            len({
                row["candidate_pool_sha256"]
                for row in rows
                if row["case_id"] == scenario.case_id
            }) == 1
            for scenario in scenarios
        ),
        "systems": {},
        "paired_statistics": {},
        "raw_event_log": event_path.relative_to(output).as_posix(),
    }
    correctness: dict[str, list[bool]] = {}
    for system in systems:
        selected = [row for row in rows if row["system"] == system]
        correctness[system] = [bool(row["correct"]) for row in selected]
        latencies = [float(row["latency_ms"]) for row in selected]
        summary["systems"][system] = {
            "correct": sum(correctness[system]),
            "total": len(selected),
            "accuracy": statistics.mean(correctness[system]),
            "latency_ms": {
                "p50": percentile(latencies, 0.50),
                "p95": percentile(latencies, 0.95),
                "p99": percentile(latencies, 0.99),
            },
            "calibration": calibration(selected),
            "by_family": {
                family: statistics.mean(
                    bool(row["correct"]) for row in selected if row["family"] == family
                )
                for family in sorted({str(row["family"]) for row in selected})
            },
        }
    for other in ("ordinary_raw_majority", "strong_structured"):
        key = f"hng_vs_{other}"
        summary["paired_statistics"][key] = {
            "paired_bootstrap_accuracy": bootstrap_delta(correctness["hng"], correctness[other]),
            "mcnemar": mcnemar(correctness["hng"], correctness[other]),
        }
    output.mkdir(parents=True, exist_ok=True)
    (output / "DETERMINISTIC_RESULTS.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def run_llm(
    scenarios: Sequence[Scenario],
    output: Path,
    *,
    model: str,
    model_digest: str,
    endpoint: str,
    timeout: float,
    limit: int,
    protocol: str = "fixed_candidate_llm_holdout",
    preregistered_commit: str | None = None,
    system_orders: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, object]:
    selected_cases = [case for case in scenarios if case.split == "holdout"][:limit]
    event_path = output / "raw" / "llm_events.jsonl"
    completed: set[tuple[str, str]] = set()
    prior_rows: list[dict[str, object]] = []
    if event_path.exists():
        for line in event_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            prior_rows.append(row)
            if row.get("status") == "completed":
                completed.add((str(row["case_id"]), str(row["system"])))
    systems = ("ordinary_rag", "strong_structured", "hng")
    orders = {
        scenario.case_id: tuple(
            system_orders.get(scenario.case_id, systems) if system_orders is not None else systems
        )
        for scenario in selected_cases
    }
    for case_id, order in orders.items():
        if len(order) != len(systems) or set(order) != set(systems):
            raise ValueError(f"invalid system order for {case_id}: {order}")
    for scenario in selected_cases:
        decisions = {
            "ordinary_rag": raw_majority_decide(scenario),
            "strong_structured": strong_structured_decide(scenario),
            "hng": hng_decide(scenario),
        }
        for order_index, system in enumerate(orders[scenario.case_id]):
            if (scenario.case_id, system) in completed:
                continue
            context = context_for(system, scenario, decisions[system])
            base = {
                "schema_version": SCHEMA_VERSION,
                "event_type": "llm_memory_system_result",
                "protocol": protocol,
                "preregistered_commit": preregistered_commit,
                "evidence_class": "synthetic",
                "case_id": scenario.case_id,
                "family": scenario.family,
                "split": scenario.split,
                "system": system,
                "system_order": list(orders[scenario.case_id]),
                "execution_order_index": order_index,
                "candidate_ids": list(scenario.candidate_ids),
                "candidate_pool_sha256": scenario.candidate_pool_sha256,
                "candidate_count": len(scenario.candidates),
                "expected": scenario.expected,
                "model": model,
                "model_digest": model_digest,
                "seed": SEED,
                "generation": {"temperature": 0, "num_predict": 32, "num_ctx": 32768},
                "memory_context_sha256": stable_hash(context),
                "memory_context_chars": len(context),
                "generated_at": utc_now(),
            }
            try:
                observed, metadata = ollama_decide(
                    model,
                    scenario,
                    context,
                    endpoint=endpoint,
                    timeout=timeout,
                )
                row = {
                    **base,
                    "status": "completed",
                    "observed": observed,
                    "correct": observed == scenario.expected,
                    "latency_seconds": metadata["elapsed_seconds"],
                    "prompt_eval_count": metadata["prompt_eval_count"],
                    "eval_count": metadata["eval_count"],
                    "total_duration_ns": metadata["total_duration_ns"],
                    "load_duration_ns": metadata["load_duration_ns"],
                    "prompt_sha256": metadata["prompt_sha256"],
                    "outer_prompt_template_sha256": metadata["outer_prompt_template_sha256"],
                    "raw_response": metadata["raw_response"],
                }
            except Exception as error:
                row = {
                    **base,
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            append_jsonl(event_path, row)
    rows = [
        json.loads(line)
        for line in event_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("status") == "completed"
    ]
    summary: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_class": "synthetic",
        "benchmark": "fixed_candidate_llm_holdout",
        "protocol": protocol,
        "preregistered_commit": preregistered_commit,
        "model": model,
        "model_digest": model_digest,
        "requested_cases": len(selected_cases),
        "counterbalanced_system_order": system_orders is not None,
        "candidate_pool_identity_verified": all(
            len({
                row["candidate_pool_sha256"]
                for row in rows
                if row["case_id"] == scenario.case_id
            }) <= 1
            for scenario in selected_cases
        ),
        "systems": {},
        "paired_statistics": {},
        "failed_events": sum(
            json.loads(line).get("status") == "failed"
            for line in event_path.read_text(encoding="utf-8").splitlines()
        ),
        "raw_event_log": event_path.relative_to(output).as_posix(),
    }
    correctness: dict[str, list[bool]] = {}
    case_order = [case.case_id for case in selected_cases]
    for system in systems:
        lookup = {
            str(row["case_id"]): bool(row["correct"])
            for row in rows
            if row["system"] == system
        }
        paired_ids = [case_id for case_id in case_order if case_id in lookup]
        correctness[system] = [lookup[case_id] for case_id in paired_ids]
        selected = [row for row in rows if row["system"] == system]
        summary["systems"][system] = {
            "correct": sum(correctness[system]),
            "total": len(correctness[system]),
            "accuracy": statistics.mean(correctness[system]) if correctness[system] else None,
            "by_family": {
                family: {
                    "correct": sum(bool(row["correct"]) for row in selected if row["family"] == family),
                    "total": sum(row["family"] == family for row in selected),
                    "accuracy": statistics.mean(
                        bool(row["correct"]) for row in selected if row["family"] == family
                    ),
                }
                for family in sorted({str(row["family"]) for row in selected})
            },
            "prompt_tokens_total": sum(int(row.get("prompt_eval_count") or 0) for row in selected),
            "generation_tokens_total": sum(int(row.get("eval_count") or 0) for row in selected),
            "latency_seconds": {
                "p50": percentile([float(row["latency_seconds"]) for row in selected], 0.5),
                "p95": percentile([float(row["latency_seconds"]) for row in selected], 0.95),
                "p99": percentile([float(row["latency_seconds"]) for row in selected], 0.99),
            },
        }
    for other in ("ordinary_rag", "strong_structured"):
        common = [
            case_id
            for case_id in case_order
            if any(row["case_id"] == case_id and row["system"] == "hng" for row in rows)
            and any(row["case_id"] == case_id and row["system"] == other for row in rows)
        ]
        hng_values = [
            next(bool(row["correct"]) for row in rows if row["case_id"] == case_id and row["system"] == "hng")
            for case_id in common
        ]
        other_values = [
            next(bool(row["correct"]) for row in rows if row["case_id"] == case_id and row["system"] == other)
            for case_id in common
        ]
        summary["paired_statistics"][f"hng_vs_{other}"] = {
            "paired_cases": len(common),
            "paired_bootstrap_accuracy": bootstrap_delta(hng_values, other_values) if common else None,
            "mcnemar": mcnemar(hng_values, other_values) if common else None,
        }
    (output / "LLM_RESULTS.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "breakthrough_eval" / "fixed_candidate")
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--llm-limit", type=int, default=30)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-digest", default=DEFAULT_DIGEST)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=300.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    scenarios = generate_scenarios()
    if len(scenarios) != 250:
        raise AssertionError(f"expected 250 scenarios, got {len(scenarios)}")
    if args.llm:
        result = run_llm(
            scenarios,
            args.output,
            model=args.model,
            model_digest=args.model_digest,
            endpoint=args.endpoint,
            timeout=args.timeout,
            limit=args.llm_limit,
        )
    else:
        result = run_deterministic(scenarios, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
