from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Protocol

from .control import HNGMemory
from .governance import EvidenceKind, EvidenceProvenance, GovernedMemoryFrame, TemporalValidity
from .semantic import SemanticState, SemanticValue


class HDCTurnEncoder(Protocol):
    def __call__(self, value: object, *, prior_state: SemanticState,
                 working_context: Mapping[str, object]) -> SemanticState: ...


@dataclass(slots=True)
class HDCAssistantAdapter:
    """Native HDC bridge with no embedding API or LLM dependency."""

    memory: HNGMemory
    encoder: HDCTurnEncoder

    def encode_turn(self, value: object, *, conversation_id: str) -> SemanticState:
        state, open_loops, constraints = self.memory.store.working_state(str(conversation_id))
        profile = self.memory.effective_profile(str(conversation_id))
        return self.encoder(
            value, prior_state=state,
            working_context={
                "open_loops": open_loops, "constraints": constraints,
                "perspective": None if profile is None else profile.as_dict(),
            },
        )

    def encode_action(self, value: object, *, conversation_id: str) -> SemanticValue:
        state = self.encode_turn(value, conversation_id=str(conversation_id))
        if "action" not in state.fields:
            raise ValueError("HDC adapter did not emit an action head")
        return state.fields["action"]


@dataclass(slots=True)
class LLMAssistantAdapter:
    memory: HNGMemory
    max_context_chars: int = 12_000

    def context(self, *, conversation_id: str, query: SemanticState | None = None,
                lexical_query: str = "") -> str:
        frame = self.memory.context(str(conversation_id), query=query, lexical_query=lexical_query)
        return frame.to_prompt_context(max_chars=self.max_context_chars)

    def action_context(self, *, conversation_id: str, state: SemanticState,
                       action: SemanticValue, lexical_query: str = "") -> str:
        frame = self.memory.evaluate_action(state, action, conversation_id=str(conversation_id), lexical_query=lexical_query)
        return frame.to_prompt_context(max_chars=self.max_context_chars)


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

