# Statistical analysis

## Methods

Paired categorical results use exact McNemar tests, implemented as an exact two-sided binomial
test over discordant pairs. Accuracy deltas use 10,000 paired bootstrap resamples with fixed seed
20260831 and percentile 95% intervals. Single model runs report latency descriptively. A dedicated
tool-agent probe reports bootstrap intervals for the mean of per-run p50, p95, and p99 across 20
independent fresh-store repeats on one host; these intervals do not estimate cross-host or
production-load variation.

## Provenance ablation

On the 25 frozen `untrusted_poison` cases, HNG provenance governance is correct on all 25 while
no-provenance and display-only policies are correct on 0. The paired exact McNemar p-value is below
`1e-7`. HNG and StrongStructuredBaseline are identical on all 25, giving exact McNemar p=1.0 and a
zero effect. The study is synthetic and family-specific.

## Deterministic component ablations

Across all 250 frozen scenarios, full HNG scores 90%. One-at-a-time counterfactual removals change
accuracy by -80 points for outcome memory, -30 for perspective, -20 for provenance/trust, and -10
each for exact floors, required-state contracts, temporal validity, and supersession. Removing
evidence independence changes 25 decisions but has zero accuracy effect because both the full and
ablated decisions miss the duplicate-family expected label. These are deterministic full-suite
descriptives, so confidence intervals or p-values would not add sampling information. The 25
variants per family share templates; the deltas do not estimate natural-task prevalence.

## LongMemEval-V2 public-data pilot

HNG, StrongStructuredBaseline, and BM25 each score 4/21 on the noncanonical text pilot, with the
same per-ability counts and identical fixed prompts. The observed effect is 0 percentage points.
No significance or competitiveness claim is made at n=21, and no leaderboard comparison is valid
because the reader, retriever, judge, and subset differ from the official stack.

## LoCoMo-Plus public-data pilot

HNG, StrongStructuredBaseline, and BM25 each score 2/6 (33.3%) on the six-category noncanonical
pilot; full context scores 3/6 (50.0%). The fixed retrieval arms have identical candidate sets and
prompts. At one example per category, the 16.7-point observed full-context advantage is descriptive
only: no significance test or competitiveness claim is justified. The same local model served as
reader and judge, and the subset/retriever differ from official evaluation.

## PersonaMem-v2 public-data pilot

HNG, StrongStructuredBaseline, BM25, and full history each score 4/7 (57.1%) on the noncanonical
seven-stratum MCQ pilot. Expanded profile scores 3/7, short profile 2/7, and no memory 1/7. The
fixed retrieval arms have identical candidates, prompts, and reader digest. At one example per
preference type, no inferential or competitiveness claim is justified; official dense/agentic
baselines and multiple reader families are absent. Runtime order/cache effects also preclude a
latency comparison.

## Deterministic Adversarial-250

| Comparison | Delta | Bootstrap 95% CI | Discordant HNG-only / other-only | Exact p |
|---|---:|---:|---:|---:|
| HNG vs raw majority | +80.0 pp | [+74.8, +84.8] pp | 200 / 0 | 1.2446e-60 |
| HNG vs StrongStructuredBaseline | 0.0 pp | [0.0, 0.0] pp | 0 / 0 | 1.0 |

The first comparison is statistically clear but scientifically weak as a superiority claim
because raw majority is not a strong baseline. The second comparison is the decisive complexity
control and is an exact tie.

## Fixed-LLM 30-case holdout

| Comparison | Delta | Bootstrap 95% CI | Discordant HNG-only / other-only | Exact p |
|---|---:|---:|---:|---:|
| HNG vs ordinary candidate context | +33.3 pp | [+16.7, +50.0] pp | 10 / 0 | 0.001953125 |
| HNG vs StrongStructuredBaseline | 0.0 pp | [0.0, 0.0] pp | 0 / 0 | 1.0 |

The experimental unit is the scenario. The 30 cases are balanced as three variants per family,
which limits ecological prevalence claims. The exact same generator template across variants also
means the interval reflects template variation, not a broad natural-task distribution.

## Executing synthetic tool-agent study

The untouched adapter's HNG arm scores 32/108 (29.6%), versus 36/108 for agent alone, 50/108 for
ordinary recent memory, and 69/108 for StrongStructuredBaseline. After temporal/access/perspective
outcome context is forwarded, the identical HNG stream scores 69/108 (63.9%), with irreversible
mistakes falling from 18 to zero and repeated failures from 38 to 2.

