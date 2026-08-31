# Native HDC assistant ablation

The executed A/B holds the HDC dimensions, semantic families, noise, action library, and decision task constant; only memory use changes. Machine output: `closure_eval/raw/REAL_HDC_ASSISTANT_ABLATION.json`.

| Metric | HNG disabled/raw | HNG enabled |
|---|---:|---:|
| Ambiguous-turn continuity | 0.78125% | 100% |
| Action exact top-1 | 7.8125% | 100% |
| Cross-chat evidence | n/a | 100% |
| Action-routing median | 1.991 ms full raw scan | 2.197 ms memory recommendation |

The complementary identical-state governance A/B (`BEHAVIORAL_GOVERNANCE.json`) gives raw majority 0% task success and 100% stale advice versus governed 100% success, 0% unsupported recommendations, and 100% provenance completeness across 32 poison/failure cases. The inherited action gate gives 100% known-good support, known-bad challenge, and unseen-action abstention; the perspective gauntlet gives 0% HNG perspective violations versus 75% semantic-only.

Mapped requested metrics: action regret and repeated-failure proxy equal the wrong-action rate (92.19% raw, 0% HNG) in the routing task; stale-action rate is 100% raw versus 0% HNG in the governance task; perspective violations are 75% versus 0%; unsupported recommendations are 100% versus 0%; unnecessary abstention is 0% on the known-good action gate; contradiction detection is 100%; provenance completeness is 100%. Constraint persistence/restart is tested, but a real external tool environment was not available, so no empirical production constraint-violation rate is claimed. Context cost is structured evidence count rather than language tokens for this native HDC run.

These are real executable HDC control loops over synthetic task geometry. They are not a public natural-language assistant benchmark, and no LLM was involved.

