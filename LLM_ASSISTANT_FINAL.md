# LLM assistant integration

`LLMAssistantAdapter` renders a bounded `GovernedMemoryFrame`. Sections are deterministically ordered by safety relevance: decision and uncertainty, current state, goal/facts/perspective, open loops/commitments/constraints, supporting and contradicting evidence, excluded or superseded evidence, then provenance.

`max_context_chars` and `max_context_tokens` impose deterministic limits; the adapter does not dump arbitrary history. Evidence items retain IDs, source identity, verification state, trust factors, exact scores, and exclusion reasons in the machine-readable frame.

The adapter and truncation are tested, but no common-model same-prompt LLM A/B was executed in this environment. Use it in shadow or context-augmentation mode until a deployment-specific model/task evaluation demonstrates benefit.

