from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

from .governance import utc_now_iso
from .semantic import SemanticState, SemanticValue


@dataclass(frozen=True, slots=True)
class ExactTurn:
    turn_id: str
    speaker: str
    content: str
    semantics: SemanticState = field(default_factory=SemanticState)
    created_at: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, object]:
        return {"turn_id": self.turn_id, "speaker": self.speaker, "content": self.content,
                "semantics": self.semantics.as_storage(), "created_at": self.created_at}

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ExactTurn":
        return cls(str(value["turn_id"]), str(value["speaker"]), str(value["content"]),
                   SemanticState.from_storage(value.get("semantics")), str(value["created_at"]))


@dataclass(frozen=True, slots=True)
class WorkingCorrection:
    correction_id: str
    target: str
    replacement: str
    reason: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, object]:
        return {"correction_id": self.correction_id, "target": self.target,
                "replacement": self.replacement, "reason": self.reason, "created_at": self.created_at}


@dataclass(frozen=True, slots=True)
class Commitment:
    commitment_id: str
    text: str
    status: str = "open"
    due_at: str | None = None
    created_at: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, object]:
        return {"commitment_id": self.commitment_id, "text": self.text, "status": self.status,
                "due_at": self.due_at, "created_at": self.created_at}


@dataclass(frozen=True, slots=True)
class DeterministicWorkingState:
    conversation_id: str
    prior_semantic_state: SemanticState = field(default_factory=SemanticState)
    recent_turns: tuple[ExactTurn, ...] = ()
    corrections: tuple[WorkingCorrection, ...] = ()
    commitments: tuple[Commitment, ...] = ()
    open_loops: tuple[str, ...] = ()
    active_episode: str = ""
    current_goal: SemanticValue | None = None
    current_facts: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    revision: int = 0
    updated_at: str = field(default_factory=utc_now_iso)

    def with_turn(self, turn: ExactTurn, *, limit: int = 32) -> "DeterministicWorkingState":
        return replace(self, recent_turns=(self.recent_turns + (turn,))[-max(1, limit):],
                       prior_semantic_state=turn.semantics, revision=self.revision + 1, updated_at=utc_now_iso())

    def as_dict(self) -> dict[str, object]:
        return {
            "conversation_id": self.conversation_id,
            "prior_semantic_state": self.prior_semantic_state.as_storage(),
            "recent_turns": [value.as_dict() for value in self.recent_turns],
            "corrections": [value.as_dict() for value in self.corrections],
            "commitments": [value.as_dict() for value in self.commitments],
            "open_loops": list(self.open_loops), "active_episode": self.active_episode,
            "current_goal": None if self.current_goal is None else self.current_goal.as_storage(),
            "current_facts": list(self.current_facts), "constraints": list(self.constraints),
            "revision": self.revision, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "DeterministicWorkingState":
        return cls(
            conversation_id=str(value.get("conversation_id") or ""),
            prior_semantic_state=SemanticState.from_storage(value.get("prior_semantic_state")),
            recent_turns=tuple(ExactTurn.from_dict(item) for item in value.get("recent_turns", [])),
            corrections=tuple(WorkingCorrection(**dict(item)) for item in value.get("corrections", [])),
            commitments=tuple(Commitment(**dict(item)) for item in value.get("commitments", [])),
            open_loops=tuple(str(x) for x in value.get("open_loops", [])),
            active_episode=str(value.get("active_episode") or ""),
            current_goal=None if value.get("current_goal") is None else SemanticValue.from_storage(value["current_goal"]),
            current_facts=tuple(str(x) for x in value.get("current_facts", [])),
            constraints=tuple(str(x) for x in value.get("constraints", [])),
            revision=int(value.get("revision") or 0), updated_at=str(value.get("updated_at") or utc_now_iso()),
        )
