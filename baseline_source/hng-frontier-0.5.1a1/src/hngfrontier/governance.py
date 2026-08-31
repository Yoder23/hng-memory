from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Mapping

from .semantic import SemanticState


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Decision(str, Enum):
    SUPPORT = "support"
    CHALLENGE = "challenge"
    CONFLICTED = "conflicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INSUFFICIENT_STATE = "insufficient_state"
    SUPERSEDED = "superseded"
    UNTRUSTED_EVIDENCE = "untrusted_evidence"
    PROFILE_UNCERTAIN = "profile_uncertain"


class EvidenceKind(str, Enum):
    OBSERVATION = "observation"
    FACT = "fact"
    CLAIM = "claim"
    HYPOTHESIS = "hypothesis"
    BELIEF = "belief"
    ACTION = "action"
    OUTCOME = "outcome"
    PROCEDURE = "procedure"
    CONSTRAINT = "constraint"
    PREFERENCE = "preference"
    PROFILE = "profile"
    DOCUMENT_CLAIM = "document_claim"
    TOOL_RESULT = "tool_result"
    SYSTEM_EVENT = "system_event"


@dataclass(frozen=True, slots=True)
class EvidenceProvenance:
    source_type: str
    source_id: str
    trust_score: float = 0.5
    verified: bool = False
    observed_at: str = field(default_factory=utc_now_iso)
    actor_id: str = ""
    signature: str = ""

    def __post_init__(self):
        if not 0.0 <= self.trust_score <= 1.0:
            raise ValueError("trust_score must be in [0,1]")

    def as_dict(self) -> dict[str, object]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "trust_score": self.trust_score,
            "verified": self.verified,
            "observed_at": self.observed_at,
            "actor_id": self.actor_id,
            "signature": self.signature,
        }


@dataclass(frozen=True, slots=True)
class TemporalValidity:
    valid_from: str | None = None
    valid_until: str | None = None
    environment_version: str = ""
    policy_version: str = ""
    invalidated_at: str | None = None

    def active(self, *, at: str, environment_version: str = "", policy_version: str = "") -> tuple[bool, str]:
        if self.invalidated_at is not None:
            return False, "invalidated"
        if self.valid_from is not None and at < self.valid_from:
            return False, "not_yet_valid"
        if self.valid_until is not None and at > self.valid_until:
            return False, "expired"
        if self.environment_version and environment_version and self.environment_version != environment_version:
            return False, "environment_version_mismatch"
        if self.policy_version and policy_version and self.policy_version != policy_version:
            return False, "policy_version_mismatch"
        return True, "active"

    def as_dict(self) -> dict[str, object]:
        return {
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "environment_version": self.environment_version,
            "policy_version": self.policy_version,
            "invalidated_at": self.invalidated_at,
        }


@dataclass(frozen=True, slots=True)
class EvidenceRecordV2:
    experience_id: str
    evidence_group_id: str
    source_event_id: str
    episode_id: str
    conversation_id: str
    kind: EvidenceKind
    content: str
    semantics: SemanticState
    provenance: EvidenceProvenance
    validity: TemporalValidity = field(default_factory=TemporalValidity)
    outcome_score: float = 0.0
    confidence: float = 1.0
    tenant_id: str = ""
    user_id: str = ""
    scope: str = "global"
    role: str = ""
    authority_level: int | None = None
    abstraction_level: int | None = None
    profile_revision: int | None = None
    supersedes: tuple[str, ...] = ()
    superseded_by: str | None = None
    invalidated_at: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self):
        if self.scope not in {"private", "tenant", "global"}:
            raise ValueError("scope must be private, tenant, or global")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0,1]")
        if not self.experience_id or not self.evidence_group_id or not self.source_event_id:
            raise ValueError("evidence identity fields must be non-empty")


@dataclass(frozen=True, slots=True)
class ExcludedEvidence:
    experience_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class AssessedEvidence:
    record: EvidenceRecordV2
    semantic_scores: Mapping[str, float]
    quality: float
    stance: str
    group_key: str

    def as_dict(self) -> dict[str, object]:
        return {
            "experience_id": self.record.experience_id,
            "group_key": self.group_key,
            "stance": self.stance,
            "quality": self.quality,
            "semantic_scores": dict(self.semantic_scores),
            "source": self.record.provenance.as_dict(),
            "content": self.record.content,
        }


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    support_score: float
    challenge_score: float
    conflict_score: float
    independent_support_count: int
    independent_challenge_count: int
    evidence_quality: float
    decision: Decision
    reasons: tuple[str, ...]
    included: tuple[AssessedEvidence, ...] = ()
    excluded: tuple[ExcludedEvidence, ...] = ()
    missing_state: tuple[str, ...] = ()
    latency_ms: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision.value,
            "support_score": self.support_score,
            "challenge_score": self.challenge_score,
            "conflict_score": self.conflict_score,
            "independent_support_count": self.independent_support_count,
            "independent_challenge_count": self.independent_challenge_count,
            "evidence_quality": self.evidence_quality,
            "reasons": list(self.reasons),
            "missing_state": list(self.missing_state),
            "included": [item.as_dict() for item in self.included],
            "excluded": [{"experience_id": item.experience_id, "reason": item.reason} for item in self.excluded],
            "latency_ms": self.latency_ms,
        }


@dataclass(frozen=True, slots=True)
class GovernedMemoryFrame:
    schema_version: int
    mode: str
    conversation_id: str
    current_state: SemanticState
    assessment: EvidenceAssessment
    perspective: Mapping[str, object] = field(default_factory=dict)
    open_loops: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    retrieved_candidates: int = 0
    generated_at: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "conversation_id": self.conversation_id,
            "current_state": self.current_state.as_storage(),
            "perspective": dict(self.perspective),
            "open_loops": list(self.open_loops),
            "constraints": list(self.constraints),
            "retrieved_candidates": self.retrieved_candidates,
            "assessment": self.assessment.as_dict(),
            "generated_at": self.generated_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))

    def to_prompt_context(self, *, max_chars: int = 12_000) -> str:
        lines = [
            "HNG GOVERNED MEMORY FRAME",
            f"DECISION: {self.assessment.decision.value}",
            "REASONS:",
            *(f"- {reason}" for reason in self.assessment.reasons),
        ]
        if self.perspective:
            lines.extend(("KNOWN USER PERSPECTIVE", json.dumps(dict(self.perspective), sort_keys=True)))
        if self.open_loops:
            lines.extend(("OPEN LOOPS", *(f"- {value}" for value in self.open_loops)))
        if self.constraints:
            lines.extend(("CONSTRAINTS", *(f"- {value}" for value in self.constraints)))
        supporting = [item for item in self.assessment.included if item.stance == "support"]
        challenging = [item for item in self.assessment.included if item.stance == "challenge"]
        if supporting:
            lines.append("SUPPORTING HISTORICAL EVIDENCE")
            lines.extend(f"- {item.record.content} [source={item.record.provenance.source_id}]" for item in supporting)
        if challenging:
            lines.append("CONTRADICTING HISTORICAL EVIDENCE")
            lines.extend(f"- {item.record.content} [source={item.record.provenance.source_id}]" for item in challenging)
        if self.assessment.excluded:
            lines.append("EXCLUDED OR SUPERSEDED EVIDENCE")
            lines.extend(f"- {item.experience_id}: {item.reason}" for item in self.assessment.excluded[:20])
        return "\n".join(lines)[:max_chars]
