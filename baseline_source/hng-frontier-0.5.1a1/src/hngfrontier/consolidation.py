from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .governance import EvidenceRecordV2


@dataclass(frozen=True, slots=True)
class ConsolidatedPattern:
    pattern_id: str
    evidence_group_id: str
    source_experience_ids: tuple[str, ...]
    independent_source_event_ids: tuple[str, ...]
    support_count: int
    challenge_count: int
    mean_confidence: float
    reversible: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "pattern_id": self.pattern_id, "evidence_group_id": self.evidence_group_id,
            "source_experience_ids": list(self.source_experience_ids),
            "independent_source_event_ids": list(self.independent_source_event_ids),
            "support_count": self.support_count, "challenge_count": self.challenge_count,
            "mean_confidence": self.mean_confidence, "reversible": self.reversible,
        }


class EvidenceConsolidator:
    """Build reversible retrieval summaries without deleting or multiplying raw evidence."""

    def consolidate(self, records: Iterable[EvidenceRecordV2]) -> tuple[ConsolidatedPattern, ...]:
        groups: dict[str, list[EvidenceRecordV2]] = {}
        for record in records:
            groups.setdefault(record.evidence_group_id, []).append(record)
        output = []
        for group_id, values in sorted(groups.items()):
            independent: dict[str, EvidenceRecordV2] = {}
            for record in values:
                previous = independent.get(record.source_event_id)
                if previous is None or record.confidence > previous.confidence:
                    independent[record.source_event_id] = record
            unique = tuple(independent.values())
            output.append(ConsolidatedPattern(
                pattern_id=f"pattern:{group_id}", evidence_group_id=group_id,
                source_experience_ids=tuple(sorted(record.experience_id for record in values)),
                independent_source_event_ids=tuple(sorted(independent)),
                support_count=sum(record.outcome_score > 0 for record in unique),
                challenge_count=sum(record.outcome_score < 0 for record in unique),
                mean_confidence=sum(record.confidence for record in unique) / max(1, len(unique)),
            ))
        return tuple(output)

