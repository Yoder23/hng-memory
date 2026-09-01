# Statistical analysis

## Methods

Paired categorical results use exact McNemar tests, implemented as an exact two-sided binomial
test over discordant pairs. Accuracy deltas use 10,000 paired bootstrap resamples with fixed seed
20260831 and percentile 95% intervals. Latency is reported descriptively at p50, p95 and p99;
this phase does not claim latency confidence intervals because calls were serialized once on one
machine and order effects remain possible.

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
