# RAG integration

## Position

HNG cooperates with RAG. BM25, dense search, HDC search, rerankers, and document hierarchies retrieve candidates. HNG decides whether retrieved information is valid, independent, trustworthy, current, actor-appropriate, and strong enough to influence behavior.

## Hybrid retrieval

```python
from hngfrontier import HybridDocumentRetriever, DocumentChunk

documents = HybridDocumentRetriever(semantic_provider=dense_or_hdc_provider)
documents.ingest(DocumentChunk(
    chunk_id="policy-27:4",
    document_id="policy-27",
    text="Database restarts require incident commander approval.",
    source_uri="s3://policies/27#4",
    semantic=encoded_chunk,
    metadata={"tenant": "acme", "policy_version": "27"},
))
documents.rebuild()
hits = documents.search(
    "may I restart the database?",
    semantic=encoded_query,
    filters={"tenant": "acme", "policy_version": "27"},
)
```

The stack uses BM25 plus optional semantic retrieval and reciprocal-rank fusion. Metadata filtering is exact.

## Persist validated chunks as evidence

```python
from hngfrontier import RAGEvidenceAdapter, RetrievedChunk

adapter = RAGEvidenceAdapter(memory)
adapter.ingest_chunks(
    [RetrievedChunk(
        chunk_id=hit.chunk.chunk_id,
        document_id=hit.chunk.document_id,
        text=hit.chunk.text,
        source_uri=hit.chunk.source_uri,
        score=min(1.0, hit.score * 60),
        metadata=hit.chunk.metadata,
    ) for hit in hits],
    semantics=encode_claim,
    trust_score=0.85,
    verified=True,
    environment_version="prod-27",
)
```

Do not mark arbitrary web or model-generated chunks verified. Document trust should reflect source authenticity and extraction quality.

## Hierarchy

The old custom boundary detector remains compatibility-only. For long documents choose a hierarchy from mature prior art when it improves the target workload:

- RAPTOR for recursively summarized trees;
- GraphRAG for entity/community global synthesis;
- SVD-RAG-class deterministic hierarchy when generator-free construction is important.

HNG's role begins after retrieval: persist claims with source spans, versions, contradiction/supersession links, and evidence type. Verified claims may optionally be encoded into native HDC memory.

## Fair evaluation

Compare BM25, semantic, hybrid, and hybrid + HNG under the same evidence/token budget and reader model. The relevant metrics are stale-answer rate, contradiction detection, provenance accuracy, unsafe support, personalization violations, and task success—not whether HNG outranks BM25 lexically.

