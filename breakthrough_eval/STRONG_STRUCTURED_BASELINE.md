# StrongStructuredBaseline

## Purpose

This is the simpler-architecture challenge required by the program. It is an independent ordinary
typed-filter implementation, not an HNG ablation. It receives the same candidate records and:

- exact current state, goal, sequence, action and environment;
- tenant, user, role and authority;
- validity, invalidation and supersession fields;
- source type, trust, verification and confidence;
- source-event identity for duplicate grouping;
- explicit action outcome.

Its operations can be implemented as typed rows, WHERE clauses, exact comparisons, GROUP BY
source_event_id, and a small deterministic aggregation function. It uses no HDC, ANN, belief
graph, consolidation, or HNG classes.

## Results so far

StrongStructuredBaseline exactly ties HNG:

- deterministic Adversarial-250: 225/250 for both;
- fixed 27B LLM holdout: 27/30 for both;
- zero paired discordances in both experiments;
- fewer LLM prompt tokens: 16,215 versus HNG's 17,103 across 30 cases;
- deterministic p95 preparation: 0.035 ms versus HNG's 0.179 ms.

These results are a current HNG loss on Gate 6. They show that explicit evidence governance helps
relative to ungoverned candidate context on this synthetic workload, but do not show that HNG's
additional architecture is necessary.

## Fairness

The baseline receives no oracle labels and no metadata withheld from HNG. Conversely, HNG receives
no semantic vectors unavailable to the baseline: all exact semantic values in this benchmark are
typed structured fields. The comparison therefore tests governance structure, not HDC.

## Next falsification

HNG can recover a differentiated result only on tasks where its additional mechanisms improve
behavior or a Pareto frontier: native HDC state, fuzzy multi-head applicability, corruption
robustness, richer provenance, consolidation, belief revision, or scale. If a matched structured
store continues to tie, the simpler architecture should be preferred.
