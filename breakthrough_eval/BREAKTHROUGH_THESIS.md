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
fewer LLM prompt tokens. In the expanded 30-sample LoCoMo-Plus slice, HNG, Strong, and BM25 tie at
30.0% and all lose to full context at 61.7%; the HNG/full-context gap is statistically supported in
this noncanonical local protocol. The result points to retrieval truncation rather than governance.

A preregistered disjoint 30-sample follow-up supports the retrieval diagnosis only weakly: widening
BM25 from 16 to 64 turns raises the mean judge score from 36.7% to 45.0%, but the paired 95%
interval [-3.3, +21.7] points includes zero. K64 nearly matches full context at 45.0% versus 46.7%
while using about 17% of its prompt tokens. HNG, Strong, and plain BM25 remain exact ties at fixed
k64, so the follow-up improves the retrieval operating point without supplying an HNG-specific win.

The stronger breakthrough claim remains unproven because:

- no real HDC assistant is available for HNG-off/on testing;
- no qualifying canonical public result is complete;
- HNG does not beat or extend the strong simple baseline in the isolated governance study;
- HDC-versus-dense and real-assistant evidence remain absent; public personalization, belief
  revision, cross-session learning, action experience, tool-agent, provenance, and consolidation
  evidence is synthetic or noncanonical and does not reveal an HNG advantage over Strong.

The research direction is therefore falsifiable. If clean public evidence produces no policy
changes, HNG should tie ordinary retrieval. If strong structured filters reproduce every robust
gain, the simpler architecture should be preferred. A paper centered on HNG itself is justified
only if later real/public evidence reveals an advantage the simpler system cannot reproduce.

## Current contribution that survives

The universal harness, candidate/prompt/model invariants, typed evidence schema, append-only logs,
and explicit separation of retrieval from governance form a useful evaluation method. Whether the
production architecture merits adoption remains the empirical question, not an assumption.
