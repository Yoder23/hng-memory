from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .retrieval import BM25Retriever, RetrievalHit
from .semantic import SemanticValue


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    text: str
    source_uri: str
    semantic: SemanticValue | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocumentSearchResult:
    chunk: DocumentChunk
    score: float
    channels: tuple[str, ...]


class HybridDocumentRetriever:
    """Production document path: BM25 + optional mature semantic provider + exact metadata."""

    def __init__(self, semantic_provider=None, *, rrf_k: int = 60):
        self.lexical = BM25Retriever()
        self.semantic = semantic_provider
        self.rrf_k = int(rrf_k)
        self._chunks: dict[str, DocumentChunk] = {}

    def ingest(self, chunk: DocumentChunk) -> None:
        self._chunks[chunk.chunk_id] = chunk
        self.lexical.add(chunk.chunk_id, chunk.text)
        if self.semantic is not None and chunk.semantic is not None:
            self.semantic.add(chunk.chunk_id, chunk.semantic)

    def rebuild(self) -> None:
        if self.semantic is not None:
            self.semantic.rebuild()

    def search(self, query: str, *, semantic: SemanticValue | None = None, top_k: int = 10,
               filters: Mapping[str, object] | None = None) -> tuple[DocumentSearchResult, ...]:
        allowed = {
            chunk_id for chunk_id, chunk in self._chunks.items()
            if all(chunk.metadata.get(key) == value for key, value in dict(filters or {}).items())
        }
        channels: dict[str, set[str]] = {}
        scores: dict[str, float] = {}
        lexical_hits = self.lexical.search(query, top_k=max(20, top_k * 4), allowed_ids=allowed)
        for rank, hit in enumerate(lexical_hits, start=1):
            scores[hit.evidence_id] = scores.get(hit.evidence_id, 0.0) + 1.0 / (self.rrf_k + rank)
            channels.setdefault(hit.evidence_id, set()).add("bm25")
        if self.semantic is not None and semantic is not None:
            semantic_hits = self.semantic.search(semantic, top_k=max(20, top_k * 4), allowed_ids=allowed)
            for rank, hit in enumerate(semantic_hits, start=1):
                scores[hit.evidence_id] = scores.get(hit.evidence_id, 0.0) + 1.0 / (self.rrf_k + rank)
                channels.setdefault(hit.evidence_id, set()).add(hit.provider)
        ranked = sorted(scores, key=lambda key: (-scores[key], key))[:top_k]
        return tuple(DocumentSearchResult(self._chunks[key], scores[key], tuple(sorted(channels[key]))) for key in ranked)
