# Belief and fact memory

`EvidenceKind` distinguishes observation, fact, claim, hypothesis, belief, model inference, action, outcome, procedure, constraint, preference, profile, document claim, tool result, and system event. Trust weights are configurable by source and evidence kind.

`BeliefStore` persists a belief ID, statement, confidence, source provenance, supporting and contradicting evidence IDs, creation/revision timestamps, revision number, status, supersession, and invalidation. Revisions are append-only and queryable through `history()`.

A `model_inference` provenance source cannot be ingested as authoritative `FACT`; callers must store it as inference, hypothesis, claim, or belief and attach evidence before promotion through application policy. This is a guardrail, not a claim that HNG can determine truth automatically.