| Post-change comparison | Delta | Paired bootstrap 95% CI | Discordant HNG-only / other-only | Exact p |
|---|---:|---:|---:|---:|
| HNG vs ordinary recent memory | +17.6 pp | [+5.6, +29.6] pp | 33 / 14 | 0.007943 |
| HNG vs StrongStructuredBaseline | 0.0 pp | [0.0, 0.0] pp | 0 / 0 | 1.0 |

The experimental unit is a deterministic synthetic episode. The significant ordinary-memory
comparison does not establish public or real-agent generality. The exact Strong tie is the
complexity control and prevents an HNG-specific superiority claim.

## Expanded LoCoMo-Plus holdout

The expanded fixed holdout contains 30 samples, five per category. HNG,
StrongStructuredBaseline, and BM25 each score 9/30 (30.0%); full context scores 18.5/30 (61.7%).
HNG versus full context is -31.7 percentage points with paired bootstrap 95% CI [-53.3, -8.3]
and exact McNemar p=0.0352 (3 HNG-only positives, 12 full-context-only positives). HNG versus BM25
and Strong is an exact tie: delta 0, CI [0, 0], McNemar p=1. The expanded result remains
noncanonical and does not establish an official benchmark rank.

## Repeated tool-agent latency

Twenty fresh-store repeats preserve identical behavior across 8,640 raw events. Mean per-run p95
decision latency is 1.976 ms for HNG (bootstrap 95% CI [1.936, 2.016]) and 0.0164 ms for
StrongStructuredBaseline (CI [0.0154, 0.0175]). Mean per-run p99 is 2.292 ms for HNG (CI [2.196,
2.390]) and 0.0323 ms for Strong (CI [0.0264, 0.0391]). HNG is roughly 121 times slower at p95,
although both are negligible beside local 27B inference. These are synthetic single-host latency
intervals, not deployment SLO evidence.

## Preregistered disjoint LoCoMo-Plus dense/hybrid holdout

The third disjoint 30-sample window excludes all 60 prior LoCoMo-Plus development and
retrieval-budget samples. At k64, BM25 scores 15.5/30 (51.7%), Qwen3 dense retrieval scores
21.5/30 (71.7%), reciprocal-rank fusion scores 18.5/30 (61.7%), and full context scores 19/30
(63.3%). The preregistered primary hybrid-versus-BM25 delta is +10.0 percentage points, with
paired bootstrap 95% CI [-10.0, +30.0] and exact McNemar p=0.5488. The interval includes zero,
so the primary improvement is not established. Dense versus BM25 is +20.0 points with CI
[0.0, +40.0] and p=0.2266; dense versus hybrid is +10.0 points with CI [-5.0, +25.0] and
p=0.6875. These exploratory comparisons likewise do not establish superiority at n=30.

Dense uses 106,672 prompt tokens and hybrid 112,665, versus 643,575 for full context. Every
BM25/dense and BM25/hybrid ordered candidate list differs, so this is genuine retrieval variation
rather than renamed lexical output. HNG hybrid, Strong hybrid, and plain hybrid are exact
fixed-candidate ties: 18.5/30, delta 0, CI [0, 0], p=1. The protocol remains noncanonical.

## Preregistered disjoint LoCoMo-Plus neural-reranker holdout

The fourth disjoint 30-sample window excludes the exact 90 indices in the three prior windows. A
pinned Qwen3 cross-encoder reranks the union of BM25-top-128 and dense-top-128 to 64 turns. BM25
scores 12/30 (40.0%), dense 13.5/30 (45.0%), RRF hybrid 15/30 (50.0%), reranked 14.5/30
(48.3%), and full context 17.5/30 (58.3%). The preregistered primary reranked-versus-hybrid delta
is -1.7 percentage points with paired bootstrap 95% CI [-13.3, +8.3] and exact McNemar p=1.0.
The cross-encoder therefore does not improve this holdout.

Reranked versus BM25 is +8.3 points (CI [-6.7, +25.0], p=1); versus dense is +3.3 points (CI
[-11.7, +18.3], p=1); and versus full context is -10.0 points (CI [-23.3, +3.3], p=0.21875).
All intervals include zero. Reranked uses 104,965 prompt tokens versus 658,631 for full context.
HNG reranked, Strong reranked, and plain reranked are exact fixed-candidate ties: 14.5/30, delta
0, CI [0, 0], p=1. The result is noncanonical and preserves a preregistered retrieval loss.

