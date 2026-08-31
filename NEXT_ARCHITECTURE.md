# HNG Frontier 0.7 closure architecture

## Thesis

HNG 0.6 is an **evidence-governed episodic memory and control plane**. It does not own commodity ANN, lexical ranking, dense embeddings, language generation, or document hierarchy. It owns the rules that decide whether retrieved history may influence behavior.

```text
assistant / agent
      |
exact working state + effective profile
      |
query planner and required-state contract
      |
FAISS | BM25 | dense | hybrid | reference HNG
      |
access-safe candidate IDs
      |
temporal/version prefilter
      |
exact original semantic checks
      |
trust + independence + supersession + actor eligibility
      |
GovernedMemoryFrame
      |
support | challenge | conflicted | abstention
```

## Ownership boundaries

| Concern | Owner |
|---|---|
| Current state, goals, constraints, open loops | HNG deterministic state store |
| Episodic transition/action/outcome records | HNG SQLite evidence store |
| Binary ANN | FAISS by default |
| Small/dependency-free binary search | Exact reference provider |
| Lexical document retrieval | BM25 provider |
| Dense similarity | Pluggable dense provider |
| Hybrid candidate fusion | Provider layer / RRF |
| Access control | Exact SQL policy, never vector similarity |
| Applicability and final semantic truth | HNG exact original-value checks |
| Trust, deduplication, versions, supersession | HNG governance |
| Language reasoning/generation | External HDC interpreter or LLM |
| Production document hierarchy | External RAPTOR/GraphRAG/SVD-RAG-class provider when justified |

## Storage truth and derived state


`SQLiteEvidenceStore` is authoritative. It stores evidence identity, source-event identity, semantic values, provenance, trust, validity intervals, environment/policy versions, actor scope, supersession, and invalidation. Retrieval indexes are rebuilt from it and can fail without corrupting evidence.

Working state is a keyed SQLite snapshot. Native HDC state is stored exactly and carried directly; the immediately prior turn is never rediscovered with ANN.

## Provider selection

`semantic_backend="faiss-auto"` is the public default. `FaissBinaryRetriever` selects BinaryFlat below 50K records and BinaryIVF above it. Explicit modes are `faiss-flat`, `faiss-ivf`, `faiss-hnsw`, and `faiss-multihash`; `usearch-hamming` is also available. MultiHash and USearch remain explicit because measured recall/build/distribution tradeoffs do not support an automatic default. New writes remain in an exact mutable tail until rebuild. `reference-hng` is the dependency-free exact fallback.

FAISS proposes candidates only. `EvidenceAggregator` recomputes exact similarity against the original `SemanticValue` for every required head. The centrally configured action floor cannot be weakened by a caller.

## Query planning

`QueryPlanner` maps intent to a `QueryPlanV2` and `EvidenceRequirement`:

- recall requires `state`;
- action evaluation requires `state`, `goal`, `sequence`, and `action`;
- role-sensitive recommendations require an authoritative role and authority field;
- procedures require `goal` and `environment_version`;
- document evidence accepts lexical and optional semantic signals.

Missing required state returns `INSUFFICIENT_STATE` before retrieval or voting.

## Evidence identity

- `experience_id`: unique stored row;
- `source_event_id`: underlying real-world observation;
- `evidence_group_id`: logical family/pattern;
- `episode_id` and `conversation_id`: temporal context.

Only one record per `source_event_id` contributes to aggregation. Copying an event under new experience or group IDs does not create independent evidence.

## Perspective layers

1. Identity/access: exact user, tenant, and scope.
2. Eligibility: structured role, authority, abstraction, permissions.
3. Fuzzy qualities: optional expertise, priorities, interests, and style.

`PerspectiveField` includes confidence, source, confirmation, revision, and validity. Low-confidence inferred role/authority returns `PROFILE_UNCERTAIN` for critical plans. Conversation-local explicit overrides have recorded precedence.

## Concurrency and rollout

SQLite runs WAL + FULL synchronous mode. Public mutation/query paths use a control-plane lock so provider state and authoritative commits are observed coherently inside one process. Interrupted index rebuilds do not alter SQLite truth; reopen rebuilds derived state.

Rollout uses `GovernedShadowEvaluator`: shadow, context augmentation, advisory challenge, then explicit hard gate. Hard gate construction requires a separate opt-in flag.

## Package map

| Module | Responsibility |
|---|---|
| `semantic.py` | model-agnostic typed semantic values and required-state contracts |
| `storage_v2.py` | transactional evidence and working-state truth |
| `retrieval.py` | FAISS, exact binary, dense, BM25, hybrid provider protocols |
| `query_planner.py` | intent-specific requirements |
| `aggregation.py` | trust, independence, exact floors, decisions |
| `profiles.py` | uncertain/revisioned structured perspective |
| `control.py` | small `HNGMemory` facade |
| `integrations.py` | HDC, LLM, and RAG adapters |
| `document_stack.py` | BM25-first hybrid document retrieval |
| `beliefs.py` | revisioned beliefs, contradiction, supersession, invalidation |
| `consolidation_v2.py` | persisted reversible patterns retaining raw provenance |
| `provenance.py` | external verifier protocol and persisted verification result |
| `profiling.py` | component latency distributions |
| `tool_agent.py` | shadow/advisory/opt-in hard-gate tool integration |
| `shadow_v2.py` | safe staged deployment and behavior logs |

The 0.5 modules remain intact as a compatibility surface. New applications should import `HNGMemory`; old gauntlets continue to use `AssistantMemory`.

