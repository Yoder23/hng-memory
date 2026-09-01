# HNG component ablation matrix

This study applies one-at-a-time counterfactual record or query-plan transformations to the same
250 frozen synthetic governance scenarios. It measures deterministic downstream decisions, not
public-task or real-assistant behavior. The transformations are not internal production feature
flags, and interactions are not identified.

| Configuration | Accuracy | Delta from full | Decisions changed |
|---|---:|---:|---:|
| Full HNG | 90% | — | — |
| Minus outcome memory | 10% | -80 pp | 225 |
| Minus perspective | 60% | -30 pp | 75 |
| Minus provenance and trust | 70% | -20 pp | 50 |
| Minus exact semantic floors | 80% | -10 pp | 25 |
| Minus required-state contracts | 80% | -10 pp | 25 |
| Minus temporal validity | 80% | -10 pp | 25 |
| Minus supersession | 80% | -10 pp | 25 |
| Minus evidence independence | 90% | 0 pp | 25 |

Outcome polarity, perspective policy, and provenance/trust have the largest measured value in this
suite. Exact floors/contracts, temporal validity, and supersession each protect exactly their
targeted 25-case family. Evidence independence changes every duplicate-attack decision but has zero
accuracy effect because full HNG returns `conflicted` and the ablation returns `support`; both miss
the frozen expected `challenge`. Zero accuracy delta therefore does not mean zero behavior.

Deterministic state carry and profile uncertainty are not isolated because this suite has neither a
multi-turn state-carry intervention nor varied profile uncertainty. Consolidation is measured in
`consolidation/RESULTS.json` and produces no action-quality change. Belief revision is measured in
`belief_revision/RESULTS.json`; HNG preserves the full revision history but ties the strong
structured authority policy. These unisolated or tied components are not credited as wins.

Protocol revision 1 is preserved in the raw log but excluded: its supposed trusted-source
counterfactual accidentally used an unrecognized source type and converted all evidence to
low-trust. Revision 2 uses the production `system_telemetry` type and is the reported result.
Machine evidence is in `ablation_matrix/RESULTS.json` and append-only raw decisions are in
`ablation_matrix/raw/events.jsonl`.
