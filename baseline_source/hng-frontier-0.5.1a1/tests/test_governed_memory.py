from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from hngfrontier import (
    Decision, DeploymentMode, DocumentChunk, EvidenceConsolidator, EvidenceKind, EvidenceProvenance,
    EvidenceRequirement, GovernedProfile, GovernedShadowEvaluator, HNGMemory, HybridDocumentRetriever,
    PerspectiveField, ProfileOverride, QueryIntent, QueryPlanV2, RAGEvidenceAdapter, RetrievedChunk,
    SemanticState, SemanticValue, TemporalValidity,
)


DIM = 256


def hv(seed: int) -> SemanticValue:
    return SemanticValue.hdc(np.random.default_rng(seed).integers(0, 2, DIM, dtype=np.uint8))


def state(seed: int = 1, *, environment: str | None = None) -> SemanticState:
    fields = {"state": hv(seed), "goal": hv(seed + 1), "sequence": hv(seed + 2)}
    if environment is not None:
        fields["environment_version"] = SemanticValue.structured(environment)
    return SemanticState(fields)


def provenance(source_type="system_telemetry", source_id="source", trust=1.0, verified=True):
    return EvidenceProvenance(source_type, source_id, trust, verified)


def add_outcome(mem: HNGMemory, query: SemanticState, action: SemanticValue, *, event: str,
                score: float, confidence: float = 1.0, source_type="system_telemetry",
                trust=1.0, verified=True, validity=None, experience_id=None,
                group=None, kind=EvidenceKind.OUTCOME, **kwargs):
    semantics = query.merged({"action": action}, revision=query.revision)
    return mem.ingest_evidence(
        content=f"{event}:{score}", semantics=semantics, kind=kind, outcome_score=score,
        confidence=confidence, provenance=provenance(source_type, event, trust, verified),
        experience_id=experience_id, source_event_id=event, evidence_group_id=group or event,
        validity=validity, **kwargs,
    )


def confirmed_profile(user="u", tenant="t", role="ic", authority=1, *, role_confidence=1.0):
    return GovernedProfile(user, tenant, {
        "role": PerspectiveField(role, role_confidence, "user", True),
        "authority_level": PerspectiveField(authority, 1.0, "system_identity", True),
        "abstraction_level": PerspectiveField(1, 1.0, "user", True),
        "priority": PerspectiveField("safety", 0.8, "inferred", False),
    })


def test_balanced_independent_evidence_is_conflicted(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="success", score=1)
        add_outcome(mem, q, action, event="failure", score=-1)
        frame = mem.evaluate_action(q, action, conversation_id="c")
        assert frame.assessment.decision is Decision.CONFLICTED
        assert frame.assessment.independent_support_count == 1
        assert frame.assessment.independent_challenge_count == 1


def test_stale_majority_cannot_overpower_new_environment(tmp_path):
    old, current, action = state(environment="v1"), state(environment="v2"), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        for i in range(100):
            add_outcome(mem, old, action, event=f"old-{i}", score=1,
                        validity=TemporalValidity(environment_version="v1"))
        for i in range(3):
            add_outcome(mem, current, action, event=f"new-{i}", score=-1,
                        validity=TemporalValidity(environment_version="v2"))
        frame = mem.evaluate_action(current, action, conversation_id="c")
        assert frame.assessment.decision is Decision.CHALLENGE
        assert frame.assessment.independent_support_count == 0
        assert any("environment_version_mismatch" == item.reason for item in frame.assessment.excluded)


