from __future__ import annotations

import numpy as np

from hngfrontier import (DocumentChunk, EvidenceProvenance, ReferenceBinaryRetriever,
                         HNGMemory, HybridDocumentRetriever, SemanticState, SemanticValue)


def test_top_level_document_index_restores_from_evidence_truth(tmp_path):
    vector = SemanticValue.hdc(np.ones(256, dtype=np.int8), dimension=256)
    def open_memory():
        return HNGMemory(tmp_path, semantic_backend="reference-hng",
                         document_retriever=HybridDocumentRetriever(
                             ReferenceBinaryRetriever()))
    with open_memory() as memory:
        memory.ingest_document_chunk(
            DocumentChunk("c1", "d1", "signed launch policy", "doc://d1", vector, {"region": "us"}),
            semantics=SemanticState({"topic": vector}),
            provenance=EvidenceProvenance("external_document", "doc://d1", .9, True))
        memory.documents.rebuild()
    with open_memory() as memory:
        result = memory.search_documents("launch", semantic=vector, filters={"region": "us"})
        assert result and result[0].chunk.chunk_id == "c1"


def test_failed_evidence_commit_does_not_leave_searchable_document(tmp_path):
    vector = SemanticValue.hdc(np.ones(256, dtype=np.int8), dimension=256)
    with HNGMemory(tmp_path, semantic_backend="reference-hng") as memory:
        chunk = DocumentChunk("same", "d1", "first", "doc://d1")
        memory.ingest_document_chunk(chunk, semantics=SemanticState({"topic": vector}),
                                     provenance=EvidenceProvenance("external_document", "d1", .9, True))
        try:
            memory.ingest_document_chunk(DocumentChunk("same", "d2", "ghost", "doc://d2"),
                semantics=SemanticState({"topic": vector}),
                provenance=EvidenceProvenance("external_document", "d2", .9, True))
        except Exception:
            pass
        assert memory.search_documents("ghost") == ()
