from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .governance import EvidenceRecordV2
from .profiles import EffectiveProfile
from .semantic import SemanticValue


class ProfileApplicability(str, Enum):
    APPLICABLE = "applicable"
    REDUCED_CONFIDENCE = "reduced_confidence"
    PERSPECTIVE_INCOMPATIBLE = "perspective_incompatible"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class ActorPolicyResult:
    applicability: ProfileApplicability
    confidence_factor: float
    reasons: tuple[str, ...]
    fuzzy_scores: Mapping[str, float]


class ActorPolicy:
    """Structured eligibility first; optional vectors only score genuinely fuzzy fields."""

    def evaluate(self, record: EvidenceRecordV2, profile: EffectiveProfile | None) -> ActorPolicyResult:
        if profile is None:
            return ActorPolicyResult(ProfileApplicability.APPLICABLE, 1.0, ("no active actor profile",), {})
        reasons: list[str] = []
        metadata = dict(record.metadata)
        snapshot = dict(metadata.get("profile_snapshot") or {})

        def value(name: str, default=None):
            field = profile.field(name)
            return default if field is None else field.value

        if record.role and value("role") is not None and record.role != str(value("role")):
            return ActorPolicyResult(ProfileApplicability.PERSPECTIVE_INCOMPATIBLE, 0.0,
                                     (f"role changed: {record.role}->{value('role')}",), {})
        authority = value("authority_level")
        if record.authority_level is not None and authority is not None and int(authority) < int(record.authority_level):
            return ActorPolicyResult(ProfileApplicability.PERSPECTIVE_INCOMPATIBLE, 0.0,
                                     ("active authority is below evidence requirement",), {})
        required_permissions = set(map(str, metadata.get("required_permissions") or ()))
        active_permissions = set(map(str, value("permissions", ()) or ()))
        missing_permissions = sorted(required_permissions - active_permissions)
        if missing_permissions:
            return ActorPolicyResult(ProfileApplicability.PERSPECTIVE_INCOMPATIBLE, 0.0,
                                     ("missing permissions: " + ",".join(missing_permissions),), {})
        responsibility = str(metadata.get("responsibility_scope") or "")
        active_responsibility = str(value("responsibility_scope", "") or "")
        factor = 1.0
        if responsibility and active_responsibility and responsibility != active_responsibility:
            factor *= 0.70; reasons.append("responsibility scope changed")
        active_abstraction = value("abstraction_level")
        if record.abstraction_level is not None and active_abstraction is not None:
            delta = abs(int(record.abstraction_level) - int(active_abstraction))
            if delta > 2:
                return ActorPolicyResult(ProfileApplicability.PERSPECTIVE_INCOMPATIBLE, 0.0,
                                         (f"abstraction mismatch delta={delta}",), {})
            if delta:
                factor *= 0.85 if delta == 1 else 0.65; reasons.append(f"abstraction mismatch delta={delta}")
        fuzzy: dict[str, float] = {}
        for name in ("expertise", "priority"):
            field = profile.field(name)
            historical = record.semantics.fields.get(name)
            if field is None or historical is None:
                continue
            current = field.value if isinstance(field.value, SemanticValue) else SemanticValue.structured(field.value)
            score = historical.exact_similarity(current); fuzzy[name] = score
            if score < 0.5:
                factor *= 0.70; reasons.append(f"fuzzy {name} changed ({score:.3f})")
        if record.profile_revision is not None and record.profile_revision != profile.profile_revision:
            if snapshot:
                changed = [name for name, old in snapshot.items() if value(name) != old]
                if changed:
                    # Structured eligibility checks above decide whether a revision is incompatible.
                    # A compatible authority increase or capability-preserving edit remains usable,
                    # but is explicitly discounted and audited rather than rewriting history.
                    factor *= 0.80; reasons.append("profile revision re-evaluated: " + ",".join(changed))
            else:
                factor *= 0.85; reasons.append("profile revision changed without full snapshot")
        applicability = ProfileApplicability.APPLICABLE if factor >= 0.95 else ProfileApplicability.REDUCED_CONFIDENCE
        return ActorPolicyResult(applicability, factor, tuple(reasons or ("actor policy matched",)), fuzzy)
