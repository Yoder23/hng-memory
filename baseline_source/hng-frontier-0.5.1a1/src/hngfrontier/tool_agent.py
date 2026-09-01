from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .control import HNGMemory
from .governance import Decision, EvidenceProvenance, GovernedMemoryFrame, TemporalValidity
from .semantic import SemanticState, SemanticValue
from .shadow_v2 import GovernedShadowEvaluator


@dataclass(frozen=True, slots=True)
class ToolAction:
    tool: str
    action: str
    semantic_action: SemanticValue
    arguments: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ToolAssessment:
    proposal: ToolAction
    frame: GovernedMemoryFrame
    execute: bool
    blocked: bool
    reasons: tuple[str, ...]


class ToolAgentAdapter:
    """Governed preflight and outcome feedback; execution remains caller-owned."""

    def __init__(self, memory: HNGMemory, rollout: GovernedShadowEvaluator):
        self.memory = memory
        self.rollout = rollout

    def assess(self, proposal: ToolAction, *, conversation_id: str,
               state: SemanticState) -> ToolAssessment:
        frame = self.memory.evaluate_action(state, proposal.semantic_action, conversation_id=conversation_id,
                                            lexical_query=f"{proposal.tool} {proposal.action}")
        decision = self.rollout.decide(frame)
        return ToolAssessment(proposal, frame, not decision.blocks, decision.blocks, frame.assessment.reasons)

    def execute(self, proposal: ToolAction, *, conversation_id: str, state: SemanticState,
                executor: Callable[[str, Mapping[str, object]], object],
                outcome_semantics: Callable[[object], SemanticValue], provenance: EvidenceProvenance,
                validity: TemporalValidity | None = None, tenant_id: str = "", user_id: str = "",
                scope: str = "global", role: str = "", authority_level: int | None = None,
                abstraction_level: int | None = None,
                profile_revision: int | None = None) -> object | None:
        assessment = self.assess(proposal, conversation_id=conversation_id, state=state)
        if assessment.blocked:
            self.rollout.log(assessment.frame, assistant_action=f"{proposal.tool}:{proposal.action}",
                             outcome={"executed": False, "reason": "hard_gate"})
            return None
        result = executor(proposal.action, proposal.arguments)
        next_state = outcome_semantics(result)
        success = not (isinstance(result, Mapping) and result.get("success") is False)
        self.memory.remember_transition(
            conversation_id=conversation_id, state=state, action=proposal.semantic_action, next_state=next_state,
            outcome=str(result), outcome_score=1.0 if success else -1.0, provenance=provenance,
            content=f"tool={proposal.tool} action={proposal.action} outcome={result}",
            metadata={"tool": proposal.tool, "action": proposal.action, "arguments": dict(proposal.arguments)},
            validity=validity, tenant_id=tenant_id, user_id=user_id, scope=scope, role=role,
            authority_level=authority_level, abstraction_level=abstraction_level,
            profile_revision=profile_revision)
        self.rollout.log(assessment.frame, assistant_action=f"{proposal.tool}:{proposal.action}",
                         outcome={"executed": True, "success": success, "result": str(result)})
        return result
