# Track B: perspective and personalization

## Verdict

The security layering is sound; the claimed HNG-specific personalization advantage is falsified by equal-information baselines. Explicit profile fields define the synthetic answer, and ordinary structured lookup or dense multi-head matching reaches the same 100% accuracy.

## Executed shipped workload (Tier A)

The fresh gauntlet used 64 semantic situations, eight personas, 1,536 experiences, 8,192 actions, 16 close action variants, and 512 queries.

| Method | Exact action top-1 | Median latency | Notes |
|---|---:|---:|---|
| Raw action HDC router | 7.2266% | not isolated | Close variants are intentionally ambiguous. |
| Semantic HNG, no perspective | 12.5% | 4.005 ms | Role-violation rate 75%. |
| Hard metadata only | 50% | 5.680 ms | Role/authority is necessary but not sufficient for the generated variant label. |
| Full HNG perspective | 100% | 6.009 ms | Role-violation rate 0%. |
| Exact structured multi-head baseline | 100% | 10.003 ms | Same metadata, exhaustive Hamming floors. |
| Ordinary dictionary | 100% | 0.0026 ms | Keyed by the explicit context/profile fields that generate ground truth. |
| Dense float multi-head | 100% on 128 queries | 7.183 ms | Exact cosine over float32 +/-1 copies of the same seven heads. |

The fresh raw-router result differs from the shipped 6.25% artifact. The important comparison is unchanged: full perspective is perfect, but so are non-HNG systems with the same information.

Additional shipped checks passed:

- acting-role switch accuracy: 100% across 64 queries;
- one profile-update before/after scenario: passed;
- private and tenant leakage: 0 across two checks.

The leakage test count is too small for a production security claim. Exact access isolation is still the correct design because eligibility is applied before semantic scoring.

## Required adversaries and coverage

| Adversary | Status | Result / gap |
|---|---|---|
| Identical situation, different role | Executed | Full HNG 100%; semantic-only creates violations. |
| Same role, different expertise | Executed in generated persona combinations | Correct, but fields directly determine answer. |
| Same role/expertise, different priority | Executed in generated combinations | Correct, same caveat. |
| Temporary acting role | Executed | 100%. |
| Profile changes | One executed case | Passed; not a distribution-level estimate. |
| Old memories under old profile revision | Partially represented | No broad migration/supersession benchmark. |
| Cross-user private memory | Two combined isolation checks | No observed leak. |
| Cross-tenant identical memory | Two combined isolation checks | No observed leak. |
| Global memory sharing | Unit/API coverage | No large adversarial evaluation. |
| Executive precedent for IC | Executed | Hard authority filter blocked it. |
| IC detail for executive | Represented by abstraction eligibility | No separately reported population metric. |
| Incorrect authoritative profile | Executed adversarially | HNG returned support; cannot detect wrong external truth. |

Any future leakage is an automatic failure. This evaluation observed none but does not claim a statistically meaningful upper bound from two trials.

## Public benchmark status

PersonaMem, PersonaMem-v2, LaMP, and PersonaAgent were researched but not run. The repository lacks a shared LLM personalization pipeline and natural-language-to-head encoder. Supplying dataset preference labels as `perspective`, `expertise`, or `priority` would give HNG oracle information. No public personalization win is claimed.

## What actually causes the gain

The gain decomposes cleanly:

1. exact access scope prevents private/tenant leakage;
2. hard role/authority/abstraction filters remove ineligible actions;
3. expertise and priority fields select among remaining variants;
4. the HDC representation is interchangeable with dense vectors or ordinary keys on this workload.

This supports the schema and policy separation, not a unique associative-memory result.

## Recommendation

Keep access and authority checks in SQLite or another transactional policy store. Treat profile revision, acting role, expiry, and provenance as typed fields. Use HDC perspective heads only when the upstream HDC interpreter already produces them; otherwise ordinary structured filters plus a standard vector index are simpler. Do not put authorization in a similarity threshold.
