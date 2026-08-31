from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Callable, Iterable, Mapping, Protocol

from .control import HNGMemory
from .governance import EvidenceKind, EvidenceProvenance, GovernedMemoryFrame, TemporalValidity
from .semantic import SemanticState, SemanticValue


class HDCTurnEncoder(Protocol):
    def __call__(self, value: object, *, prior_state: SemanticState,
                 working_context: Mapping[str, object],
                 perspective: Mapping[str, object] | None,
                 governed_frame: GovernedMemoryFrame) -> SemanticState: ...


@dataclass(slots=True)
class HDCAssistantAdapter:
    """Native HDC bridge with no embedding API or LLM dependency."""

    memory: HNGMemory
    encoder: HDCTurnEncoder

    def encode_turn(self, value: object, *, conversation_id: str, query: SemanticState | None = None,
                    lexical_query: str = "") -> SemanticState:
        working = self.memory.working_state(str(conversation_id))
        profile = self.memory.effective_profile(str(conversation_id))
        frame = self.memory.context(str(conversation_id), query=query or working.prior_semantic_state,
                                    lexical_query=lexical_query)
        context = {
            "open_loops": working.open_loops, "constraints": working.constraints,
            "commitments": tuple(item.as_dict() for item in working.commitments),
            "corrections": tuple(item.as_dict() for item in working.corrections),
            "recent_exact_turns": tuple(item.as_dict() for item in working.recent_turns),
            "active_episode": working.active_episode,
            "current_goal": working.current_goal,
            "current_facts": working.current_facts,
            "perspective": None if profile is None else profile.as_dict(),
            "supporting_evidence": tuple(item.as_dict() for item in frame.assessment.included if item.stance == "support"),
            "contradicting_evidence": tuple(item.as_dict() for item in frame.assessment.included if item.stance == "challenge"),
            "superseded_evidence": tuple({"experience_id": item.experience_id, "reason": item.reason}
                                         for item in frame.assessment.excluded if "supersed" in item.reason),
            "decision": frame.assessment.decision.value,
        }
        signature = inspect.signature(self.encoder)
        accepts_kwargs = any(item.kind is inspect.Parameter.VAR_KEYWORD
                             for item in signature.parameters.values())
        optional = {"perspective": None if profile is None else profile.as_dict(),
                    "governed_frame": frame}
        kwargs = {name: item for name, item in optional.items()
                  if accepts_kwargs or name in signature.parameters}
        return self.encoder(value, prior_state=working.prior_semantic_state,
                            working_context=context, **kwargs)  # type: ignore[arg-type]

    def encode_action(self, value: object, *, conversation_id: str) -> SemanticValue:
        state = self.encode_turn(value, conversation_id=str(conversation_id))
        if "action" not in state.fields:
            raise ValueError("HDC adapter did not emit an action head")
        return state.fields["action"]


@dataclass(slots=True)
class LLMAssistantAdapter:
    memory: HNGMemory
    max_context_chars: int = 12_000
    max_context_tokens: int = 3_000

    def context(self, *, conversation_id: str, query: SemanticState | None = None,
                lexical_query: str = "") -> str:
        frame = self.memory.context(str(conversation_id), query=query, lexical_query=lexical_query)
        with self.memory.profiler.measure("frame_rendering"):
            return frame.to_prompt_context(max_chars=self.max_context_chars, max_tokens=self.max_context_tokens)

    def action_context(self, *, conversation_id: str, state: SemanticState,
                       action: SemanticValue, lexical_query: str = "") -> str:
        frame = self.memory.evaluate_action(state, action, conversation_id=str(conversation_id), lexical_query=lexical_query)
        with self.memory.profiler.measure("frame_rendering"):
            return frame.to_prompt_context(max_chars=self.max_context_chars, max_tokens=self.max_context_tokens)


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text: str
    source_uri: str
    score: float = 0.0
    metadata: Mapping[str, object] = None  # type: ignore[assignment]


class RAGEvidenceAdapter:
    """Turns conventional BM25/dense/HDC chunks into governed, versioned evidence."""

    def __init__(self, memory: HNGMemory):
        self.memory = memory

    def ingest_chunks(self, chunks: Iterable[RetrievedChunk], *, semantics: Callable[[RetrievedChunk], SemanticState],
                      trust_score: float = 0.75, verified: bool = False,
                      environment_version: str = "") -> tuple[str, ...]:
        ids = []
        for chunk in chunks:
            record = self.memory.ingest_evidence(
                experience_id=f"chunk:{chunk.chunk_id}", source_event_id=f"document:{chunk.document_id}:{chunk.chunk_id}",
                evidence_group_id=f"document:{chunk.document_id}:{chunk.chunk_id}",
                content=chunk.text, semantics=semantics(chunk), kind=EvidenceKind.DOCUMENT_CLAIM,
                provenance=EvidenceProvenance("external_document", chunk.source_uri, trust_score, verified),
                validity=TemporalValidity(environment_version=environment_version),
                confidence=max(0.0, min(1.0, chunk.score if chunk.score else 1.0)),
                metadata={"document_id": chunk.document_id, "chunk_id": chunk.chunk_id, **dict(chunk.metadata or {})},
            )
            ids.append(record.experience_id)
        return tuple(ids)

