# Statistical analysis

## Methods

Paired categorical results use exact McNemar tests, implemented as an exact two-sided binomial
test over discordant pairs. Accuracy deltas use 10,000 paired bootstrap resamples with fixed seed
20260831 and percentile 95% intervals. Latency is reported descriptively at p50, p95 and p99;
this phase does not claim latency confidence intervals because calls were serialized once on one
machine and order effects remain possible.

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

## Multiplicity and claims

No family-level significance tests are used; the ten family breakdowns are diagnostic. This avoids
presenting uncorrected multiple comparisons as discoveries. No literature score is included in a
local statistical comparison.

## Remaining statistical requirements

- Repeat the LLM holdout with at least one genuinely different model family.
- Add order randomization or counterbalancing and multiple inference seeds where stochasticity is
  enabled.
- Use public benchmark bootstrap units defined by official examples/users, not generated variants.
- Add confidence intervals for component and end-to-end latency from repeated independent runs.
- Pre-register any aggregation-threshold fix against a varied development set before holdout.
