# Breakthrough thesis under test

The original hypothesis is that persistent state and retrieved information are more useful when
governed as applicable historical evidence than when treated as semantically similar context.
Current evidence supports a narrower statement:

> Explicit filtering for actor, authority, time, supersession, trust, independence, and exact
> task state can materially improve a fixed model on corrupted retrieved evidence, without
> changing model weights.

It does **not** yet establish that the HNG implementation is the necessary or best way to obtain
that benefit. On 250 deterministic synthetic cases, both HNG and StrongStructuredBaseline score
90%; on the 30-case frozen local-LLM holdout both score 90%. The simple baseline is faster and uses
fewer LLM prompt tokens. HNG's only losses are the 25 frozen duplicate-boundary cases, and the
simple baseline reproduces them exactly.

The stronger breakthrough claim remains unproven because:

- no real HDC assistant is available for HNG-off/on testing;
- no qualifying canonical public result is complete;
- HNG does not beat or extend the strong simple baseline in the isolated governance study;
- HDC-versus-dense, personalization, belief revision, cross-session learning, action experience,
  tool-agent, provenance, and consolidation studies remain incomplete.

The research direction is therefore falsifiable. If clean public evidence produces no policy
changes, HNG should tie ordinary retrieval. If strong structured filters reproduce every robust
gain, the simpler architecture should be preferred. A paper centered on HNG itself is justified
only if later real/public evidence reveals an advantage the simpler system cannot reproduce.

## Current contribution that survives

The universal harness, candidate/prompt/model invariants, typed evidence schema, append-only logs,
and explicit separation of retrieval from governance form a useful evaluation method. Whether the
production architecture merits adoption remains the empirical question, not an assumption.
