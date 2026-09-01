# Strong/HNG experimental identifiability audit

This audit asks a narrower question than benchmark accuracy: did the StrongStructuredBaseline and
HNG arms actually give the reader different inputs, so a downstream score difference was possible?
It reads preserved JSONL only and compares paired candidate, selection, context, and prompt hashes.
It does not rescore answers or create new behavioral evidence.

## Result

All 11 preserved reader studies contain a unique Strong/HNG pair. In all seven public-data studies,
every paired unit has the same selected candidates and the same reader prompt in both arms. That is
154 exact prompt pairs: 21 LongMemEval-V2, 6 and 30 in the two LoCoMo-Plus pilots, 30 each in the
retrieval-budget, hybrid, and reranker holdouts, and 7 PersonaMem-v2 units. Several later studies
explicitly reused the earlier model response; earlier studies independently produced the same
prediction from the same prompt. None can identify an HNG-specific reader effect.

At the policy level, production HNG and the independent Strong baseline make the same decision and
the same support/challenge scores on all 250 deterministic scenarios. This confirms that a new
reader holdout over the same policy regime has no preregistered HNG-specific treatment contrast.

The four synthetic Qwen/Mistral fixed-candidate reader studies are different at rendering time:
24 of 30 Strong/HNG pairs
per study have distinct context and prompt hashes, while six are identical. Reader outputs are
still equal in all 120 paired units. Those studies can identify an input effect, but the result is
an observed HNG/Strong tie, not superiority.

## Consequence

Public retrieval comparisons remain meaningful for BM25, dense, hybrid, reranked, and full-context
arms. The public Strong/HNG tie is a policy no-op check, not independent downstream evidence for or
against HNG. It must not be counted as an HNG-specific replication.

Any next Strong/HNG reader experiment must fail closed before inference unless development evidence
first establishes a policy-output difference and the frozen holdout has at least one paired unit
with distinct governed output and a distinct reader prompt. It must hold the pre-governance
candidate pool fixed, give Strong the same metadata and policy budget, preregister the expected
policy-changing cases, and retain a no-change stratum. Public text with injected metadata remains
public-data-plus-synthetic-corruption, not canonical public evidence.

Machine-readable result: `identifiability/RESULTS.json`.
