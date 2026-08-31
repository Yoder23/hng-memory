from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Iterable, Mapping

from .governance import (
    AssessedEvidence, Decision, EvidenceAssessment, EvidenceKind, EvidenceRecordV2, ExcludedEvidence, utc_now_iso,
)
from .profiles import EffectiveProfile
from .actor_policy import ActorPolicy, ProfileApplicability
from .query_planner import QueryPlanV2
from .semantic import SemanticKind, SemanticState


@dataclass(frozen=True, slots=True)
class TrustPolicy:
    minimum_trust: float = 0.60
    minimum_verified_trust: float = 0.45
    support_threshold: float = 0.60
    challenge_threshold: float = 0.60
    conflict_ratio: float = 0.50
    strict_action_floor: float = 0.97
    profile_confidence_threshold: float = 0.80
    require_authoritative_profile_for_critical: bool = True
    source_weights: Mapping[str, float] = field(default_factory=lambda: {
        "system_telemetry": 1.0,
        "authoritative_database": 1.0,
        "human_confirmed": 0.95,
        "tool_result": 0.90,
        "external_document": 0.75,
        "user_assertion": 0.65,
        "model_inference": 0.35,
        "unverified_text": 0.25,
    })
    kind_weights: Mapping[EvidenceKind, float] = field(default_factory=lambda: {
        EvidenceKind.SYSTEM_EVENT: 1.0,
        EvidenceKind.OUTCOME: 1.0,
        EvidenceKind.TOOL_RESULT: 0.95,
        EvidenceKind.OBSERVATION: 0.90,
        EvidenceKind.FACT: 0.90,
        EvidenceKind.DOCUMENT_CLAIM: 0.75,
        EvidenceKind.CLAIM: 0.65,
        EvidenceKind.PROCEDURE: 0.80,
        EvidenceKind.CONSTRAINT: 0.90,
        EvidenceKind.PREFERENCE: 0.70,
        EvidenceKind.PROFILE: 0.70,
        EvidenceKind.ACTION: 0.70,
        EvidenceKind.BELIEF: 0.45,
        EvidenceKind.HYPOTHESIS: 0.25,
        EvidenceKind.MODEL_INFERENCE: 0.30,
    })

    def trust(self, record: EvidenceRecordV2) -> float:
        source_weight = float(self.source_weights.get(record.provenance.source_type, 0.40))
        kind_weight = float(self.kind_weights.get(record.kind, 0.50))
        verified_factor = 1.0 if record.provenance.verified else 0.75
        return min(record.provenance.trust_score, source_weight) * kind_weight * verified_factor


