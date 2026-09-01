# Provenance ablation

The frozen `untrusted_poison` family supplies 25 candidate-identical synthetic scenarios. The
ablation compares four decision paths: provenance removed from the decision, provenance present in
the rendered record but ignored, provenance used by the independent StrongStructuredBaseline, and
provenance used by HNG governance.

The displayed-only arm deliberately makes the same decisions as the no-provenance arm. This tests
whether provenance changes downstream decisions rather than whether a system can print source
metadata. Candidate IDs, order, and pool hashes remain fixed across all arms.

Machine evidence is `provenance_ablation/RESULTS.json`. This is a deterministic synthetic decision
study on one corruption family. It does not establish downstream public-benchmark improvement, and
an HNG tie with the strong structured policy remains a loss on architectural complexity.
