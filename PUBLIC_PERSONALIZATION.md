# Public personalization validation plan

HNG 0.5's synthetic perspective gauntlet is an architectural proof, not a real-user benchmark. The public personalization track should use the production HDC interpreter and identical upstream profile extraction across baselines.

## Baselines

1. no personalization / semantic query only;
2. durable profile injected as prompt/context text;
3. retrieval-augmented user history (LaMP-style);
4. agentic/profile memory baseline where reproducible;
5. HNG soft perspective HDC heads only;
6. HNG full access + role/authority eligibility + perspective/expertise/priority HDC heads.

## Public datasets

- PersonaMem: dynamic user profiling over multi-session histories;
- PersonaMem-v2: implicit, evolving user preferences and agentic memory;
- LaMP / LaMP-QA: personalized classification/generation and retrieval-augmented profiles.

For implicit-persona datasets, HNG must not receive privileged gold persona labels. Use the same extractor/interpreter inputs available to the competing system, then test whether HNG's persistent perspective representation and evidence routing improve downstream decisions.

## Metrics beyond task accuracy

- perspective violation rate;
- role/authority-inappropriate action rate;
- cross-user / cross-tenant leakage;
- adaptation after a profile change;
- active-role override accuracy;
- stale-profile contradiction handling;
- evidence provenance;
- input-token/context cost;
- p50/p95/p99 memory latency;
- action regret / historically failed action reuse where the task supports it.

## Falsification

If a profile-in-prompt or ordinary retrieval baseline matches HNG at lower complexity, perspective-conditioned HNG has not earned its architecture. If HNG materially improves current-profile alignment, actor-appropriate action selection, and leakage/violation rates across real histories while keeping provenance explicit, the perspective layer becomes a strong contribution to the broader HNG memory thesis.
