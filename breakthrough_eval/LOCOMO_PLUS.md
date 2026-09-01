# LoCoMo-Plus

## Installed public resource

The official LoCoMo-Plus repository is pinned at
`059f4e3d38f7f1f96765e8e2cb7de3097551bffb`. Dataset and generated-input hashes are recorded in
`PUBLIC_RESOURCES.json`; the external checkout and 223 MB generated file are intentionally ignored
by Git.

The unmodified upstream `data/unified_input.py` completed successfully and produced 2,387 inputs:

| Category | Samples |
|---|---:|
| Cognitive | 401 |
| adversarial | 446 |
| common-sense | 96 |
| multi-hop | 282 |
| single-hop | 841 |
| temporal | 321 |

Input prompts range from 48,768 to 109,950 characters (median 95,427); none is empty.

## Integrity boundary

LoCoMo-Plus answers and judge evidence may be used only after generation for scoring. The cognitive
trigger turn must not be ingested into a memory built from the preceding conversation, and the
upstream evidence annotation must never be used as retrieval input. Doing either would leak the
target into the memory system.

## Prepared local pilot

A deterministic SHA-selected slice contains one sample from each of the six categories. The full
context arm uses the official model-input construction. BM25, StrongStructuredBaseline, and HNG
receive the same 16 selected dialogue turns under an 18,000-character budget. The Cognitive final
trigger utterance and ordinary `Question:` suffix are removed before retrieval, then supplied only
as the current query. Tests verify that changing answers or oracle judge evidence cannot change
sample selection.

Reader/judge execution is not yet complete. A full 2,387-sample run would require both a reader and
judge call per arm and is not feasible on the single local 27B runtime within the current experiment
window. The six-sample pilot is explicitly noncanonical because it uses the same local model as
reader and judge and BM25 turn retrieval is not an official baseline. No LoCoMo-Plus score is
claimed yet, and all published systems remain undefeated locally.
