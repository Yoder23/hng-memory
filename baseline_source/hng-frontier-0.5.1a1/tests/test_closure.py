from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from hngfrontier import (
    Belief, Commitment, DeploymentMode, DocumentChunk, EvidenceKind, EvidenceProvenance,
    GovernedProfile, GovernedShadowEvaluator, HDCAssistantAdapter, HNGMemory,
    LLMAssistantAdapter, PerspectiveField, ProfileOverride, SemanticState, SemanticValue,
    StaticIdentityVerifier, ToolAction, ToolAgentAdapter, WorkingCorrection,
)


def hv(seed: int, dim: int = 256) -> SemanticValue:
    return SemanticValue.hdc(np.random.default_rng(seed).choice([-1, 1], size=dim), dimension=dim)


def action_state(seed: int = 1) -> SemanticState:
    return SemanticState({"state": hv(seed), "goal": hv(seed + 1), "sequence": hv(seed + 2)})


def profile(role="ic", authority=1, **extra) -> GovernedProfile:
    fields = {
        "role": PerspectiveField(role, 1.0, "user-confirmed", True),
        "authority_level": PerspectiveField(authority, 1.0, "user-confirmed", True),
        **extra,
    }
    return GovernedProfile("u", "t", fields)


def trusted() -> EvidenceProvenance:
    return EvidenceProvenance("system_telemetry", "system", 1.0, True)


def precedent(mem: HNGMemory, *, role="ic", authority=1, abstraction=None, metadata=None):
    state, action = action_state(), hv(10)
    mem.remember_transition(conversation_id="c", state=state, action=action, next_state=hv(20),
                            outcome="worked", outcome_score=1.0, provenance=trusted(),
                            tenant_id="t", scope="tenant", role=role, authority_level=authority,
                            abstraction_level=abstraction, metadata=metadata or {})
    return state, action


@pytest.mark.parametrize("before,after", [("ic", "manager"), ("manager", "ic")])
def test_role_revision_is_reevaluated_without_rewriting_history(tmp_path, before, after):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.set_profile(profile(role=before)); mem.activate_profile("c", "u")
        state, action = precedent(mem, role=before)
        mem.set_profile(profile(role=after)); mem.activate_profile("c", "u")
        frame = mem.evaluate_action(state, action, conversation_id="c")
        assert frame.assessment.decision.value == "insufficient_evidence"
        assert any(item.reason == "actor_role_ineligible" for item in frame.assessment.excluded)
        assert len(mem.profile_history("u")) == 2


