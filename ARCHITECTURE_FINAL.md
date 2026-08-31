# HNG Frontier 0.7 architecture

HNG is an evidence-governed memory and control layer. SQLite records and deterministic working state are authoritative; retrieval indexes are replaceable derived state.

```mermaid
flowchart TD
    A[HDC / LLM / RAG / tool agent] --> W[Exact working state]
    W --> Q[Intent-specific query plan]
    Q --> R{Candidate providers}
    R --> F[FAISS binary or dense]
    R --> B[BM25]
    R --> U[USearch Hamming]
    R --> X[External hierarchy / graph retriever]
    F --> G[Evidence governance]
    B --> G
    U --> G
    X --> G
    G --> V[Access, validity, exact floors, trust,
    independence, actor policy, supersession]
    V --> M[GovernedMemoryFrame]
    M --> D[SUPPORT / CHALLENGE / CONFLICTED /
    INSUFFICIENT_* / SUPERSEDED / UNTRUSTED]
```

## Persistence and coherent queries

```mermaid
sequenceDiagram
    participant C as Client
    participant H as HNGMemory
    participant S as SQLite truth
    participant I as Derived indexes
    C->>H: query generation g
    H->>S: read generation + data_version
    H->>I: retrieve candidates
    H->>S: read exact records and govern
    H->>S: verify generation + data_version
    alt unchanged
        H-->>C: coherent frame
    else changed concurrently
        H->>H: clear caches/rebuild providers/retry
    end
```

Writes commit evidence before advancing the generation. A process killed before commit leaves no record. A process killed after commit may lose derived index state, but reopen or generation mismatch rebuilds it from SQLite. Raw evidence is never deleted by consolidation.

## Integration boundary

```mermaid
flowchart LR
    H[HNG owns] --> H1[working state]
    H --> H2[transition/outcome ledger]
    H --> H3[trust and provenance]
    H --> H4[actor applicability]
    H --> H5[abstention and reasons]
    E[External systems own] --> E1[language generation]
    E --> E2[embedding models]
    E --> E3[BM25 / ANN implementation]
    E --> E4[RAPTOR / GraphRAG / SVD-RAG hierarchy]
```

The automatic binary provider remains Flat below 50K and IVF above it. MultiHash and USearch are explicit modes: MultiHash is extremely fast on independent vectors but measured at 25.07 ms p50 on correlated leading-bit geometry versus IVF at 0.60 ms; USearch had weaker recall/build behavior on the evaluated HDC distribution.

