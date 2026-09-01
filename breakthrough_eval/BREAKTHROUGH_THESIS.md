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

A second preregistered follow-up uses a third disjoint 30-sample window and genuine Qwen3 dense
embeddings. Dense retrieval scores 71.7%, hybrid BM25/dense reciprocal-rank fusion 61.7%, BM25
51.7%, and full context 63.3%. Hybrid's preregistered +10-point gain over BM25 is inconclusive
(95% CI [-10, +30]); dense's exploratory +20-point gain is also not statistically established
(CI [0, +40]). Dense and hybrid use roughly one-sixth of full-context prompt tokens. HNG, Strong,
and plain hybrid remain exact ties, so better retrieval is the surviving direction while the
HNG-specific claim remains unsupported.

A fourth disjoint preregistered window closes the missing genuine-reranker control. A pinned Qwen3
cross-encoder reranks the BM25-top-128/dense-top-128 union, but scores 48.3% versus RRF hybrid at
50.0%; the primary delta is -1.7 points with 95% CI [-13.3, +8.3]. Full context scores 58.3%.
HNG, Strong, and plain reranked contexts are exact ties at 48.3%. Thus neither neural reranking nor
governance supplies a demonstrated gain on this slice; prompt-efficient retrieval remains useful,
but its best recipe varies across disjoint windows.

A separately pushed preregistration repeats the exact 30 synthetic fixed-candidate cases with a
pinned 24B Mistral-family reader. HNG and Strong each score 27/30 (90.0%) while ordinary context
scores 8/30 (26.7%). The primary HNG-minus-ordinary delta is +63.3 points with 95% CI
[+46.7, +80.0] and exact McNemar p=3.81e-6, so the governed/structured-context effect survives a
genuinely different reader family. HNG versus Strong is again an exact tie (CI [0, 0], p=1), and
both fail every duplicate-attack case. This strengthens reader-family robustness while reinforcing
the simpler-baseline attribution failure; it is fixed-case synthetic replication, not independent
public or real evidence.

The next pushed preregistration removes that case-reuse weakness. On 30 untouched variants with
all six arm orders exactly balanced, Qwen again gives HNG/Strong 27/30 versus ordinary at 17/30
(+33.3 points, CI [+16.7, +50.0], p=0.001953), while Mistral gives HNG/Strong 27/30 versus
ordinary at 9/30 (+60.0 points, CI [+43.3, +76.7], p=7.63e-6). The Bonferroni-adjusted joint
two-reader rule passes with 180/180 events and zero failures. Both HNG/Strong controls remain exact
ties and both systems again fail every duplicate-attack case. Thus structured/governed context now
replicates across both reader families and an independent generated-case window, but HNG-specific,
public, and real-assistant claims remain unsupported.

A cross-study identifiability audit sharpens that limitation. Across all seven public-data studies,
every Strong/HNG pair has the same selected candidates and exact reader prompt (154/154 pairs);
several later studies explicitly reuse the model output. Those ties are policy no-op checks and
cannot identify an HNG-specific reader effect. The four synthetic Qwen/Mistral studies do render
distinct Strong/HNG inputs on 24/30 units each, yet the reader outputs remain equal on all 120
pairs. Public retrieval-arm comparisons remain valid, but public Strong/HNG replication was weaker
than the score tables alone suggested. At the policy level, HNG and the independent Strong baseline
also emit identical decisions and support/challenge scores on all 250 deterministic scenarios. A
further reader run over the same regime would repeat a treatment with no policy-level contrast.

The stronger breakthrough claim remains unproven because:

- no real HDC assistant is available for HNG-off/on testing;
- no qualifying canonical public result is complete;
- HNG does not beat or extend the strong simple baseline in the isolated governance study;
- matched HDC-versus-dense and real-assistant evidence remain absent; public personalization, belief
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
