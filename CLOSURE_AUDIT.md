# HNG Frontier 0.7 closure audit

## Outcome

Release classification: **B — Publication-ready research system**. The release is assistant-integration complete for its documented APIs and has reproducible public, provider, fault, security, and performance evidence. It is not a production control-plane candidate or a default autonomous hard gate.

The frozen starting commit is recorded in `closure_eval/BASELINE_COMMIT.txt`. Baseline outputs are under `closure_eval/baseline/`; final machine outputs are under `closure_eval/raw/` and `closure_eval/final/`.

## Mandatory gates

All inherited and closure tests pass; the canonical adversarial suite is 11/11; the expanded adversarial/regression selection passes; inherited assistant/perspective/turn-stream gauntlets pass; leakage is zero; required state fails closed; duplicate, stale/superseded, and low-trust poisoning attacks do not manufacture support; complete HDC/LLM/RAG/provenance/tool adapters are present; fault injection is 10/10; a 300-query component profile exists; and official QMSum was executed.

## All 38 phases

| Requirement | Previous audit | Final status | Evidence |
|---|---|---|---|
| 1. Provider abstractions | Complete | Complete | Retriever/store protocols and replaceable providers |
| 2. FAISS/default HDC ANN | Partial | Closed with measured selection | Flat/IVF/HNSW/MultiHash/USearch; provider result JSON |
| 3. Exact full-HDC verification | Complete | Complete | `vector_exact_verification` trace/profile |
| 4. Required-state contracts | Complete | Complete | Missing-head adversaries return `INSUFFICIENT_STATE` |
| 5. Evidence identity/deduplication | Complete | Complete | Source-event independence tests |
| 6. Temporal validity/supersession | Complete | Complete | stale, expiry, invalidation, version tests |
| 7. Trust/provenance | Partial | Closed with external verifier boundary | `provenance.py`, `PROVENANCE_SECURITY.md` |
| 8. Evidence aggregation | Complete | Complete | auditable support/challenge/conflict factors |
| 9. Perspective policy | Partial | Complete | revision history plus all named change tests |
| 10. Profile uncertainty | Complete | Complete | inferred-to-confirmed and critical uncertainty tests |
| 11. Deterministic HDC working state | Partial | Complete | exact turns/facts/goals/etc.; 100-turn restart replay |
| 12. Model-agnostic semantics | Complete | Complete | HDC/dense/structured/lexical `SemanticValue` |
| 13. HDC adapter | Partial | Complete | explicit perspective/frame contract and runnable loop |
| 14. LLM adapter | Partial | Complete | deterministic bounded sections/token controls |
| 15. RAG integration | Partial | Complete | top-level chunk ingest/search/governance |
| 16. BM25-first documents | Complete | Complete, external hierarchy boundary | QMSum loss preserved; interoperability documented |
| 17. Evidence types | Complete | Complete | explicit evidence enum including model inference |
| 18. Belief/fact separation | Partial | Complete | persisted revision/supersession/invalidation history |
| 19. Consolidation/forgetting | Partial | Complete | persisted reversible patterns; explicit no-delete policy |
| 20. Poisoning defenses | Complete | Complete | canonical and expanded adversaries |
| 21. Stable decisions | Complete | Complete | structured `Decision` vocabulary |
| 22. Query planner | Complete | Complete | intent-specific fail-closed plans |
| 23. Public API | Complete | Complete | compact `HNGMemory` facade |
| 24. Backward compatibility | Complete | Complete | unchanged inherited gauntlets |
| 25. Regression suite | Complete | Complete | final pytest and gauntlet outputs |
| 26. Canonical 11 adversaries | Complete | Complete | 11/11 final result |
| 27. New adversaries | Complete | Complete | >30 governed scenarios plus closure cases |
| 28. Prior-art/provider benchmarks | Complete | Complete with honest limits | 100K/1M, inherited feasible 10M, geometry trials |
| 29. Behavioral evaluation | Partial | Closed for native HDC + public QMSum | A/B and QMSum; common-LLM not run |
| 30. Shadow/tool rollout | Partial | Complete | tool preflight/log/feedback; hard gate opt-in |
| 31. Observability | Partial | Complete | candidates, factors, scores, exclusions, reasons |
| 32. Explainability | Complete | Complete | machine JSON and bounded prompt frame |
| 33. Performance | Partial | Complete | 300-query component distributions |
| 34. Concurrency/persistence | Partial | Complete for single-host scope | 10/10 process fault suite; distributed scope excluded |
| 35. Security/access isolation | Complete | Complete for tested scope | zero private/tenant leakage; corrupt data fail-closed |
| 36. Documentation | Complete | Complete | closure document set and architecture diagrams |
| 37. Package structure | Complete | Complete | separated modules and compatibility surface |
| 38. Release deliverables | Complete | Complete | docs, results, wheel, sdist, hashes, GitHub release |

## Personal adoption decision

1. Frontier HDC assistant: **yes with caveats** — use exact state carry, transition/outcome evidence, actor policy, and FAISS providers; retain shadow rollout until domain evidence matures.
2. LLM assistant: **yes with caveats** — use HNG as a bounded evidence harness around established retrieval, but first run a same-model/same-prompt task A/B.
3. Enterprise RAG assistant: **yes with caveats** — use it for governance/state/provenance, while keeping BM25, dense retrieval, and external hierarchy systems in charge of retrieval.
4. Tool-using autonomous agent: **no** as the primary safety/control authority — use it in shadow/advisory mode; the release lacks multi-node security operations and real high-impact tool outcome evidence required for sole hard gating.

