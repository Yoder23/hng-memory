# HNG Frontier 0.4 — HDC-native document memory

HNG document memory treats a long document as a sequence of **native semantic states**, not as a bag of chunks that must later be reinterpreted by an LLM.

The document semantic adapter is application-owned. HNG never calls an LLM to understand text. For each unit, the adapter may emit independent HDC heads such as:

- `topic` — semantic region/theme;
- `claim` — proposition content;
- `entity` — involved entities;
- `evidence` — evidentiary content;
- `role` — rhetorical/evidence role such as caveat, contradiction, conclusion, procedure, warning, etc.

## Ingestion

```text
raw document
    |
    v
application HDC interpreter
    |
    +-- topic HV
    +-- claim HV
    +-- entity HV
    +-- evidence HV
    +-- role HV
    |
    v
HDCDocumentMemory
```

`DocumentSemanticAdapter` receives the previous unit's native heads, so a sequence-aware HDC interpreter can encode discourse continuity without reconstructing it from text.

## LLM-free synopsis

`summarize_document()` performs:

1. ordered HDC boundary detection from adjacent `topic` states (or known section structure);
2. majority bundling into semantic-segment prototypes;
3. majority bundling into document-level head prototypes;
4. central representative selection per semantic segment;
5. optional rare/priority evidence detection through HDC `role` queries;
6. bounded novelty fill;
7. exact source/provenance retention.

The output is a `DocumentSummaryFrame` containing:

- document-level HDC heads;
- segment-level HDC prototypes;
- representative source evidence;
- rare/caveat/contradiction evidence;
- exact source slots.

An HDC assistant consumes `frame.to_hdc_context()` directly. An LLM or human-facing application can use `frame.to_context_text()`, which is an extractive rendering of the same evidence. No generated language is needed to create either representation.

## Why this differs from ordinary RAG

A flat RAG query such as "summarize this document" provides almost no semantic cue for comprehensive coverage. Top-k relevance therefore tends to over-sample dominant themes. HNG's synopsis objective is **coverage + structure + exception preservation**, not query similarity.

This is closer in objective to hierarchical systems such as RAPTOR and GraphRAG, but those systems create higher-level summaries using LLMs. HNG's alpha tests whether the hierarchy itself can be represented and compressed in native HDC state, leaving language generation optional.

## Current evidence

Synthetic documentation benchmark (32 documents, 8,960 HDC units, 16 semantic themes/document, 40-unit evidence budget):

| Method | Theme coverage | Key-claim recall | Priority evidence | Contradictions | Median |
|---|---:|---:|---:|---:|---:|
| HNG HDC synopsis | 100% | 98.0% | 100% | 100% | ~23.6 ms |
| Naive semantic top-k | 21.7% | 21.7% | 14.2% | 15.6% | ~0.10 ms |
| Importance-aware top-k | 44.1% | 25.0% | 63.7% | 65.1% | ~0.05 ms |
| MMR | 100% | 57.2% | 99.0% | 100% | ~1.40 ms |
| Oracle KMeans (`k=16`) | 100% | 100% | 100% | 100% | ~57.5 ms |

HNG inferred the 16 semantic regions from ordered HDC continuity with boundary F1=1.00; the KMeans baseline was explicitly given the oracle region count.

A separate 8,960-unit / 128-theme single-document test produced 100% theme/key/priority coverage in ~440 ms with a 140-unit synopsis. This is an ingestion/synopsis operation rather than a per-token generation loop.

These are **synthetic semantic-geometry results**, not claims of state-of-the-art natural-language summarization. The publication gate is evaluation on public long-document datasets (e.g. BillSum/GovReport) using a fixed HDC text/interpreter front end and matched extractive/hierarchical baselines.

## Corpus-wide recall

`query_corpus()` / `query_corpus_adaptive()` search all ingested documents when the caller does not already know which source contains the answer. Returned evidence keeps the source `document_id`, section identity, ordinal and raw source text, so global recall never discards provenance.

This is the document-memory analogue of cross-chat episodic recall: a document can be semantically internalized once, then become part of the assistant's persistent knowledge/evidence plane rather than being re-uploaded and re-chunked for every conversation.
