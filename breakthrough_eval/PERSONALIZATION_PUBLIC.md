# Public personalization

The official PersonaMem-v2 repository is pinned at
`dd52429f83ced4394be46c3849186a423942b2a5`; the Hugging Face dataset is pinned at revision
`0622e56d1cc6f1bc990a5100a6ec4022a60e66a6`. The 5,000-row text benchmark and all 1,998 released
32K history files are present. All 200 unique histories referenced by the benchmark resolve, with
zero missing references. Exact hashes and category counts are in `PUBLIC_RESOURCES.json`.

A deterministic noncanonical pilot selects one row from each of the seven preference types without
using correct/incorrect answers, preference/profile text, related snippets, or other oracle text.
The public `pref_type` field is used only to define the seven strata. Answer
options are loaded only after sample selection and retrieval. The seven arms are no memory, short
profile, expanded profile, full history, BM25 history chunks, StrongStructuredBaseline, and HNG.
BM25/Strong/HNG share fixed candidates and prompts. The append-only 49-evaluation local run is in
complete with zero unresolved failures and all seven fixed-candidate invariants passing.

| Arm | Correct | Accuracy | Prompt tokens |
|---|---:|---:|---:|
| No memory | 1/7 | 14.3% | 2,713 |
| Short profile | 2/7 | 28.6% | 2,781 |
| Expanded profile | 3/7 | 42.9% | 9,173 |
| Full history | 4/7 | 57.1% | 222,934 |
| BM25 history chunks | 4/7 | 57.1% | 30,970 |
| StrongStructuredBaseline | 4/7 | 57.1% | 30,970 |
| HNG | 4/7 | 57.1% | 30,970 |

HNG provides no accuracy or token advantage over BM25 or StrongStructuredBaseline on these clean
histories, and it ties the much more expensive full-history arm. Serialized order and runtime cache
effects prevent a latency-superiority claim. Eleven superseded or invalid historical attempts remain
in the raw log but are excluded: three capped first-pass outputs, one mislabeled HNG provenance
trace, and seven revision-1 full-history prompts. Prompt protocol revision 2 moves the MCQ task into
the final user turn for local Ollama compatibility and reruns all seven full-history cases.

The frozen perspective gauntlet passes its synthetic role/authority cases, and the 250-scenario
suite correctly filters wrong-role, wrong-tenant, and authority-mismatch evidence. These are policy
unit/integration probes, not evidence of evolving realistic preference modeling.

The pilot does not install the official dense RAG, summary-profile, structured-dictionary, or
agentic-profile systems and therefore cannot establish contemporary competitiveness. At n=7, the
pilot also cannot support a significance claim. Structured
exact profile state must remain separate from semantic fuzzy perspective. Until a full official
evaluation with those strong baselines and multiple reader families is run, dynamic personalization
remains `PARTIAL` and no HNG advantage is claimed.