class EvidenceAggregator:
    """Auditable, independence-aware evidence governance; no duplicate voting."""

    def __init__(self, policy: TrustPolicy | None = None, actor_policy: ActorPolicy | None = None):
        self.policy = policy or TrustPolicy()
        self.actor_policy = actor_policy or ActorPolicy()

    @staticmethod
    def _structured_text(state: SemanticState, name: str) -> str:
        value = state.fields.get(name)
        return "" if value is None else str(value.value)

    def assess(self, records: Iterable[EvidenceRecordV2], query: SemanticState, plan: QueryPlanV2, *,
               profile: EffectiveProfile | None = None, now: str | None = None) -> EvidenceAssessment:
        started = time.perf_counter()
        missing = plan.requirement.validate(query)
        if missing:
            return EvidenceAssessment(0, 0, 0, 0, 0, 0, Decision.INSUFFICIENT_STATE,
                                      ("missing required semantic state: " + ", ".join(missing),), missing_state=missing,
                                      latency_ms=(time.perf_counter() - started) * 1000)
        if plan.requirement.require_profile and profile is None:
            return EvidenceAssessment(0, 0, 0, 0, 0, 0, Decision.PROFILE_UNCERTAIN,
                                      ("required actor profile is absent",), latency_ms=(time.perf_counter() - started) * 1000)
        if plan.critical and profile is not None and plan.required_profile_fields:
            uncertain = profile.uncertain(
                plan.required_profile_fields, threshold=self.policy.profile_confidence_threshold,
                require_authoritative=self.policy.require_authoritative_profile_for_critical,
            )
            if uncertain:
                return EvidenceAssessment(0, 0, 0, 0, 0, 0, Decision.PROFILE_UNCERTAIN,
                                          ("critical profile fields are uncertain: " + ", ".join(uncertain),),
                                          latency_ms=(time.perf_counter() - started) * 1000)

        at = now or utc_now_iso()
        component_ms = {"temporal_governance": 0.0, "perspective_policy": 0.0,
                        "vector_exact_verification": 0.0, "trust_evaluation": 0.0,
                        "independence_grouping": 0.0, "evidence_aggregation": 0.0}
        environment = self._structured_text(query, "environment_version")
        policy_version = self._structured_text(query, "policy_version")
        excluded: list[ExcludedEvidence] = []
        candidates: list[AssessedEvidence] = []
        saw_untrusted = False
        saw_superseded = False
        for record in records:
            if record.superseded_by is not None:
                excluded.append(ExcludedEvidence(record.experience_id, f"superseded_by:{record.superseded_by}"))
                saw_superseded = True
                continue
            if record.invalidated_at is not None:
                excluded.append(ExcludedEvidence(record.experience_id, "invalidated"))
                continue
            phase = time.perf_counter()
            active, reason = record.validity.active(at=at, environment_version=environment, policy_version=policy_version)
            component_ms["temporal_governance"] += (time.perf_counter() - phase) * 1000
            if not active:
                excluded.append(ExcludedEvidence(record.experience_id, reason, {"active": False, "reason": reason}))
                continue
            phase = time.perf_counter()
            actor_result = self.actor_policy.evaluate(record, profile)
            component_ms["perspective_policy"] += (time.perf_counter() - phase) * 1000
            if actor_result.applicability in {ProfileApplicability.PERSPECTIVE_INCOMPATIBLE, ProfileApplicability.SUPERSEDED}:
                actor_reason = actor_result.applicability.value
                if actor_result.reasons and actor_result.reasons[0].startswith("role changed"):
                    actor_reason = "actor_role_ineligible"
                elif actor_result.reasons and actor_result.reasons[0].startswith("active authority"):
                    actor_reason = "authority_ineligible"
                elif actor_result.reasons and actor_result.reasons[0].startswith("missing permissions"):
                    actor_reason = "permission_ineligible"
                excluded.append(ExcludedEvidence(record.experience_id, actor_reason,
                                                 {"applicability": actor_result.applicability.value,
                                                  "reasons": list(actor_result.reasons),
                                                  "fuzzy_scores": dict(actor_result.fuzzy_scores)}))
                if actor_result.applicability is ProfileApplicability.SUPERSEDED:
                    saw_superseded = True
                continue
            profile_factor = actor_result.confidence_factor
            if profile is not None:
                if record.tenant_id and record.tenant_id != profile.tenant_id:
                    excluded.append(ExcludedEvidence(record.experience_id, "tenant_mismatch"))
                    continue
                role = profile.field("role")
                if record.role and role is not None and role.authoritative and record.role != str(role.value):
                    excluded.append(ExcludedEvidence(record.experience_id, "actor_role_ineligible"))
                    continue
                authority = profile.field("authority_level")
                if record.authority_level is not None and authority is not None and authority.authoritative:
                    if int(authority.value) < int(record.authority_level):
                        excluded.append(ExcludedEvidence(record.experience_id, "authority_ineligible"))
                        continue
            scores: dict[str, float] = {}
            semantic_failure = None
            phase = time.perf_counter()
            for head in plan.requirement.required_heads:
                evidence_value = record.semantics.fields.get(head)
                query_value = query.fields.get(head)
                if evidence_value is None or query_value is None:
                    semantic_failure = f"evidence_missing_head:{head}"
                    break
                score = evidence_value.exact_similarity(query_value)
                scores[head] = score
                floor = float(plan.requirement.min_similarity.get(head, 0.0))
                if head == "action":
                    floor = max(floor, plan.requirement.strict_action_floor, self.policy.strict_action_floor)
                if score < floor:
                    semantic_failure = f"semantic_floor:{head}:{score:.4f}<{floor:.4f}"
                    break
            component_ms["vector_exact_verification"] += (time.perf_counter() - phase) * 1000
            if semantic_failure:
                excluded.append(ExcludedEvidence(record.experience_id, semantic_failure, {"exact_scores": scores}))
                continue
            for head in plan.requirement.optional_heads:
                if head in record.semantics.fields and head in query.fields:
                    scores[head] = record.semantics.fields[head].exact_similarity(query.fields[head])
            phase = time.perf_counter()
            trust = self.policy.trust(record)
            minimum = self.policy.minimum_verified_trust if record.provenance.verified else self.policy.minimum_trust
            component_ms["trust_evaluation"] += (time.perf_counter() - phase) * 1000
            if trust < minimum:
                saw_untrusted = True
                excluded.append(ExcludedEvidence(record.experience_id, f"untrusted:{trust:.3f}<{minimum:.3f}",
                                                 {"trust": trust, "minimum": minimum,
                                                  "source_type": record.provenance.source_type,
                                                  "verified": record.provenance.verified,
                                                  "verification_status": record.provenance.verification_status}))
                continue
            semantic_quality = sum(scores.values()) / len(scores) if scores else 1.0
            quality = trust * record.confidence * semantic_quality * profile_factor * min(1.0, abs(record.outcome_score) or 1.0)
            stance = "support" if record.outcome_score > 0 else "challenge" if record.outcome_score < 0 else "neutral"
            factors = {"trust": trust, "minimum_trust": minimum, "confidence": record.confidence,
                       "semantic_quality": semantic_quality, "profile_factor": profile_factor,
                       "temporal_active": True, "independence_group": record.source_event_id,
                       "perspective": actor_result.applicability.value,
                       "perspective_reasons": list(actor_result.reasons),
                       "fuzzy_scores": dict(actor_result.fuzzy_scores),
                       "verification_status": record.provenance.verification_status}
            candidates.append(AssessedEvidence(record, scores, quality, stance, record.source_event_id, factors))

        # One underlying source event contributes at most once, regardless of copied rows.
        phase = time.perf_counter()
        independent: dict[str, AssessedEvidence] = {}
        for candidate in candidates:
            previous = independent.get(candidate.group_key)
            if previous is None or candidate.quality > previous.quality:
                independent[candidate.group_key] = candidate
            else:
                excluded.append(ExcludedEvidence(candidate.record.experience_id, f"duplicate_event:{candidate.group_key}"))
        component_ms["independence_grouping"] = (time.perf_counter() - phase) * 1000
        phase = time.perf_counter()
        included = tuple(sorted(independent.values(), key=lambda item: (-item.quality, item.record.experience_id)))
        support = [item for item in included if item.stance == "support"]
        challenge = [item for item in included if item.stance == "challenge"]
        support_score = sum(item.quality for item in support)
        challenge_score = sum(item.quality for item in challenge)
        conflict_score = min(support_score, challenge_score)
        quality = sum(item.quality for item in included) / len(included) if included else 0.0
        reasons: list[str] = []
        if support and challenge and min(support_score, challenge_score) >= self.policy.conflict_ratio * max(support_score, challenge_score):
            decision = Decision.CONFLICTED
            reasons.append(f"{len(support)} independent support and {len(challenge)} independent challenge groups are materially balanced")
        elif challenge_score >= self.policy.challenge_threshold and challenge_score > support_score:
            decision = Decision.CHALLENGE
            reasons.append(f"{len(challenge)} independent current challenge groups outweigh support")
        elif support_score >= self.policy.support_threshold and support_score > challenge_score:
            decision = Decision.SUPPORT
            reasons.append(f"{len(support)} independent current support groups outweigh challenge")
        elif not included and saw_untrusted:
            decision = Decision.UNTRUSTED_EVIDENCE
            reasons.append("matching evidence exists but does not satisfy trust policy")
        elif not included and saw_superseded:
            decision = Decision.SUPERSEDED
            reasons.append("matching historical evidence has been superseded")
        else:
            decision = Decision.INSUFFICIENT_EVIDENCE
            reasons.append("current independent evidence does not meet a decision threshold")
        if excluded:
            counts: dict[str, int] = {}
            for item in excluded:
                category = item.reason.split(":", 1)[0]
                counts[category] = counts.get(category, 0) + 1
            reasons.append("excluded evidence: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
        component_ms["evidence_aggregation"] = (time.perf_counter() - phase) * 1000
        return EvidenceAssessment(
            support_score, challenge_score, conflict_score, len(support), len(challenge), quality,
            decision, tuple(reasons), included, tuple(excluded), latency_ms=(time.perf_counter() - started) * 1000,
            component_ms=component_ms,
        )
