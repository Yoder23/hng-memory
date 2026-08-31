# HNG Frontier 0.7.0rc1

This closure release completes the assistant integration surfaces and preserves the 0.5/0.6 compatibility behavior.

## Added

- FAISS BinaryMultiHash and USearch Hamming providers, exact mutable-tail visibility, and distribution-sensitive provider benchmarks.
- Revision-aware actor policy for role, authority, permission, responsibility, abstraction, expertise, and priority.
- Restart-safe exact turns, corrections, commitments, facts, goal, loops, constraints, episode, and prior semantic state.
- Complete native HDC and bounded LLM adapters; top-level hybrid document/RAG and tool-agent adapters.
- First-class belief revisions and persisted reversible consolidation/retention policy.
- Pluggable provenance verification with persisted identity/status/reference/time.
- Full decision traces, component profiler, generation-coherent queries, and process fault-injection suite.
- Public governed-memory retrieval evaluation on official QMSum.

## Evidence

- 94/94 full tests; 64/64 expanded adversarial selection; canonical 11/11.
- Fault/concurrency injection 10/10; private and tenant leakage zero.
- Inherited assistant and perspective gauntlets preserved, including 20K-turn restart behavior.
- QMSum: BM25 64.93% span hit@5, deterministic HDC hybrid 55.22%, governed candidates 55.97%. BM25 remains the retrieval winner.
- Built wheel and sdist; the wheel passed an isolated install/persistence smoke test.

## Classification and limitations

Classification: **B — Publication-ready research system**. Hard blocking remains opt-in. No common-LLM, LongMemEval-V2, PersonaMem-v2, GovReport, distributed multi-node, or production tool-safety claim is made. See `CLOSURE_AUDIT.md` and `closure_eval/RESULTS.json`.