## Preregistered disjoint LoCoMo-Plus retrieval-budget holdout

The 30-sample holdout uses zero source-index overlap with the observed top-16 development slice.
BM25 k16 scores 11/30 (36.7%), k32 scores 12/30 (40.0%), and k64 scores 13.5/30 (45.0%);
full context scores 14/30 (46.7%). The primary k64-versus-k16 delta is +8.3 percentage points,
with paired bootstrap 95% CI [-3.3, +21.7] and exact McNemar p=0.375 (4 k64-only versus 1
k16-only positive). The interval includes zero, so wider lexical retrieval is promising but not a
statistically established improvement on this holdout. K64 uses 116,800 prompt tokens versus
680,824 for full context and trails it by 1.7 points (CI [-20.0, +16.7], p=1). HNG, Strong, and
plain BM25 are exact fixed-candidate k64 ties: 13.5/30, delta 0, CI [0, 0], p=1.

## Preregistered fixed-candidate cross-family reader replication

The exact 30 synthetic holdout cases, ordered candidate pools, system-specific memory contexts,
outer prompt hash, and scoring rule from the Qwen study were reused with pinned Mistral Small 3.1
24B digest `b9aaf0c2586a8ed8105feab808c0f034bd4d346203822f048e2366165a13f4ea`.
All 90 events completed with zero failures under the single pushed preregistration commit.

HNG and Strong each score 27/30 (90.0%); ordinary RAG scores 8/30 (26.7%). The preregistered
primary HNG-minus-ordinary delta is +63.3 percentage points with paired-bootstrap 95% CI
[+46.7, +80.0]. All 19 discordant pairs favor HNG, giving exact two-sided McNemar
p=0.0000038147. The reader-family-independent governed/structured-context rule therefore passes.

The preregistered complexity control is an exact HNG/Strong tie: delta 0, CI [0, 0], zero
discordant pairs, p=1. Both systems miss all three duplicate-attack cases. Accordingly, this run
does not attribute the gain specifically to HNG. It reuses previously evaluated synthetic cases,
so it is a model-family replication rather than an independent confirmatory sample.

## Preregistered disjoint cross-reader holdout

The next 30 untouched generated holdout cases (variants 08-10 in each of ten families) have zero
overlap with the prior reader-family window. Within each pinned reader, all six system execution
orders occur exactly five times. The single pushed preregistration applies per-reader alpha 0.025
and requires both reader-specific HNG-versus-ordinary tests to have positive deltas, bootstrap 95%
lower bounds above zero, and exact two-sided McNemar p below 0.025.

Qwen HNG and Strong each score 27/30 (90.0%) versus ordinary at 17/30 (56.7%). HNG-minus-ordinary
is +33.3 points, CI [+16.7, +50.0], with all ten discordant pairs favoring HNG and p=0.001953.
Mistral HNG and Strong each score 27/30 versus ordinary at 9/30 (30.0%). Its delta is +60.0
points, CI [+43.3, +76.7], with all 18 discordant pairs favoring HNG and p=0.0000076294. The joint
structured-context rule passes.

For both readers, HNG versus Strong is an exact tie: delta 0, CI [0,0], zero discordant pairs,
p=1. The HNG-specific joint control therefore fails. Both systems miss all three duplicate-attack
cases in both readers. All 180 events complete with zero failures, one preregistration commit,
exact model digests, exact prepared inputs/orders, and the frozen prompt-template hash. The unit is
still a generated synthetic case, not a public or real-assistant task.

## Multiplicity and claims

No family-level significance tests are used; the ten family breakdowns are diagnostic. This avoids
presenting uncorrected multiple comparisons as discoveries. No literature score is included in a
local statistical comparison.

## Remaining statistical requirements

- Add multiple inference seeds where stochasticity is enabled; the disjoint cross-reader window
  now supplies independent generated cases and exact order counterbalancing.
- Use public benchmark bootstrap units defined by official examples/users, not generated variants.
- Extend repeated-run confidence intervals beyond the synthetic tool-agent decision path to every
  component and end-to-end deployment path.
- Pre-register any aggregation-threshold fix against a varied development set before holdout.
