from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1"
sys.path.insert(0, str(SOURCE / "src"))

from hngfrontier import (  # noqa: E402
    Decision, EvidenceKind, EvidenceProvenance, EvidenceRequirement, GovernedProfile, HNGMemory,
    PerspectiveField, QueryIntent, QueryPlanV2, SemanticState, SemanticValue, TemporalValidity,
)

DIM = 512


def hv(seed):
    return SemanticValue.hdc(np.random.default_rng(seed).integers(0, 2, DIM, dtype=np.uint8))


def state(seed=1, env=None):
    fields = {"state": hv(seed), "goal": hv(seed + 1), "sequence": hv(seed + 2)}
    if env:
        fields["environment_version"] = SemanticValue.structured(env)
    return SemanticState(fields)


def add(mem, query, action, event, score, **kwargs):
    source_type = kwargs.pop("source_type", "system_telemetry")
    trust = kwargs.pop("trust", 1.0)
    verified = kwargs.pop("verified", True)
    return mem.ingest_evidence(
        content=event, semantics=query.merged({"action": action}, revision=query.revision),
        provenance=EvidenceProvenance(source_type, event, trust, verified), kind=kwargs.pop("kind", EvidenceKind.OUTCOME),
        outcome_score=score, source_event_id=event, evidence_group_id=kwargs.pop("group", event), **kwargs,
    )


def run():
    run_root = ROOT / "next_eval" / "run_data" / "adversarial_11"
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True)
    results = []

    def case(name, expected, actual, detail=""):
        value = actual.value if isinstance(actual, Decision) else str(actual)
        allowed = {item.value if isinstance(item, Decision) else str(item) for item in (expected if isinstance(expected, tuple) else (expected,))}
        results.append({"case": name, "expected": sorted(allowed), "actual": value, "passed": value in allowed, "detail": detail})

    q, action = state(), hv(10)
    with HNGMemory(run_root, semantic_backend="faiss-auto") as mem:
        add(mem, q, action, "balanced-positive", 1); add(mem, q, action, "balanced-negative", -1)
        case("balanced_evidence", Decision.CONFLICTED, mem.evaluate_action(q, action, conversation_id="c").assessment.decision)

    shutil.rmtree(run_root); q1, q2 = state(env="v1"), state(env="v2")
    with HNGMemory(run_root, semantic_backend="faiss-auto") as mem:
        for i in range(100): add(mem, q1, action, f"old-{i}", 1, validity=TemporalValidity(environment_version="v1"))
        for i in range(3): add(mem, q2, action, f"new-{i}", -1, validity=TemporalValidity(environment_version="v2"))
        case("stale_majority", Decision.CHALLENGE, mem.evaluate_action(q2, action, conversation_id="c").assessment.decision)

    shutil.rmtree(run_root)
    with HNGMemory(run_root, semantic_backend="faiss-auto") as mem:
        for i in range(20): add(mem, q, action, f"poison-{i}", 1, source_type="model_inference", trust=1, verified=False)
        case("poisoned_experiences", Decision.UNTRUSTED_EVIDENCE, mem.evaluate_action(q, action, conversation_id="c").assessment.decision)

    shutil.rmtree(run_root)
    with HNGMemory(run_root, semantic_backend="faiss-auto") as mem:
        for i in range(100):
            add(mem, q, action, "duplicate-event", 1, experience_id=f"copy-{i}", group=f"fake-group-{i}",
                source_type="user_assertion", trust=.65, verified=True, confidence=.5)
        frame = mem.evaluate_action(q, action, conversation_id="c")
        case("duplicate_amplification", Decision.INSUFFICIENT_EVIDENCE, frame.assessment.decision,
             f"independent_support={frame.assessment.independent_support_count}")

    shutil.rmtree(run_root)
    with HNGMemory(run_root, semantic_backend="faiss-auto") as mem:
        add(mem, q, action, "known", 1)
        partial = SemanticState({"state": q.fields["state"], "goal": q.fields["goal"]})
        case("missing_sequence", Decision.INSUFFICIENT_STATE, mem.evaluate_action(partial, action, conversation_id="c").assessment.decision)
        changed = q.merged({"sequence": hv(999)}, revision=q.revision)
        case("changed_sequence_supplied", Decision.INSUFFICIENT_EVIDENCE, mem.evaluate_action(changed, action, conversation_id="c").assessment.decision)
        case("unseen_action", Decision.INSUFFICIENT_EVIDENCE, mem.evaluate_action(q, hv(888), conversation_id="c").assessment.decision)

    shutil.rmtree(run_root)
    base = np.random.default_rng(7).integers(0, 2, DIM, dtype=np.uint8)
    close = base.copy(); close[:26] ^= 1
    base_action, close_action = SemanticValue.hdc(base), SemanticValue.hdc(close)
    with HNGMemory(run_root, semantic_backend="faiss-auto") as mem:
        add(mem, q, base_action, "strict-known", 1)
        case("close_wrong_action", Decision.INSUFFICIENT_EVIDENCE, mem.evaluate_action(q, close_action, conversation_id="c").assessment.decision)
        loose = QueryPlanV2(QueryIntent.ACTION_EVALUATION,
                            EvidenceRequirement(("state", "goal", "sequence", "action"), min_similarity={"action": .5}, strict_action_floor=.5))
        case("loose_action_floor", Decision.INSUFFICIENT_EVIDENCE,
             mem.evaluate_action(q, close_action, conversation_id="c", plan=loose).assessment.decision)

    shutil.rmtree(run_root)
    with HNGMemory(run_root, semantic_backend="faiss-auto") as mem:
        mem.set_profile(GovernedProfile("u", "t", {
            "role": PerspectiveField("manager", .42, "inferred", False),
            "authority_level": PerspectiveField(2, .42, "inferred", False),
        })); mem.activate_profile("c", "u")
        add(mem, q, action, "profile", 1, scope="tenant", tenant_id="t")
        case("incorrect_uncertain_profile", Decision.PROFILE_UNCERTAIN, mem.evaluate_action(q, action, conversation_id="c").assessment.decision)

    shutil.rmtree(run_root)
    with HNGMemory(run_root, semantic_backend="faiss-auto") as mem:
        mem.set_profile(GovernedProfile("u", "t", {
            "role": PerspectiveField("ic", 1, "user", True),
            "authority_level": PerspectiveField(1, 1, "system_identity", True),
        })); mem.activate_profile("c", "u")
        add(mem, q, action, "executive-only", 1, scope="tenant", tenant_id="t", role="ic", authority_level=5)
        frame = mem.evaluate_action(q, action, conversation_id="c")
        blocked = frame.assessment.decision is Decision.INSUFFICIENT_EVIDENCE and any(x.reason == "authority_ineligible" for x in frame.assessment.excluded)
        case("authority_inappropriate_precedent", "blocked", "blocked" if blocked else frame.assessment.decision)

    output = {
        "architecture": "HNG evidence-governed 0.7.0rc1", "timestamp": datetime.now(timezone.utc).isoformat(),
        "passed": sum(item["passed"] for item in results), "total": len(results), "cases": results,
    }
    raw = ROOT / "next_eval" / "raw"; raw.mkdir(parents=True, exist_ok=True)
    (raw / "ADVERSARIAL_11.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
    raise SystemExit(0 if output["passed"] == output["total"] else 1)


if __name__ == "__main__":
    run()

