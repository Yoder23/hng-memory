# RAG governance

## Fixed-candidate result

All systems receive the same ordered synthetic candidate records and metadata. On 250 frozen
governance cases:

| System | Decision accuracy |
|---|---:|
| Raw majority over candidates | 10.0% |
| StrongStructuredBaseline | 90.0% |
| Production HNG | 90.0% |

HNG versus raw majority is +80.0 percentage points (paired bootstrap 95% CI +74.8 to +84.8;
McNemar exact p=1.2446e-60). HNG versus StrongStructuredBaseline is an exact tie: zero discordant
cases, p=1.0.

With the same frozen local 27B model on 30 untouched holdout cases:

| Memory rendering | Accuracy | Prompt tokens | p95 latency |
|---|---:|---:|---:|
| Ordinary candidates | 56.7% | 41,046 | 8.825 s |
| StrongStructuredBaseline | 90.0% | 16,215 | 5.674 s |
| HNG | 90.0% | 17,103 | 5.483 s |

HNG versus ordinary candidates is +33.3 points (paired bootstrap 95% CI +16.7 to +50.0;
McNemar exact p=0.001953). HNG versus the strong baseline is again an exact tie. The result proves
the value of **some explicit governance** on this synthetic corruption distribution; it does not
prove an HNG-specific advantage.

## Preserved loss

Both structured systems fail all 25 duplicate-attack cases. They correctly reduce six copied
support rows to one independent source event, but the frozen one-support/two-challenge boundary is
classified conflicted rather than challenge. Expected outcomes were not changed.

## Missing public scope

The study is synthetic and does not satisfy realistic hybrid/dense/reranked RAG validation. A
qualifying public study must inject versioned/stale/conflicting/poisoned documents into a recognized
corpus, hold retrieval candidates fixed, equalize context, and measure answer accuracy, leakage,
poison success, provenance, abstention, and tokens. No such public win is currently claimed.
