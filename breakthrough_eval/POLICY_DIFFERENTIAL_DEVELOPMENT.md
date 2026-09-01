# HNG versus Strong policy differential search

This development-only search enumerates 960 exact-state cases across all 15 evidence kinds, eight
source types, verified/unverified status, support/challenge stance, and one/two independent groups.
It invokes the production `EvidenceAggregator` and the independent StrongStructuredBaseline on the
same ordered candidates. Cases are deliberately unlabeled and are not a holdout.

## Result

The policies differ on 596/960 decision labels, 520 score pairs, and 204 included sets. Of the
decision differences, 360 are only `insufficient_evidence` versus `untrusted_evidence`; neither
policy authorizes an action. The remaining 236 are action-relevant and all make HNG more
conservative: Strong returns support or challenge while HNG returns insufficient or untrusted.
There are zero cases where HNG is decisive and Strong is not.

The most coherent contrast is a verified external-document claim. One independent claim scores
0.75 in Strong and 0.5625 in HNG because HNG composes source and evidence-kind weights; Strong acts
while HNG requires corroboration. With two independent claims both are decisive. But converting a
document claim into support/challenge requires a synthetic outcome stance and a normative label.
The public-memory records use neutral document claims, so this grid does not license retroactive
public scoring or an LLM holdout.

## Admission decision

No reader holdout is admitted from this development grid. A qualifying experiment needs authentic
provenance, a task with externally defined ground truth for act/abstain behavior, and labels that do
not encode HNG's own trust formula. If such a task becomes available, the preregistration must use
disjoint case construction, retain both one-source and corroborated strata, give Strong identical
metadata and policy budget, and pass the distinct-policy/distinct-prompt preflight before inference.

Machine-readable result: `policy_differential/DEVELOPMENT_RESULTS.json`.
