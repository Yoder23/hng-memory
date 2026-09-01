# Preserved failures and negative results

This log is append-only in substance: later fixes may add resolution notes, but must not erase the
original observation or raw artifact.

## Baseline reproduction setup failures

1. The first full pytest baseline invocation omitted the nested package Python path. The unchanged
   code passed 94/94 on the corrected invocation. Both attempts are retained.
2. The first performance-profile invocation lacked the untracked FAISS vendor path. The unchanged
   code passed on retry. Both attempts are retained.
3. The first QMSum invocation had the same vendor-path setup defect. The unchanged code passed on
   retry. Both attempts are retained.

These are harness/dependency failures, not product-code failures.

## Missing release producers

The shipped REAL_HDC_ASSISTANT_ABLATION.json and BEHAVIORAL_GOVERNANCE.json have no producer
scripts in the frozen release. They are marked SHIPPED_ONLY_NO_PRODUCER_SCRIPT and are not counted
as freshly reproduced behavioral evidence.

## Real HDC gate blocked

No production HDC assistant, trained interpreter checkpoint or real trace corpus is available.
Prototype code without a trained checkpoint is not substituted. Therefore no real HDC HNG-off/on
claim exists.

## Adversarial duplicate-boundary loss

HNG returns conflicted rather than the frozen expected challenge for all 25 duplicate_attack cases
after correctly reducing six copies to one independent support event against two independent
challenges. Artifact: fixed_candidate/raw/deterministic_events.jsonl.

The same failure occurs in StrongStructuredBaseline and propagates through the fixed 27B model on
all three evaluated holdout variants. The expectation remains unchanged.

## Strong simple baseline tie

StrongStructuredBaseline exactly ties HNG on deterministic and fixed-LLM results while being
simpler, faster in deterministic preparation, and slightly smaller in prompt tokens. This is a
failure of HNG to satisfy Breakthrough Gate 6 on the current workload.

## Prior public losses remain

- BM25 remains better for query-specific QMSum retrieval in the inherited public experiment.
- Ordinary structured dictionary and matched dense heads reproduce the inherited synthetic
  perspective result.
- FAISS remains preferable to custom HNG ANN infrastructure at matched retrieval quality.

These losses motivate composition with strong retrieval and simple policy stores rather than
claims of universal HNG dominance.

## GitHub publication blocked

The Yoder23 account and remote were rejected by the user as belonging to Tao Yu and removed.
GitHub CLI is logged out and no origin exists. Local version history is preserved, but this
milestone cannot be pushed until the user authenticates the correct account.
