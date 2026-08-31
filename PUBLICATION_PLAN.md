# Publication plan

## Proposed research claim

**HNG: Native Hyperdimensional State as Persistent Episodic Memory, Evidence Control, and Hierarchical Document Context for Intelligent Agents**

The paper should not claim that HNG replaces all RAG. It should test whether HNG moves retrieval augmentation from text-chunk similarity to a more general memory substrate in which the model's semantic state is also its memory address.

## Core experiments

### Agent memory

Compare the same model/interpreter with and without HNG on long-horizon tasks. Primary outcomes: task success, repeated-failure rate, action regret, contradiction detection, constraint violations, unsupported actions and provenance quality.

### Retrieval

Matched-recall latency/RSS/build/update comparisons against binary FAISS, USearch Hamming and strong multi-vector systems.

### Long-document understanding

Evaluate HNG synopsis and document Q&A on BillSum/GovReport (and, where feasible, scientific long-document data). Report ROUGE for extractive renderings, semantic/factual coverage, contradiction/exception recall, source attribution, index/build cost and query cost.

Compare to:

- flat top-k RAG;
- MMR/diversity retrieval;
- clustering/hierarchical extractive baselines;
- RAPTOR/GraphRAG results or runnable implementations under clearly matched conditions;
- direct full-context models when document length permits.

### Ablations

Remove one component at a time:

- no deterministic state carry;
- one composite state instead of independent heads;
- no exact semantic floors;
- no outcome memory;
- no semantic-role head;
- no hierarchical document prototypes;
- no adaptive probing.

## Falsification rule

If HNG improves only latency, it is an index.

If HNG improves evidence retrieval/coverage but not downstream behavior, it is a memory retrieval system.

If HNG materially improves long-horizon decisions and document understanding across real workloads/models while preserving explicit provenance and external control, the broader cognitive-substrate claim is supported.


## Personalization / perspective experiment

Add a dedicated actor-conditioned evaluation track. Compare:

- query semantics only;
- profile text in an LLM/system prompt;
- retrieval-augmented user history (LaMP-style);
- soft HDC perspective heads only;
- HNG exact access + actor eligibility + HDC perspective/expertise/priority heads.

Primary metrics should include ordinary task accuracy plus **perspective violation rate**, authority-inappropriate action rate, cross-user leakage, profile-update adaptation, active-role-switch accuracy, and token/context cost. PersonaMem/PersonaMem-v2 and LaMP are appropriate public gates; PersonaAgent is relevant related work for personalized memory/action agents.