def test_duplicate_amplification_is_collapsed_by_source_event(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        for i in range(100):
            add_outcome(mem, q, action, event="one-underlying-event", score=1, confidence=0.5,
                        experience_id=f"copy-{i}", group=f"copy-group-{i}",
                        source_type="user_assertion", trust=0.65, verified=True)
        frame = mem.evaluate_action(q, action, conversation_id="c")
        assert frame.assessment.decision is Decision.INSUFFICIENT_EVIDENCE
        assert frame.assessment.independent_support_count == 1
        assert frame.assessment.support_score < 0.6


@pytest.mark.parametrize("kind", [EvidenceKind.HYPOTHESIS, EvidenceKind.BELIEF, EvidenceKind.CLAIM])
def test_repeated_model_speculation_never_becomes_authoritative(tmp_path, kind):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        for i in range(20):
            add_outcome(mem, q, action, event=f"model-{i}", score=1, kind=kind,
                        source_type="model_inference", trust=0.95, verified=False)
        frame = mem.evaluate_action(q, action, conversation_id="c")
        assert frame.assessment.decision is Decision.UNTRUSTED_EVIDENCE
        assert not frame.assessment.included


def test_poisoned_document_does_not_manufacture_support(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="poison-doc", score=1, kind=EvidenceKind.DOCUMENT_CLAIM,
                    source_type="external_document", trust=0.2, verified=False)
        assert mem.evaluate_action(q, action, conversation_id="c").assessment.decision is Decision.UNTRUSTED_EVIDENCE


@pytest.mark.parametrize("missing", ["state", "goal", "sequence"])
def test_missing_required_state_fails_closed(tmp_path, missing):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="known", score=1)
        partial = SemanticState({name: value for name, value in q.fields.items() if name != missing})
        frame = mem.evaluate_action(partial, action, conversation_id="c")
        assert frame.assessment.decision is Decision.INSUFFICIENT_STATE
        assert missing in frame.assessment.missing_state


def test_changed_sequence_rejects_old_precedent(tmp_path):
    q, action = state(), hv(10)
    changed = q.merged({"sequence": hv(99)}, revision=q.revision)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="old", score=1)
        frame = mem.evaluate_action(changed, action, conversation_id="c")
        assert frame.assessment.decision is Decision.INSUFFICIENT_EVIDENCE
        assert any(item.reason.startswith("semantic_floor:sequence") for item in frame.assessment.excluded)


def test_unseen_action_is_insufficient(tmp_path):
    q = state()
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, hv(10), event="known", score=1)
        assert mem.evaluate_action(q, hv(999), conversation_id="c").assessment.decision is Decision.INSUFFICIENT_EVIDENCE


def test_close_wrong_action_is_rejected_by_strict_floor(tmp_path):
    q = state()
    base = np.random.default_rng(10).integers(0, 2, DIM, dtype=np.uint8)
    close = base.copy(); close[:13] ^= 1
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, SemanticValue.hdc(base), event="known", score=1)
        frame = mem.evaluate_action(q, SemanticValue.hdc(close), conversation_id="c")
        assert frame.assessment.decision is Decision.INSUFFICIENT_EVIDENCE
        assert any(item.reason.startswith("semantic_floor:action") for item in frame.assessment.excluded)


def test_loose_caller_floor_cannot_weaken_central_action_policy(tmp_path):
    q = state()
    base = np.random.default_rng(10).integers(0, 2, DIM, dtype=np.uint8)
    close = base.copy(); close[:13] ^= 1
    loose = QueryPlanV2(QueryIntent.ACTION_EVALUATION,
                        EvidenceRequirement(("state", "goal", "sequence", "action"),
                                            min_similarity={"action": 0.5}, strict_action_floor=0.5), critical=False)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, SemanticValue.hdc(base), event="known", score=1)
        frame = mem.evaluate_action(q, SemanticValue.hdc(close), conversation_id="c", plan=loose)
        assert frame.assessment.decision is Decision.INSUFFICIENT_EVIDENCE


def test_inferred_low_confidence_profile_returns_profile_uncertain(tmp_path):
    q, action = state(), hv(10)
    profile = GovernedProfile("u", "t", {
        "role": PerspectiveField("manager", 0.42, "inferred", False),
        "authority_level": PerspectiveField(2, 0.42, "inferred", False),
    })
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.set_profile(profile); mem.activate_profile("c", "u")
        add_outcome(mem, q, action, event="known", score=1, tenant_id="t", scope="tenant")
        assert mem.evaluate_action(q, action, conversation_id="c").assessment.decision is Decision.PROFILE_UNCERTAIN