def test_temporary_acting_role_override_restores_applicability(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.set_profile(profile(role="ic"))
        override = ProfileOverride({"role": PerspectiveField("manager", 1.0, "user-confirmed", True)})
        mem.activate_profile("c", "u", override)
        state, action = precedent(mem, role="manager")
        assert mem.evaluate_action(state, action, conversation_id="c").assessment.decision.value == "support"


def test_authority_reduction_blocks_and_increase_allows(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.set_profile(profile(authority=5)); mem.activate_profile("c", "u")
        state, action = precedent(mem, authority=5)
        mem.set_profile(profile(authority=2)); mem.activate_profile("c", "u")
        assert any(x.reason == "authority_ineligible" for x in mem.evaluate_action(state, action, conversation_id="c").assessment.excluded)
        mem.set_profile(profile(authority=7)); mem.activate_profile("c", "u")
        assert mem.evaluate_action(state, action, conversation_id="c").assessment.decision.value == "support"


def test_responsibility_permission_and_abstraction_policy(tmp_path):
    extra = {
        "permissions": PerspectiveField(("deploy",), 1.0, "system_identity", True),
        "responsibility_scope": PerspectiveField("payments", 1.0, "user-confirmed", True),
        "abstraction_level": PerspectiveField(2, 1.0, "user-confirmed", True),
    }
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.set_profile(profile(**extra)); mem.activate_profile("c", "u")
        state, action = precedent(mem, abstraction=2, metadata={"required_permissions": ["deploy"], "responsibility_scope": "payments"})
        assert mem.evaluate_action(state, action, conversation_id="c").assessment.decision.value == "support"
        changed = dict(extra); changed["permissions"] = PerspectiveField((), 1.0, "system_identity", True)
        mem.set_profile(profile(**changed)); mem.activate_profile("c", "u")
        frame = mem.evaluate_action(state, action, conversation_id="c")
        assert any("permission" in item.reason for item in frame.assessment.excluded)


def test_fuzzy_expertise_and_priority_reduce_applicability(tmp_path):
    old_expertise, new_expertise = hv(40), hv(41)
    extra = {"expertise": PerspectiveField(old_expertise, 1.0, "user-confirmed", True),
             "priority": PerspectiveField("safety", 1.0, "user-confirmed", True)}
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.set_profile(profile(**extra)); mem.activate_profile("c", "u")
        state = action_state().merged({"expertise": old_expertise, "priority": SemanticValue.structured("safety")})
        action = hv(10)
        mem.remember_transition(conversation_id="c", state=state, action=action, next_state=hv(20), outcome="ok",
                                outcome_score=1, provenance=trusted(), tenant_id="t", scope="tenant", role="ic")
        changed = {"expertise": PerspectiveField(new_expertise, 1.0, "user-confirmed", True),
                   "priority": PerspectiveField("speed", 1.0, "user-confirmed", True)}
        mem.set_profile(profile(**changed)); mem.activate_profile("c", "u")
        frame = mem.evaluate_action(action_state(), action, conversation_id="c")
        assert frame.assessment.decision.value in {"insufficient_evidence", "support"}
        details = [x.factors for x in frame.assessment.included] + [x.factors for x in frame.assessment.excluded]
        assert any("fuzzy_scores" in value or "exact_scores" in value for value in details)


def test_complete_working_state_survives_restart_and_long_replay(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        for turn in range(100):
            mem.record_turn("c", turn_id=str(turn), speaker="user", content=f"turn {turn}", semantics=action_state(turn + 1))
        mem.add_correction("c", WorkingCorrection("fix-1", "turn 3", "corrected", "user correction"))
        mem.add_commitment("c", Commitment("commit-1", "ship fix"))
        mem.update_working_state("c", active_episode="episode-7", current_goal=hv(90),
                                 current_facts=("fact-a",), open_loops=("loop-a",), constraints=("safe",))
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        state = mem.working_state("c")
        assert len(state.recent_turns) == 32 and state.recent_turns[-1].turn_id == "99"
        assert state.corrections[0].replacement == "corrected" and state.commitments[0].text == "ship fix"
        assert state.active_episode == "episode-7" and state.current_facts == ("fact-a",)
        assert state.open_loops == ("loop-a",) and state.constraints == ("safe",)


def test_hdc_adapter_receives_complete_governed_context(tmp_path):
    captured = {}
    def encoder(value, **kwargs):
        captured.update(kwargs); return action_state()
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.record_turn("c", turn_id="1", speaker="user", content="hello", semantics=action_state())
        adapter = HDCAssistantAdapter(mem, encoder)
        adapter.encode_turn("next", conversation_id="c")
        assert captured["prior_state"].fields
        assert captured["working_context"]["recent_exact_turns"]
        assert "supporting_evidence" in captured["working_context"]
        assert captured["governed_frame"].assessment.decision.value


def test_llm_sections_and_token_budget_are_deterministic(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.update_state("c", action_state(), open_loops=("loop",), constraints=("constraint",))
        mem.add_commitment("c", Commitment("k", "deliver"))
        mem.update_working_state("c", current_goal=hv(9), current_facts=("known",))
        adapter = LLMAssistantAdapter(mem, max_context_chars=20_000, max_context_tokens=500)
        first = adapter.context(conversation_id="c"); second = adapter.context(conversation_id="c")
        for section in ("GOVERNANCE DECISION", "UNCERTAINTY", "CURRENT STATE", "ACTIVE GOAL",
                        "CURRENT FACTS", "OPEN LOOPS", "COMMITMENTS", "CONSTRAINTS"):
            assert section in first
        assert first == second and len(first) <= 2000


def test_top_level_hybrid_document_ingestion_and_filtering(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        chunk = DocumentChunk("c1", "d1", "alpha launch policy", "doc://d1", metadata={"region": "us"})
        record = mem.ingest_document_chunk(chunk, semantics=SemanticState({"state": hv(1)}), provenance=trusted())
        assert record.kind is EvidenceKind.DOCUMENT_CLAIM
        assert mem.search_documents("launch", filters={"region": "us"})[0].chunk.chunk_id == "c1"
        assert mem.search_documents("launch", filters={"region": "eu"}) == ()


def test_belief_revision_history_and_model_fact_rejection(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.beliefs.create(Belief("b1", "service is healthy", .6, "system", ("e1",), ()))
        revised = mem.beliefs.revise("b1", confidence=.2, contradicting_evidence_ids=("e2",), reason="failure observed")
        assert revised.revision == 2 and len(mem.beliefs.history("b1")) == 2
        with pytest.raises(ValueError):
            mem.ingest_evidence(content="guess", semantics=SemanticState({"state": hv(1)}),
                                provenance=EvidenceProvenance("model_inference", "m", 1, True), kind=EvidenceKind.FACT)


def test_persisted_consolidation_and_retention_never_delete_raw(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        rec = mem.observe("old", SemanticState({"state": hv(1)}), provenance=EvidenceProvenance("unverified_text", "x", .2),
                          experience_id="old", source_event_id="event", evidence_group_id="group")
        old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        mem.store.con.execute("UPDATE evidence SET created_at=? WHERE experience_id='old'", (old,)); mem.store.con.commit()
        assert mem.consolidate() == ("pattern:group",)
        assert mem.evaluate_retention()["old"] == "forgetting_eligible"
        assert mem.store.get("old") is not None


def test_pluggable_authenticated_provenance_and_observability(tmp_path):
    verifier = StaticIdentityVerifier({"tool-service": "spiffe://prod/tool"})
    with HNGMemory(tmp_path, semantic_backend="reference-hng", provenance_verifier=verifier) as mem:
        state, action = action_state(), hv(10)
        mem.remember_transition(conversation_id="c", state=state, action=action, next_state=hv(20), outcome="ok",
                                outcome_score=1, provenance=EvidenceProvenance("tool_result", "tool-service", 1, False))
        frame = mem.evaluate_action(state, action, conversation_id="c")
        item = frame.assessment.included[0]
        assert item.record.provenance.verified and item.record.provenance.verifier == "static-identity"
        assert frame.assessment.original_candidates and item.factors["trust"] > 0
        assert "retrieval" in frame.assessment.component_ms and mem.stats()["profile"]


def test_corrupt_metadata_fails_closed(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        rec = mem.observe("x", SemanticState({"state": hv(1)}), provenance=trusted())
        mem.store.con.execute("UPDATE evidence SET metadata_json='{' WHERE experience_id=?", (rec.experience_id,))
        mem.store.con.commit()
        assert mem.store.get(rec.experience_id) is None
        assert mem.recall(SemanticState({"state": hv(1)}), conversation_id="c").assessment.decision.value == "insufficient_evidence"


def test_tool_agent_preflight_logs_and_feeds_outcome_back(tmp_path):
    log = tmp_path / "tool.jsonl"
    with HNGMemory(tmp_path / "memory", semantic_backend="reference-hng") as mem:
        rollout = GovernedShadowEvaluator(log, mode=DeploymentMode.SHADOW)
        adapter = ToolAgentAdapter(mem, rollout)
        proposal = ToolAction("deploy", "restart", hv(10), {"service": "api"})
        result = adapter.execute(proposal, conversation_id="c", state=action_state(),
                                 executor=lambda action, args: {"success": True, "action": action},
                                 outcome_semantics=lambda result: hv(20), provenance=trusted())
        assert result["success"] and rollout.summarize()["records"] == 1
        assert any(record.kind is EvidenceKind.OUTCOME for record in mem.store.all())
