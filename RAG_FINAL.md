# RAG and documents

The top-level `HNGMemory` API exposes document chunk ingestion and search. `HybridDocumentRetriever` provides BM25, an optional semantic provider, reciprocal-rank fusion, exact metadata filters, and document/chunk conversion into provenance-bearing `DOCUMENT_CLAIM` evidence. HNG then governs validity, contradiction, supersession, trust, and actor applicability.

The official QMSum closure run confirms that HNG should not replace lexical retrieval: BM25 span hit@5 was 64.93%, the deterministic HDC hybrid 55.22%, and governed candidate routing 55.97% over 134 queries. The loss is preserved in `closure_eval/raw/QMSUM_GOVERNED_20.json`.

RAPTOR, Microsoft GraphRAG, and SVD-RAG remain external hierarchy providers. RAPTOR recursively clusters and summarizes a tree; GraphRAG builds entity/relationship/community structures and supports local/global/DRIFT query modes; SVD-RAG is an emerging tree-organized SVD approach. HNG should consume their returned chunks/claims through `DocumentChunk` or `RAGEvidenceAdapter`, retaining their source IDs and versions. It does not reimplement their hierarchy or require their LLM indexing cost.

References: [RAPTOR (ICLR 2024)](https://openreview.net/forum?id=GN921JHCRw), [Microsoft GraphRAG indexing](https://microsoft.github.io/graphrag/index/overview/), [GraphRAG query methods](https://microsoft.github.io/graphrag/query/overview/), and [SVD-RAG](https://arxiv.org/abs/2607.10316).

