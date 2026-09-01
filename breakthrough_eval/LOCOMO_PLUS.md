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

## Completed local pilot

A deterministic SHA-selected slice contains one sample from each of the six categories. The full
context arm uses the official model-input construction. BM25, StrongStructuredBaseline, and HNG
receive the same 16 selected dialogue turns under an 18,000-character budget. The Cognitive final
trigger utterance and ordinary `Question:` suffix are removed before retrieval, then supplied only
as the current query. Tests verify that changing answers or oracle judge evidence cannot change
sample selection.

All 24 arm evaluations completed without runtime failures. All six fixed-candidate invariants pass:
BM25, StrongStructuredBaseline, and HNG used identical candidate pools, selected candidate IDs,
prompts, and frozen model digest for each sample.

| Arm | Judge score | Average | Prompt tokens |
|---|---:|---:|---:|
| Full context | 3/6 | 50.0% | 149,139 |
| BM25 | 2/6 | 33.3% | 5,920 |
| StrongStructuredBaseline | 2/6 | 33.3% | 5,920 |
| HNG | 2/6 | 33.3% | 5,920 |

HNG produces no gain over either retrieval control and trails full context by 16.7 percentage
points. The six-sample result is explicitly noncanonical: it uses the same frozen local 27B model
as reader and judge, BM25 turn retrieval is not an official baseline, and the subset is far too
small for a competitiveness or significance claim. A full 2,387-sample reader-plus-judge run remains
outside the current single-machine inference budget. Raw evidence is append-only in
`public/locomo_plus/raw/events.jsonl`; compiled evidence is in `public/locomo_plus/RESULTS.json`.
Six original HNG events with a mislabeled shared-adapter source identity are preserved but excluded;
their corrected selective reruns reproduce the same scores and prompts with zero unresolved failures.

## Expanded preregistered holdout

A second preserved evaluation increases the deterministic selection to five samples per category:
30 samples and 120 arm events. Selection, model, top-k, context budget, reader prompt, judge prompt,
and answer/evidence leakage controls are unchanged. The original six-sample evidence remains intact.
All 30 fixed-candidate invariants pass and no evaluation event failed.

| Arm | Judge score | Average | Prompt tokens |
|---|---:|---:|---:|
| Full context | 18.5/30 | 61.7% | 686,221 |
| BM25 | 9/30 | 30.0% | 31,511 |
| StrongStructuredBaseline | 9/30 | 30.0% | 31,511 |
| HNG | 9/30 | 30.0% | 31,511 |

HNG again ties BM25 and StrongStructuredBaseline exactly. Against full context, HNG loses by 31.7
percentage points: paired bootstrap 95% CI [-53.3, -8.3] points; exact McNemar p=0.0352 using an
official-judge score above 0.5 as positive. This is a meaningful local loss, not an official
leaderboard result. It indicates that turn-level top-16 truncation discards useful clean dialogue
on this slice; governance has no applicable metadata distinction with which to recover it.

The run contains 70 actual deterministic model/judge evaluations and 50 exact-input reuses. Reuse
occurs only within the same sample when prompt SHA-256, model digest, reader options, prediction,
and judge input are identical. This prevents repeated-call nondeterminism from being mislabeled as
a memory effect. Raw evidence is in `public/locomo_plus_n30/raw/events.jsonl`; the preparation and
result are `public/locomo_plus_n30/PREPARED.json` and `public/locomo_plus_n30/RESULTS.json`.

## Expanded preregistered holdout

A second preserved evaluation increases the deterministic selection to five samples per category:
30 samples and 120 arm events. Selection, model, top-k, context budget, reader prompt, judge prompt,
and answer/evidence leakage controls are unchanged. The original six-sample evidence remains intact.
All 30 fixed-candidate invariants pass and no evaluation event failed.

| Arm | Judge score | Average | Prompt tokens |
|---|---:|---:|---:|
| Full context | 18.5/30 | 61.7% | 686,221 |
| BM25 | 9/30 | 30.0% | 31,511 |
| StrongStructuredBaseline | 9/30 | 30.0% | 31,511 |
| HNG | 9/30 | 30.0% | 31,511 |

HNG again ties BM25 and StrongStructuredBaseline exactly. Against full context, HNG loses by 31.7
percentage points: paired bootstrap 95% CI [-53.3, -8.3] points; exact McNemar p=0.0352 using an
official-judge score above 0.5 as positive. This is a meaningful local loss, not an official
leaderboard result. It indicates that turn-level top-16 truncation discards useful clean dialogue
on this slice; governance has no applicable metadata distinction with which to recover it.

The run contains 70 actual deterministic model/judge evaluations and 50 exact-input reuses. Reuse
occurs only within the same sample when prompt SHA-256, model digest, reader options, prediction,
and judge input are identical. This prevents repeated-call nondeterminism from being mislabeled as
a memory effect. Raw evidence is in `public/locomo_plus_n30/raw/events.jsonl`; the preparation and
result are `public/locomo_plus_n30/PREPARED.json` and `public/locomo_plus_n30/RESULTS.json`.
