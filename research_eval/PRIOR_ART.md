# Current prior art review

Research cutoff: 2026-08-31. Dates and claims below come from the linked primary paper, official repository, or product documentation. Published scores are Tier C literature evidence unless this evaluation explicitly says they were reproduced; they are not mixed into local result tables.

## Agent and long-horizon memory

| System | Date / source | Architecture and representation | Retrieval / memory semantics | Reported evaluation | Local status and comparability |
|---|---|---|---|---|---|
| MemGPT / Letta | 2023 paper; active framework | LLM-managed tiered context with archival and recall memory | Function calls move data across context tiers | MemGPT paper evaluates conversational agents and document analysis | Not reproduced; conceptual comparison only. It is an agent memory manager, not a binary ANN. [Paper](https://arxiv.org/abs/2310.08560), [Letta](https://github.com/letta-ai/letta) |
| Hindsight | 2025-12 preprint; ACL 2026 demo | Four logical memory networks for world, experience, opinion, and observation | Structured ingestion, consolidation, and query-time recall | Repository reports 91.4 on original LongMemEval | Not reproduced; published score is not comparable to HNG synthetic tests. [Paper](https://arxiv.org/abs/2512.12818), [repository](https://github.com/vectorize-io/hindsight) |
| MAGMA | ACL 2026 | Multi-graph agent memory | Graph-structured storage and multi-path retrieval | Paper reports LoCoMo overall 0.700 with GPT-4o-mini, above several listed memory systems | Not reproduced; literature-only. [ACL paper](https://aclanthology.org/2026.acl-long.309/) |
| APEX-MEM | 2026-04 preprint | Append-only temporal property graph | An agent chooses retrieval tools and reasons over temporal relations | Evaluated on long-term conversational-memory tasks | Not reproduced; stronger explicit temporal model than HNG's caller-supplied sequence head. [Paper](https://arxiv.org/abs/2604.14362) |
| Memory-R1 | ACL 2026 | Learned memory manager and answer agent | RL-trained ADD/UPDATE/DELETE/NOOP operations | LoCoMo, MSC, and LongMemEval | Not reproduced; learned memory policy and benchmark results are not directly comparable to HNG's deterministic API. [ACL paper](https://aclanthology.org/2026.acl-long.1029/) |
| LongMemEval | ICLR 2025 | Benchmark, not a backend | Five long-term memory abilities across long chat histories | Official benchmark | Not run because this release has no production text-to-HDC interpreter or common reader model. [Paper](https://arxiv.org/abs/2410.10813), [repository](https://github.com/xiaowu0162/LongMemEval) |
| LongMemEval-V2 | 2026-05 | 451 questions with up to 500 trajectories / 115M tokens | Tests memory plus environment interaction | Paper reports AgentRunbook-C 72.5%, vanilla coding agent 69.3%, strong RAG 48.5% under its setup | Not reproduced; literature-only and later than the shipped HNG claims. [Paper](https://arxiv.org/abs/2605.12493), [repository](https://github.com/xiaowu0162/LongMemEval) |
| LoCoMo-Plus | 2026-02 preprint / ACL 2026 | Long-context conversational benchmark extension | Tests grounded long-term dialogue memory | Official benchmark results in paper | Not reproduced; no HNG win inferred. [Paper](https://arxiv.org/abs/2602.10715) |

The prior art makes HNG's broad "cognitive substrate" claim unproven. Current systems explicitly manage temporal updates, consolidation, graph relations, or learned memory operations and are evaluated with language models on public long-horizon tasks. HNG's local evidence establishes deterministic behavior on generated HDC states, not parity on those workloads.

## Personalization

| System | Date / source | Memory design | Public evaluation | Local status |
|---|---|---|---|---|
| LaMP | ACL 2024 | Retrieval-augmented personalization over user histories | Seven personalized language tasks | Not reproduced. [Paper](https://aclanthology.org/2024.acl-long.399/), [repository](https://github.com/LaMP-Benchmark/LaMP) |
| PersonaMem | COLM 2025 | Benchmark for learning user preferences from interaction history | Preference-memory tasks | Not reproduced. [Repository](https://github.com/bowen-upenn/PersonaMem) |
| PersonaMem-v2 | 2025-12 preprint | 1,000 interactions, about 20K preferences, 128K context | Paper reports frontier models around 37-48%, Qwen3-4B 53%, and an agentic memory setup 55% with a 2K-token budget | Not reproduced; literature-only. [Paper](https://arxiv.org/abs/2512.06688) |
| PersonaAgent | Findings of ACL 2026 | Episodic and semantic persona memory with actions | Public personalization tasks | Not reproduced. [ACL paper](https://aclanthology.org/2026.findings-acl.119/) |

HNG correctly separates access scope, authority eligibility, and soft perspective similarity. That separation is good security design. The synthetic accuracy does not show an HDC advantage: an ordinary dictionary keyed by the explicit fields and a dense multi-head equivalent each reached 100% locally.

## HDC and associative memory

| Work | Source | Relevance |
|---|---|---|
| HDC/VSA survey | 2024 | Associative memory, binding, bundling, and distributed binary/bipolar representations are established HDC concepts, so they are not individually novel. [Journal of Big Data survey](https://journalofbigdata.springeropen.com/articles/10.1186/s40537-024-00978-z) |
| agidb | Current repository checked 2026-08 | HDC-oriented cognitive database/substrate; adjacent engineering prior art. No direct benchmark was run. [Repository](https://github.com/agi-db/agidb) |
| Kohaku | Current repository checked 2026-08 | HDC episodic memory engine; adjacent representation prior art. No direct benchmark was run. [Repository](https://github.com/Continuum-Research/Kohaku) |

The potentially differentiated HNG contribution is therefore the software contract joining exact state carry, typed transition/outcome records, conjunctive head floors, policy decisions, and provenance. It is not the discovery of HDC associative memory.

## Binary ANN and multi-vector retrieval

| System | Current capability | Reproduction / implication |
|---|---|---|
| FAISS 1.15.0 | BinaryFlat, BinaryIVF, BinaryHNSW and binary hash families over Hamming distance | BinaryFlat, BinaryIVF, and BinaryHNSW were run locally. BinaryIVF beat HNG at matched exact top-1 at 100K, 1M, and 10M. [Official binary-index documentation](https://github.com/facebookresearch/faiss/wiki/Binary-indexes) |
| USearch 2.26.1 | Native `b1` vectors and Hamming metric in a compact HNSW implementation | Run locally. Competitive on clustered 100K data but did not reach HNG recall on 1M independent data by expansion 128. [Repository](https://github.com/unum-cloud/usearch) |
| DiskANN | Graph ANN with SSD-scale and filtered/fresh variants | Not run: the supported representation/metric path was not a clean packed-Hamming comparison. [Repository](https://github.com/microsoft/DiskANN) |
| Qdrant | Binary quantization with optional original-vector rescoring | Not run; its binary quantization pipeline is not identical to native supplied HDC bits. [Documentation](https://qdrant.tech/documentation/guides/quantization/#binary-quantization) |
| Milvus | Multiple vector fields plus weighted or reciprocal-rank hybrid fusion | Not run locally; relevant as an off-the-shelf multi-head orchestration alternative. [Documentation](https://milvus.io/docs/multi-vector-search.md) |
| Weaviate | Named vectors / multi-target vector search and join strategies | Not run locally; relevant to multi-vector fusion, though not an exact per-head-floor substitute by itself. [Documentation](https://docs.weaviate.io/weaviate/search/multi-vector) |

FAISS BinaryIVF is the strongest directly executed low-level competitor. The clean design is one binary index per head, candidate union/intersection, then HNG's exact metadata filters and full-HV floors. This preserves HNG semantics without maintaining HNGIX.

## Document and global retrieval

| System | Date / architecture | Evaluation status |
|---|---|---|
| RAPTOR | ICLR 2024; recursively clusters and summarizes text into a retrieval tree | Not run; requires a generator/embedding stack absent from the release. It is a stronger public hierarchical baseline than flat top-k. [Paper/repository](https://github.com/parthsarthi03/raptor) |
| Microsoft GraphRAG | LLM-extracted entity graph, community hierarchy, local/global search | Not run; high-cost and semantically different, but directly relevant to cross-document/global synthesis. The official repository is in maintenance mode as of 2026. [Repository](https://github.com/microsoft/graphrag) |
| SVD-RAG | 2026-07 preprint; deterministic SVD-derived hierarchy without LLM-generated intermediate summaries | Not run. The paper reports MRR 0.867, results within 1-5% of RAPTOR, and major token savings; literature-only. [Paper](https://arxiv.org/abs/2607.10316) |
| QMSum | EMNLP 2021 meeting summarization dataset | Official test data reproduced on a fixed first-20 subset. HNG did not win. [Repository](https://github.com/Yale-LILY/QMSum) |

## Bottom line from prior art

No current competitor was counted as defeated merely because its full stack was too costly or unavailable. The directly comparable evidence is narrower: FAISS defeats HNGIX on raw ANN; simple structured/dense baselines tie HNG personalization; and public QMSum baselines defeat HNG documents. Modern agent-memory publications further raise the bar that HNG has not yet attempted on public end-to-end tasks.
