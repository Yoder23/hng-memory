"""Named profile-revision cases required by the completion mandate."""
from __future__ import annotations

import numpy as np

from hngfrontier import (Decision, EvidenceProvenance, GovernedProfile, HNGMemory,
                         PerspectiveField, SemanticState, SemanticValue)


def hv(seed: int, dim: int = 256) -> SemanticValue:
    return SemanticValue.hdc(np.random.default_rng(seed).choice([-1, 1], size=dim), dimension=dim)


def state() -> SemanticState:
    return SemanticState({"state": hv(1), "goal": hv(2), "sequence": hv(3)})


def fields(**changes):
    base = {"role": PerspectiveField("ic", 1, "user-confirmed", True),
            "authority_level": PerspectiveField(3, 1, "user-confirmed", True),
            "responsibility_scope": PerspectiveField("payments", 1, "user-confirmed", True),
            "abstraction_level": PerspectiveField(2, 1, "user-confirmed", True),
            "expertise": PerspectiveField("backend", 1, "user-confirmed", True),
            "priority": PerspectiveField("safety", 1, "user-confirmed", True)}
    base.update(changes); return base


def install(memory: HNGMemory, **changes):
    memory.set_profile(GovernedProfile("u", "t", fields(**changes)))
    return memory.activate_profile("c", "u")


def remember(memory: HNGMemory):
    current = state().merged({"expertise": SemanticValue.structured("backend"),
                              "priority": SemanticValue.structured("safety")})
    action = hv(10)
    memory.remember_transition(conversation_id="c", state=current, action=action, next_state=hv(20),
        outcome="worked", outcome_score=1, provenance=EvidenceProvenance("system_telemetry", "event", 1, True),
        tenant_id="t", scope="tenant", role="ic", authority_level=3, abstraction_level=2,
        metadata={"responsibility_scope": "payments"})
    return action


def test_changed_responsibility_is_retained_but_discounted(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as memory:
        install(memory); action = remember(memory)
        install(memory, responsibility_scope=PerspectiveField("search", 1, "user-confirmed", True))
        item = memory.evaluate_action(state(), action, conversation_id="c").assessment.included[0]
        assert item.factors["perspective"] == "reduced_confidence"
        assert "responsibility scope changed" in item.factors["perspective_reasons"]


def test_changed_abstraction_preference_can_make_history_incompatible(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as memory:
        install(memory); action = remember(memory)
        install(memory, abstraction_level=PerspectiveField(6, 1, "user-confirmed", True))
        frame = memory.evaluate_action(state(), action, conversation_id="c")
        assert frame.assessment.decision is Decision.INSUFFICIENT_EVIDENCE
        assert any("abstraction mismatch" in " ".join(x.factors.get("reasons", ()))
                   for x in frame.assessment.excluded)


def test_changed_expertise_is_fuzzy_and_discounted(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as memory:
        install(memory); action = remember(memory)
        install(memory, expertise=PerspectiveField("frontend", 1, "user-confirmed", True))
        item = memory.evaluate_action(state(), action, conversation_id="c").assessment.included[0]
        assert item.factors["fuzzy_scores"]["expertise"] == 0
        assert item.factors["perspective"] == "reduced_confidence"


def test_changed_priority_is_fuzzy_and_discounted(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as memory:
        install(memory); action = remember(memory)
        install(memory, priority=PerspectiveField("speed", 1, "user-confirmed", True))
        item = memory.evaluate_action(state(), action, conversation_id="c").assessment.included[0]
        assert item.factors["fuzzy_scores"]["priority"] == 0
        assert item.factors["perspective"] == "reduced_confidence"


def test_inferred_profile_later_corrected_by_user(tmp_path):
    inferred = {"role": PerspectiveField("manager", .45, "inferred", False),
                "authority_level": PerspectiveField(5, .45, "inferred", False)}
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as memory:
        memory.set_profile(GovernedProfile("u", "t", inferred)); memory.activate_profile("c", "u")
        assert memory.evaluate_action(state(), hv(10), conversation_id="c").assessment.decision is Decision.PROFILE_UNCERTAIN
        memory.set_profile(GovernedProfile("u", "t", fields())); memory.activate_profile("c", "u")
        action = remember(memory)
        assert memory.evaluate_action(state(), action, conversation_id="c").assessment.decision is Decision.SUPPORT
        assert [p.revision for p in memory.profile_history("u")] == [1, 2]
