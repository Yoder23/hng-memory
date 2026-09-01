# Belief revision

`scripts/belief_revision_probe.py` executes 100 deterministic five-event timelines against the
shipped `BeliefStore`. Each timeline contains an initial authoritative fact, corroboration, an
unverified contradiction, an authoritative environment change, and a later authoritative
superseding state.

The study compares naive first-fact memory, append-only latest-event selection, temporal latest
selection, a strong structured authority policy, and that same explicit authority policy backed by
HNG's durable revision store. It measures current-state accuracy, contradiction recognition,
revision latency in event steps, incorrect persistence, historical reconstruction, and evidence-ID
preservation.

This is a controlled synthetic component probe. The harness supplies the authority decision; the
HNG component supplies revision durability and audit history. It is not a public benchmark and it
does not demonstrate an end-to-end assistant choosing when to revise.

The machine result is `belief_revision/RESULTS.json`. The decisive comparison is intentionally
adversarial: HNG must be compared with the strongest simple structured policy. A tie is preserved
as a tie and cannot satisfy the breakthrough strong-baseline gate.