def test_authority_inappropriate_precedent_is_excluded(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.set_profile(confirmed_profile()); mem.activate_profile("c", "u")
        add_outcome(mem, q, action, event="executive", score=1, tenant_id="t", scope="tenant",
                    role="ic", authority_level=5)
        frame = mem.evaluate_action(q, action, conversation_id="c")
        assert frame.assessment.decision is Decision.INSUFFICIENT_EVIDENCE
        assert any(item.reason == "authority_ineligible" for item in frame.assessment.excluded)


def test_private_memory_collision_never_leaks(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.set_profile(confirmed_profile("alice", "a")); mem.activate_profile("alice-chat", "alice")
        add_outcome(mem, q, action, event="alice-private", score=1, tenant_id="a", user_id="alice", scope="private")
        mem.set_profile(confirmed_profile("bob", "a")); mem.activate_profile("bob-chat", "bob")
        frame = mem.evaluate_action(q, action, conversation_id="bob-chat")
        assert frame.assessment.decision is Decision.INSUFFICIENT_EVIDENCE
        assert frame.retrieved_candidates == 0


def test_tenant_memory_collision_never_leaks(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.set_profile(confirmed_profile("alice", "a")); mem.activate_profile("a-chat", "alice")
        add_outcome(mem, q, action, event="a-tenant", score=1, tenant_id="a", scope="tenant")
        mem.set_profile(confirmed_profile("bob", "b")); mem.activate_profile("b-chat", "bob")
        assert mem.evaluate_action(q, action, conversation_id="b-chat").assessment.decision is Decision.INSUFFICIENT_EVIDENCE


def test_global_memory_is_visible_across_tenants(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="global", score=1, scope="global")
        mem.set_profile(confirmed_profile("bob", "b")); mem.activate_profile("b-chat", "bob")
        assert mem.evaluate_action(q, action, conversation_id="b-chat").assessment.decision is Decision.SUPPORT


def test_explicit_supersession_prevents_old_support(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        old = add_outcome(mem, q, action, event="old", score=1)
        add_outcome(mem, q, action, event="new", score=-1, supersedes=(old.experience_id,))
        frame = mem.evaluate_action(q, action, conversation_id="c")
        assert frame.assessment.decision is Decision.CHALLENGE
        assert frame.assessment.independent_support_count == 0


def test_only_superseded_evidence_reports_superseded(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        old = add_outcome(mem, q, action, event="old", score=1)
        mem.supersede((old.experience_id,), "replacement-not-indexed")
        assert mem.evaluate_action(q, action, conversation_id="c").assessment.decision is Decision.SUPERSEDED


def test_invalidated_evidence_cannot_support(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        record = add_outcome(mem, q, action, event="bad", score=1)
        mem.invalidate(record.experience_id)
        assert mem.evaluate_action(q, action, conversation_id="c").assessment.decision is Decision.INSUFFICIENT_EVIDENCE


def test_expired_evidence_is_excluded(tmp_path):
    q, action = state(), hv(10)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="expired", score=1, validity=TemporalValidity(valid_until=past))
        frame = mem.evaluate_action(q, action, conversation_id="c")
        assert frame.assessment.decision is Decision.INSUFFICIENT_EVIDENCE
        assert any(item.reason == "expired" for item in frame.assessment.excluded)


def test_future_evidence_is_excluded(tmp_path):
    q, action = state(), hv(10)
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="future", score=1, validity=TemporalValidity(valid_from=future))
        assert mem.evaluate_action(q, action, conversation_id="c").assessment.decision is Decision.INSUFFICIENT_EVIDENCE


def test_policy_version_mismatch_is_excluded(tmp_path):
    q = state().merged({"policy_version": SemanticValue.structured("p2")})
    action = hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="p1", score=1, validity=TemporalValidity(policy_version="p1"))
        frame = mem.evaluate_action(q, action, conversation_id="c")
        assert any(item.reason == "policy_version_mismatch" for item in frame.assessment.excluded)


def test_one_trusted_failure_beats_many_low_trust_poisoned_successes(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        for i in range(50):
            add_outcome(mem, q, action, event=f"poison-{i}", score=1,
                        source_type="model_inference", trust=1, verified=False)
        add_outcome(mem, q, action, event="telemetry-failure", score=-1)
        frame = mem.evaluate_action(q, action, conversation_id="c")
        assert frame.assessment.decision is Decision.CHALLENGE
        assert frame.assessment.independent_support_count == 0


def test_two_distinct_moderate_sources_are_independent(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        for event in ("human-a", "human-b"):
            add_outcome(mem, q, action, event=event, score=1, confidence=0.8,
                        source_type="user_assertion", trust=0.65, verified=True)
        frame = mem.evaluate_action(q, action, conversation_id="c")
        assert frame.assessment.decision is Decision.SUPPORT
        assert frame.assessment.independent_support_count == 2


def test_changed_role_excludes_old_role_precedent(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.set_profile(confirmed_profile(role="ic")); mem.activate_profile("c", "u")
        add_outcome(mem, q, action, event="old-role", score=1, tenant_id="t", scope="tenant", role="ic")
        mem.set_profile(confirmed_profile(role="manager")); mem.activate_profile("c", "u")
        frame = mem.evaluate_action(q, action, conversation_id="c")
        assert frame.assessment.decision is Decision.INSUFFICIENT_EVIDENCE
        assert any(item.reason == "actor_role_ineligible" for item in frame.assessment.excluded)


def test_conversation_override_has_clear_precedence(tmp_path):
    q, action = state(), hv(10)
    override = ProfileOverride({
        "role": PerspectiveField("manager", 1, "conversation_explicit", True),
        "authority_level": PerspectiveField(3, 1, "conversation_explicit", True),
    })
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        mem.set_profile(confirmed_profile(role="ic")); mem.activate_profile("c", "u", override)
        add_outcome(mem, q, action, event="manager", score=1, tenant_id="t", scope="tenant", role="manager", authority_level=2)
        frame = mem.evaluate_action(q, action, conversation_id="c")
        assert frame.assessment.decision is Decision.SUPPORT
        assert set(mem.effective_profile("c").override_fields) == {"authority_level", "role"}


def test_recent_low_confidence_evidence_does_not_force_decision(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="weak", score=1, confidence=0.2)
        assert mem.evaluate_action(q, action, conversation_id="c").assessment.decision is Decision.INSUFFICIENT_EVIDENCE


def test_authoritative_indefinite_fact_remains_valid(tmp_path):
    q, action = state(environment="v99"), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="timeless", score=1, validity=TemporalValidity())
        assert mem.evaluate_action(q, action, conversation_id="c").assessment.decision is Decision.SUPPORT


def test_exact_state_floor_blocks_highly_similar_wrong_context(tmp_path):
    q, action = state(), hv(10)
    bits = np.unpackbits(np.asarray(q.fields["state"].value, np.uint8), bitorder="little", count=DIM)
    bits[:60] ^= 1
    wrong = q.merged({"state": SemanticValue.hdc(bits)}, revision=q.revision)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="known", score=1)
        assert mem.evaluate_action(wrong, action, conversation_id="c").assessment.decision is Decision.INSUFFICIENT_EVIDENCE


def test_working_state_carries_directly_and_survives_restart(tmp_path):
    q = state()
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        carried = mem.update_state("c", q, open_loops=("review",), constraints=("no restart",))
        assert carried.fields["state"].exact_similarity(q.fields["state"]) == 1
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        restored, loops, constraints = mem.store.working_state("c")
        assert restored.fields["state"].exact_similarity(q.fields["state"]) == 1
        assert loops == ("review",) and constraints == ("no restart",)


def test_rag_adapter_preserves_chunk_provenance(tmp_path):
    q = state()
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        adapter = RAGEvidenceAdapter(mem)
        ids = adapter.ingest_chunks(
            [RetrievedChunk("1", "doc", "verified clause", "https://example.test/doc", 1.0, {})],
            semantics=lambda chunk: q, trust_score=0.9, verified=True,
        )
        record = mem.store.get(ids[0])
        assert record is not None
        assert record.kind is EvidenceKind.DOCUMENT_CLAIM
        assert record.provenance.source_id == "https://example.test/doc"


def test_assessment_is_auditable_and_prompt_bounded(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="good", score=1)
        frame = mem.evaluate_action(q, action, conversation_id="c")
        payload = frame.as_dict()
        assert payload["assessment"]["included"][0]["source"]["source_id"] == "good"
        assert "independent current support" in frame.to_prompt_context(max_chars=1000)
        assert len(frame.to_prompt_context(max_chars=80)) <= 80


def test_faiss_default_uses_provider_or_explicit_reference_fallback(tmp_path):
    with HNGMemory(tmp_path, semantic_backend="faiss-auto") as mem:
        q, action = state(), hv(10)
        add_outcome(mem, q, action, event="known", score=1)
        mem.rebuild_retrieval()
        frame = mem.evaluate_action(q, action, conversation_id="c")
        assert frame.assessment.decision is Decision.SUPPORT
        providers = mem.stats()["providers"]
        assert providers["state"]["provider"] in {"faiss-binary", "reference-hng-fallback"}


def test_shadow_mode_never_blocks_and_logs_reasons(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path / "memory", semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="failure", score=-1)
        frame = mem.evaluate_action(q, action, conversation_id="c")
        shadow = GovernedShadowEvaluator(tmp_path / "shadow.jsonl")
        decision = shadow.log(frame, assistant_action="attempt")
        assert decision.would_block and not decision.blocks
        assert shadow.summarize()["decisions"]["challenge"] == 1
    with pytest.raises(ValueError):
        GovernedShadowEvaluator(tmp_path / "bad.jsonl", mode=DeploymentMode.HARD_GATE)


def test_consolidation_is_reversible_and_deduplicated(tmp_path):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        for i in range(4):
            add_outcome(mem, q, action, event="same-event", group="pattern", score=1, experience_id=f"copy-{i}")
        add_outcome(mem, q, action, event="independent-failure", group="pattern", score=-1)
        pattern = EvidenceConsolidator().consolidate(mem.store.all())[0]
        assert pattern.reversible
        assert len(pattern.source_experience_ids) == 5
        assert len(pattern.independent_source_event_ids) == 2
        assert pattern.support_count == 1 and pattern.challenge_count == 1


def test_hybrid_document_stack_uses_bm25_and_exact_metadata():
    stack = HybridDocumentRetriever()
    stack.ingest(DocumentChunk("a", "doc-a", "redis allocator regression", "a", metadata={"tenant": "x"}))
    stack.ingest(DocumentChunk("b", "doc-b", "redis allocator regression", "b", metadata={"tenant": "y"}))
    result = stack.search("allocator regression", filters={"tenant": "x"})
    assert [item.chunk.chunk_id for item in result] == ["a"]
    assert result[0].channels == ("bm25",)


def test_concurrent_writers_and_readers_see_coherent_records(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        def write(i):
            return add_outcome(mem, q, action, event=f"event-{i}", score=-1, experience_id=f"record-{i}").experience_id
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(write, range(24)))
        with ThreadPoolExecutor(max_workers=4) as pool:
            decisions = list(pool.map(lambda _: mem.evaluate_action(q, action, conversation_id="c").assessment.decision, range(16)))
        assert len(set(ids)) == 24 and len(mem.store.all()) == 24
        assert set(decisions) == {Decision.CHALLENGE}


def test_failed_duplicate_insert_rolls_back_without_partial_record(tmp_path):
    import sqlite3
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="first", score=1, experience_id="same-id")
        with pytest.raises(sqlite3.IntegrityError):
            add_outcome(mem, q, action, event="second", score=-1, experience_id="same-id")
        records = mem.store.all()
        assert len(records) == 1 and records[0].source_event_id == "first"


def test_interrupted_rebuild_does_not_damage_authoritative_store(tmp_path, monkeypatch):
    q, action = state(), hv(10)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as mem:
        add_outcome(mem, q, action, event="durable", score=1)
        monkeypatch.setattr(mem._providers["state"], "rebuild", lambda: (_ for _ in ()).throw(RuntimeError("crash")))
        with pytest.raises(RuntimeError): mem.rebuild_retrieval()
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as reopened:
        assert reopened.evaluate_action(q, action, conversation_id="c").assessment.decision is Decision.SUPPORT
