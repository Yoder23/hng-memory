# HNG Frontier 0.5.0a1 — breakthrough-candidate report

## Thesis

HNG is testing one combined proposition:

> Native semantic state can serve as a persistent, model-external memory substrate for intelligent systems, supporting both experiential action control and whole-document semantic compression without requiring an LLM to own memory or summarization.

This alpha adds HDC-native document memory to the assistant transition-memory architecture from 0.3.x.

## Result A — memory changes assistant behavior

Focused synthetic ablation:

- 128 hard-neighbor HDC contexts;
- 2,048-bit semantic heads;
- 4,096-action library (256 families × 16 close variants);
- cross-chat historical outcomes.

Results:

- direct HDC exact-action top-1: **7.81%**;
- HNG historically grounded exact-action top-1: **100%**;
- HNG evidence came from other chats: **100%**;
- ambiguous current-turn-only context recovery: **0.78%**;
- HNG prior-state carry context recovery: **100%**.

This does not say HNG is intrinsically more intelligent than HDC. It demonstrates that a semantic action family can be ambiguous while historical state/action/outcome evidence resolves the exact choice.

The larger 0.3.1 gauntlet separately demonstrated 16,384 actions, changed-world sequence constraints, support/challenge/insufficient evidence, 15% query noise, 10,240 historical chats, and a 20,000-turn conversation.

## Result B — HDC can form a document synopsis without an LLM

32-document synthetic benchmark:

- 8,960 document units;
- 2,048-bit HDC heads;
- skewed dominant and rare themes;
- rare caveats, contradictions and conclusions;
- no LLM calls;
- 40-unit evidence budget.

HNG recovered:

- semantic-theme coverage: **100%**;
- key-claim recall: **98.0%**;
- priority/rare evidence: **100%**;
- contradictions: **100%**;
- semantic-boundary F1: **1.00**.

A naive semantic top-k baseline covered ~21.7% of themes. MMR recovered all themes but only ~57.2% of designated key claims. An oracle KMeans hierarchy given the true number of semantic regions reached perfect coverage but was ~2.4× slower at median than HNG on this workload.

A 128-theme, 8,960-unit single document was compressed to 140 evidence units with 100% theme/key/priority coverage in ~440 ms.

## What is genuinely new vs what is not

Not new by itself:

- vector retrieval;
- HDC/VSA associative memory;
- hierarchical document retrieval;
- multi-vector fields;
- external agent memory;
- ANN + exact reranking;
- global-document summarization as a research objective.

The potential contribution is the **coherent HDC-native control plane**:

1. deterministic native-state continuity between turns;
2. independently addressable state/goal/entity/sequence/action/outcome heads;
3. conjunctive approximate routing followed by exact full-state floors;
4. explicit historical outcome evidence for action evaluation;
5. document-level and segment-level semantic prototypes in the same native representation;
6. HDC role/exception retrieval for coverage-oriented summaries;
7. language generation made optional rather than part of memory construction.

## Closest existing directions

- RAPTOR recursively clusters and summarizes chunks into a retrieval tree; its higher-order nodes are created via abstractive summarization.
- Microsoft GraphRAG builds entity/relationship communities and LLM-generated community reports for global queries.
- LongMemEval-V2 evaluates whether memory systems internalize long histories into compact evidence for static state, dynamic state, workflow knowledge, environment gotchas and premise awareness.
- HDC/VSA already provides binding, bundling, sequence operations and associative retrieval; HNG's question is whether those primitives can support a practical long-horizon memory/control layer at modern scale.

## What would elevate this from a breakthrough candidate to a breakthrough result

1. Real HDC assistant traces: statistically significant improvement in task success / action regret / constraint adherence with HNG enabled.
2. Public memory benchmarks: LongMemEval-V2 and related long-horizon tasks.
3. Public document benchmarks: BillSum/GovReport or comparable long-document datasets with ROUGE plus factual/coverage evaluation.
4. Direct retrieval baselines: FAISS binary, USearch Hamming and competitive multi-vector ANN at matched recall.
5. Strong memory-system baselines: Hindsight/MAGMA-style structured memory where reproducible.
6. Ablations proving the gains come from semantic conjunction, state continuity and outcome memory—not synthetic labels or a favorable encoder.
7. Adversarial memory: poisoning, contradictory evidence, stale rules, missing state variables and distribution shift.

Until those gates are passed, the correct public description is **breakthrough candidate / research preview with strong synthetic evidence**.

## Stronger trivial baselines

The latest document run also includes position-only baselines. Uniform sampling of 40 units achieved 100% theme coverage—showing that broad coverage alone is not a sufficient claim—but recovered only 23.0% of designated key claims, 17.4% of priority evidence and 11.5% of contradictions. This is why the research target is **structured salient/exception coverage with provenance**, not merely touching every region of a document.


## Result C — perspective conditioning changes the answer to the same semantic query

0.5 adds an actor-conditioned gauntlet specifically for the "one-size-fits-all assistant" failure mode. The semantic state is held constant while eight personas vary role, authority, abstraction, expertise and priority. The action library contains 8,192 HDC actions with 16 deliberately close variants per family.

Results:

- raw HDC action top-1: **6.25%** (family top-16: 100%);
- HNG semantic memory without user perspective: **12.5%**;
- role/authority gating alone: **50%** on a 128-query sample;
- soft HDC perspective/expertise/priority heads: **100%** on a 128-query sample;
- full perspective-conditioned HNG: **100%** over 512 queries;
- semantic-only role violation rate: **75%**;
- full HNG role violation rate: **0%**;
- same-user active-role switch: **64/64**;
- private-memory leakage: **0** in the adversarial checks.

This is not evidence that user personalization is solved. It demonstrates a concrete failure of semantics-only routing and a mechanism for separating topic meaning from actor appropriateness. The public gate is PersonaMem/PersonaMem-v2/LaMP-style evaluation with the production HDC interpreter.
