# Prior art and benchmark bar

Research cutoff: 2026-09-01.

This review uses primary papers, official repositories, and official documentation. Reported
scores are **literature evidence**, not local reproductions, unless a row explicitly says
otherwise. Different readers, judges, dataset revisions, token budgets, and hardware make
cross-paper ranks unsafe. Missing information is written as **NR**, never inferred.

## What changed the decision bar

The original LongMemEval/LoCoMo benchmark generation is now crowded with reported scores in
the high 80s and 90s. Mem0 reports 94.8% on LongMemEval, Hindsight reports 91.4%, and APEX-MEM
reports 86.2%. These are not interchangeable protocols, but they make a weak RAG comparison
scientifically irrelevant. LongMemEval-V2 instead tests whether memory converts up to 500 prior
web-agent trajectories and 115M tokens into environment-specific working knowledge.
PersonaMem-v2 similarly makes implicit, evolving preference inference—not explicit profile
lookup—the personalization bar.

HNG's falsifiable claim is therefore narrower:

> Given the same candidate evidence and downstream model, does explicit applicability
> governance improve behavior under temporal change, duplication, contradiction, trust,
> provenance, actor scope, and known action outcomes?

## Agent memory systems

| System | Architecture; representation and storage | Retrieval | Time / contradiction | Profile / provenance | Learned vs deterministic | Reported result, compute, latency | Reproducibility |
|---|---|---|---|---|---|---|---|
| [Letta / MemGPT](https://github.com/letta-ai/letta) | Agent-managed context hierarchy; current Letta uses Git-backed Markdown MemFS plus message recall | Agent/tool-directed search and context editing | Version history; revision policy is agent-mediated | User/persona blocks; Git history is not evidence authority | LLM-managed | No directly comparable fixed-candidate score; compute/latency NR | Apache-2.0 code; full evaluation depends on models/services |
| [Mem0](https://github.com/mem0ai/mem0) | Extracted facts and entity links; April 2026 pipeline is append-only ADD | Single-pass semantic + BM25 + entity fusion with temporal ranking | Time-aware retrieval; current algorithm accumulates rather than UPDATE/DELETE | User/session/agent scopes; authority semantics NR | LLM extraction + deterministic fusion | Official repo reports LongMemEval 94.8 top-50, LoCoMo 91.6, 6.8–7K tokens, p50 0.88–1.09 s | OSS library and [benchmark code](https://github.com/mem0ai/memory-benchmarks); managed-v3 parity must be verified |
| [Zep / Graphiti](https://github.com/getzep/graphiti) | Entity/fact temporal knowledge graph with episodic source edges | Semantic, keyword and graph traversal | Bi-temporal valid/invalid intervals and evolving facts | Group scope and episode provenance; profile layer NR | LLM extraction + deterministic graph queries | Comparable current score/compute/latency NR | Apache-2.0 code; graph DB and LLM required |
| [Hindsight](https://arxiv.org/abs/2512.12818) | Four logical networks for world facts, experiences, entity observations and evolving beliefs; sparse/dense vectors, entities and time | Retain/recall/reflect with structured multi-path recall | Temporal/entity-aware; reflection updates traceable beliefs | Banks and metadata filters; evidence/inference separated | LLM extraction/reflection + deterministic substrate | Paper reports 83.6% LongMemEval with open 20B and 91.4% with larger backbone; LoCoMo up to 89.61%; local latency NR | [MIT repository](https://github.com/vectorize-io/hindsight); model services required |
| [MAGMA](https://aclanthology.org/2026.acl-long.1709/) | Every item spans semantic, temporal, causal and entity graphs | Intent-aware policy chooses and traverses views, then fuses subgraphs | Temporal and causal graphs explicit; conflicting paths exposed | Entity structure; actor profile/source authority NR | Policy-guided and LLM-assisted | Paper reports LoCoMo/LongMemEval gains plus lower token use/latency; exact values are setup-specific | [Official code](https://github.com/FredJiang0324/MAGMA); model services required |
| [APEX-MEM](https://aclanthology.org/2026.acl-long.749/) | Append-only entity-centric property graph of temporally grounded events | Multi-tool retrieval agent produces a compact summary | Query-time resolution of conflicting/evolving information while retaining history | Entity-centric; source authority/profile policy NR | LLM agent over deterministic graph | 88.88% LoCoMo QA and 86.2% LongMemEval; compute/latency NR | Paper available; no official runnable repo located |
| [Memory-R1](https://aclanthology.org/2026.acl-long.583/) | External structured memory with Memory Manager and Answer Agent | Answer Agent preselects entries and reasons | Manager emits ADD/UPDATE/DELETE/NOOP; detailed temporal model NR | Profile/provenance authority NR | PPO/GRPO, only 152 training QA pairs | Reported gains on LoCoMo, MSC, LongMemEval across 3B–14B; latency NR | Paper available; official code/checkpoints not located |
| [GAM](https://aclanthology.org/2026.acl-long.1600/) | Event-progression graph consolidated into topic-associative network on semantic shifts | Graph-guided multi-factor retrieval | Separates fast capture from stable consolidation | Profile/provenance authority NR | LLM extraction + structured hierarchy | Paper reports LoCoMo/LongDialQA and efficiency gains; exact values setup-specific | Paper available; code status not established |
| [HyperMem](https://aclanthology.org/2026.acl-long.1627/) | Hypergraph conversational memory | Hyperedge-aware retrieval | Multi-way event relations; exact contradiction policy NR | Profile/provenance authority NR | Mixed structured/LLM pipeline | Paper results only; compute/latency NR | Paper available; code status not established |
| [HeLa-Mem](https://aclanthology.org/2026.acl-long.625/) | Dynamic graph with Hebbian association strength | Association-weighted graph recall | Online evolution; explicit contradiction policy NR | Profile/provenance authority NR | Hebbian learning + LLM components | Paper results only; compute/latency NR | Paper available; code status not established |
| [PlugMem](https://github.com/TIMAN-group/PlugMem) | Task-agnostic plug-in long-term memory service | Learned/agent memory plug-in | Paper-specific; authority semantics NR | NR | Learned components | ICML 2026 reported task results; no local comparison | Official code public |

## Public memory and personalization benchmarks

| Benchmark/system | What it measures | Public scale / protocol | Current implication | Reproducibility |
|---|---|---|---|---|
| [LongMemEval](https://github.com/xiaowu0162/LongMemEval) | Information extraction, multi-session reasoning, updates, temporal reasoning, abstention | 500 questions; cleaned histories and judge scripts | Useful but increasingly saturated and sensitive to reader/judge/data revision | Official data/code; canonical LLM judge needed |
| [LongMemEval-V2](https://github.com/xiaowu0162/LongMemEval-V2) | Static state, dynamic state, workflow, environment gotchas, premise awareness from agent trajectories | Small/medium/large; up to 500 sessions and 115M tokens; latency-adjusted leaderboard frontier | Central public test for HNG action/outcome and environment-version claims | Official code/data; fixed reader, controller/embedding endpoints and canonical judge needed |
| [LoCoMo](https://github.com/snap-research/locomo) | Multi-session single-hop, multi-hop, temporal and open-domain QA | Ten long conversations with generated QA | Relevant to episodic/temporal recall; protocol and judge revision must be pinned | Public data/code; LLM judge common |
| [LoCoMo-Plus](https://github.com/xjtuleeyf/Locomo-Plus) | Latent user state, goals and values under cue–trigger semantic disconnect | Public conversations and constraint-consistency framework | Stronger applicability test than explicit recall | Public code/data; canonical judging needs compatible model |
| [PersonaMem](https://github.com/bowen-upenn/PersonaMem) | Evolving profile inference and personalized response | Multi-session public generation/evaluation pipeline | Explicit dictionary lookup is insufficient evidence | Public code; API dependent |
| [PersonaMem-v2](https://github.com/bowen-upenn/PersonaMem-v2) | Mostly implicit preferences over long histories | 1,000 users, 300+ scenarios, 20K+ preferences, up to 128K context | Paper: frontier LLMs 37–48%, Qwen3-4B RFT 53%, 2K-token agent memory 55% | Public data/code; original Docker expects CUDA 12.6 and configured APIs |
| [PersonaAgent](https://aclanthology.org/2026.findings-acl.1315/) | Personalized test-time decisions and actions | Episodic + semantic memory and personalized action module; LaMP protocols | Relevant memory-to-action competitor | Paper available; complete assets must be audited |
| [LaMP](https://aclanthology.org/2024.acl-long.399/) | Seven personalized classification/generation tasks over user histories | Official retrieval-personalization baselines | Strong conventional history/profile baseline, not a dynamic-state proof alone | [Official code](https://github.com/LaMP-Benchmark/LaMP) |

## HDC / VSA associative memory

| System/work | Representation and storage | Retrieval / temporal semantics | Evidence bar |
|---|---|---|---|
| [IEEE HDC/VSA](https://cis.taskforce.ieee.org/hdcvsa/) | Binary/bipolar high-dimensional compositional vectors; binding, bundling, permutation | Associative similarity; durable governance is application-defined | HDC association is prior art; novelty cannot rest on XOR/Hamming |
| [TorchHD](https://github.com/hyperdimensional-computing/torchhd) | Standard VSA models and memory modules on PyTorch | Exact/learned associative memory | Reproducible matched-HDC library baseline |
| [agidb](https://github.com/rohansx/agidb) | Rust embedded HDC store with episodes, beliefs, goals and self-model | Content-addressable recall, bi-temporal supersession, consolidation, unlearn | Strong adjacent engineering; benchmark claims require reproduction |
| [Kohaku](https://github.com/konjoai/kohaku) | Bipolar episodes; optional dense-to-SimHash encoder; SQLite provenance/version stores | Exact cosine or LSH candidate generation then exact rerank | Shows HDC may be compact while semantics still originate in dense embeddings |
| [MEMHD](https://arxiv.org/abs/2502.07834) | Multi-centroid HDC for in-memory hardware | Associative classification | Efficiency/robustness evidence, not assistant governance |

## Retrieval infrastructure and RAG

| System | Architecture / representation | Temporal, contradiction, profile, provenance | Reported result / local status | Reproducibility |
|---|---|---|---|---|
| [FAISS binary](https://github.com/facebookresearch/faiss/wiki/Binary-indexes) | BinaryFlat, BinaryIVF, BinaryHNSW, BinaryHash/MultiHash over Hamming | Caller filters only | **Locally reproduced** 100K, 1M and inherited 10M; retained backend | Mature MIT code |
| [USearch](https://github.com/unum-cloud/usearch) | HNSW with native b1 packed vectors and Hamming/Jaccard | Caller policy only | **Locally reproduced** 100K/1M; did not displace FAISS | Apache-2.0 code |
| BM25 | Sparse lexical ranking | No inherent time/authority policy | **Locally reproduced QMSum win** over HNG text geometry; retained dependency | Standard implementations |
| Dense RAG | Dense embedding ANN | No inherent time/authority policy | Required baseline; embedding/model must be frozen | Widely reproducible |
| Hybrid + reranker | Sparse+dense fusion then cross-encoder/LLM reranker | Can infer applicability from supplied text but no guaranteed policy contract | Strong default; candidate pool must freeze before HNG | Reproducible with frozen models |
| [Microsoft GraphRAG](https://github.com/microsoft/graphrag) | LLM-extracted entity graph, hierarchical communities, local/global search | Source text retained; temporal/authority policy application-defined | Not local; high indexing cost and different global-synthesis objective | Official MIT code; model APIs needed |
| [RAPTOR](https://proceedings.iclr.cc/paper_files/paper/2024/hash/8a2acd174940dbca361a6398a4f9df91-Abstract-Conference.html) | Recursively embed, cluster and LLM-summarize retrieval tree | No inherent temporal/actor policy | Paper reports strong QA gains including +20 absolute QuALITY with GPT-4 versus cited prior best | [Official code](https://github.com/parthsarthi03/raptor) |
| [SVD-RAG](https://arxiv.org/abs/2607.10316) | Deterministic SVD extractive summaries in RAPTOR-like tree | No inherent temporal/actor policy | Paper: MRR .867 vs RAPTOR .875, Recall@1 .483 vs .458, 317x faster build in its small controlled corpus | Paper says package released; official repository not discovered |

### Retrieval-budget implication after the LoCoMo-Plus loss

The [official LoCoMo release](https://github.com/snap-research/locomo) evaluates RAG over generated
session observations and summaries, making candidate construction and retained context part of the
benchmark system rather than a fixed constant. Current official implementations also expose wider
retrieval regimes: [SYNAPSE](https://github.com/hq0709/synapse) reports recall@30 and uses a
Top-K(15) graph sparsity gate, while [LazyMem](https://github.com/allacnobug/LazyMem) releases a
hybrid dense/BM25/cross-encoder pipeline that saves and windows top-50 LoCoMo results. Their scores
are not locally comparable, but the configurations make a top-16-only evaluation too narrow to
diagnose retrieval-budget sensitivity. HNG therefore preregisters a disjoint 16/32/64-turn sweep;
this changes retrieval candidates and is analyzed separately from fixed-candidate governance.

## Architectural consequences

1. Keep retrieval modular. FAISS, BM25, dense/hybrid, graph and hierarchical systems may
   supply candidates. HNG must not claim to replace them.
2. Literature numbers are an eligibility bar, not a local win. Only official locally reproduced
   protocols enter HNG's result column.
3. Give StrongStructuredBaseline all metadata: tenant, validity, trust, provenance, profile and
   outcome. If it reproduces HNG more simply, HNG loses.
4. Require fixed-candidate tests. Different candidates do not isolate governance.
5. Do not protect HDC. Dense and HDC heads must run behind identical governance.
6. Do not claim the real-HDC gate. No trained production assistant checkpoint or real traces are
   present. Synthetic vectors cannot substitute.

## Evidence separation

Artifacts under baseline_070 are local machine evidence. This document is literature evidence
except for rows explicitly labeled locally reproduced. Published competitor scores are never
copied into RESULTS.json as if they were local comparisons.
