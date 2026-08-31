# Public benchmark protocol

HNG Frontier 0.4.0a1 is intentionally shipped with a public-data harness rather than treating synthetic semantic geometry as sufficient evidence for the broad research claim.

## QMSum

`benchmarks/qmsum_public_hdc.py` accepts the official QMSum `data/ALL/jsonl/test.jsonl` file and runs an end-to-end, non-neural HDC document benchmark.

```bash
python benchmarks/qmsum_public_hdc.py \
  /path/to/QMSum/data/ALL/jsonl/test.jsonl \
  --limit 20 \
  --dim 4096 \
  --budget 32 \
  --top-k 5 \
  --output benchmarks/QMSUM_PUBLIC.json
```

The included encoder is deliberately simple and deterministic: a bag of token and token-bigram HDC atoms. It does not use a transformer, embedding service, or LLM. This makes the protocol reproducible but also sets a conservative semantic ceiling relative to an application's real HDC interpreter.

Reported metrics:

- extractive ROUGE-1/2/L F1 against the human whole-meeting summary;
- annotated specific-query relevant-span hit@k;
- evidence budget;
- inferred semantic segment count;
- ingestion and synopsis latency.

The benchmark has **not been executed inside the ChatGPT build environment** because the full official dataset could not be materialized into the local runtime. No public QMSum score is claimed in this release.

## Long-document publication gate

For a paper-strength document claim, run at least:

- QMSum for general and query-conditioned meeting context;
- BillSum for long legal documents with human summaries;
- GovReport for substantially longer government reports;
- direct full-context/model baselines where source length permits;
- flat top-k, MMR, clustering/hierarchical extractive baselines;
- RAPTOR/GraphRAG-style hierarchical systems under clearly matched conditions where reproducible.

Measure both *rendered-summary* quality and *memory-frame* quality. The HNG-native object is the semantic/provenance frame, so ROUGE alone is insufficient: also measure coverage, exception/contradiction recall, source attribution, and downstream question answering from the frame.
