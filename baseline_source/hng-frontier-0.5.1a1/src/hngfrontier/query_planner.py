from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .semantic import EvidenceRequirement


class QueryIntent(str, Enum):
    RECALL = "recall"
    ACTION_EVALUATION = "action_evaluation"
    ROLE_SENSITIVE_RECOMMENDATION = "role_sensitive_recommendation"
    PROCEDURE = "procedure"
    DOCUMENT_EVIDENCE = "document_evidence"


@dataclass(frozen=True, slots=True)
class QueryPlanV2:
    intent: QueryIntent
    requirement: EvidenceRequirement
    top_k: int = 32
    candidate_k: int = 128
    critical: bool = False
    required_profile_fields: tuple[str, ...] = ()


class QueryPlanner:
    def __init__(self, overrides: Mapping[QueryIntent, QueryPlanV2] | None = None):
        self._plans = {
            QueryIntent.RECALL: QueryPlanV2(QueryIntent.RECALL, EvidenceRequirement(("state",), min_similarity={"state": 0.75})),
            QueryIntent.ACTION_EVALUATION: QueryPlanV2(
                QueryIntent.ACTION_EVALUATION,
                EvidenceRequirement(("state", "goal", "sequence", "action"), optional_heads=("entity",),
                                    min_similarity={"state": 0.80, "goal": 0.80, "sequence": 0.90, "action": 0.97},
                                    strict_action_floor=0.97, require_environment_version=False),
                candidate_k=32, critical=True, required_profile_fields=("role", "authority_level"),
            ),
            QueryIntent.ROLE_SENSITIVE_RECOMMENDATION: QueryPlanV2(
                QueryIntent.ROLE_SENSITIVE_RECOMMENDATION,
                EvidenceRequirement(("state",), optional_heads=("goal", "expertise", "priority"), require_profile=True),
                critical=True, required_profile_fields=("role", "authority_level"),
            ),
            QueryIntent.PROCEDURE: QueryPlanV2(
                QueryIntent.PROCEDURE,
                EvidenceRequirement(("goal", "environment_version"), min_similarity={"goal": 0.80}),
            ),
            QueryIntent.DOCUMENT_EVIDENCE: QueryPlanV2(
                QueryIntent.DOCUMENT_EVIDENCE,
                EvidenceRequirement((), optional_heads=("topic", "claim", "entity")),
            ),
        }
        self._plans.update(dict(overrides or {}))

    def plan(self, intent: QueryIntent | str) -> QueryPlanV2:
        return self._plans[QueryIntent(intent)]
