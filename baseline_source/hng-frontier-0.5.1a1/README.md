# HNG Frontier Memory

HNG is an evidence-governed memory and control layer for intelligent assistants. It maintains durable working state and episodic experience, evaluates whether retrieved memories are current, independent, trustworthy, and actor-appropriate, and exposes structured evidence to HDC-native or LLM-based reasoning systems.

Version: **0.7.0rc2**

The project no longer treats a custom ANN or document segmenter as its central contribution. FAISS, BM25, dense retrieval, and hybrid RAG are providers. HNG owns the control-plane decisions those systems do not make:

- deterministic current state and direct HDC `next_state -> state` carry;
- typed episodic transitions, actions, and outcomes;
- required-state contracts and fail-closed abstention;
- evidence identity and duplicate resistance;
- temporal validity, versions, invalidation, and supersession;
- configurable source trust and fact/belief separation;
- exact private, tenant, and global access boundaries;
- structured role/authority eligibility and uncertain profiles;
- exact full-vector semantic floors after ANN routing;
- auditable support, challenge, conflict, and abstention decisions;
- bounded memory frames for HDC and LLM assistants.

## Status

Version 0.7.0rc2 is a backward-compatible integration fix over the frozen rc1 baseline. It adds
versioned and scoped ToolAgentAdapter outcome forwarding after an executing benchmark showed that
unversioned global outcomes made HNG worse than agent alone. The frozen rc1 evidence remains
unchanged under breakthrough_eval/baseline_070.

The inherited 0.5.1 release remains preserved in the release artifacts and `research_eval/`. Its independent verdict was **C - Valuable specialized system**.

The 0.7.0rc1 architecture addresses the principal failures:

| Check | 0.5.1 baseline | 0.7.0rc1 |
|---|---:|---:|
| Original source tests | 30/30 | 30/30 unchanged |
| Full test suite | 30 | 99 passing |
| Canonical adversarial suite | 5/11 | 11/11 |
| Missing sequence | unsafe support | `INSUFFICIENT_STATE` |
| Duplicate amplification | unsafe support | one source event counts once |
| Stale version majority | unsafe support | current version challenges |
| Poisoned low-trust memory | unsafe support | `UNTRUSTED_EVIDENCE` |
| Uncertain inferred profile | unsafe support | `PROFILE_UNCERTAIN` |
| Default production ANN | HNGIX | FAISS binary, reference fallback |
| Windows restart/durability path | `fsync` failure | native tests and gauntlets pass |

The final 100K provider evaluation reached 100% source top-1 for Flat, IVF, and MultiHash; IVF remained the scale default because MultiHash degraded from 0.19 ms to 25.07 ms p50 on correlated leading-bit geometry. The synthetic end-to-end governed action harness reached 100% task success at 3.99 ms median. These are local Tier A results, not public end-to-end assistant claims.

## Install

```powershell
python -m pip install .\baseline_source\hng-frontier-0.5.1a1
```

FAISS is optional but recommended:

```powershell
python -m pip install ".\baseline_source\hng-frontier-0.5.1a1[faiss]"
```

Without FAISS, `HNGMemory` can use the exact reference backend. The legacy 0.5 `AssistantMemory` API remains available for migration and unchanged gauntlets.

## Minimal governed action evaluation

```python
from hngfrontier import (
    HNGMemory, SemanticState, SemanticValue,
    EvidenceProvenance, Decision,
)

with HNGMemory("./memory", semantic_backend="faiss-auto") as memory:
    current = SemanticState({
        "state": SemanticValue.hdc(state_hv),
        "goal": SemanticValue.hdc(goal_hv),
        "sequence": SemanticValue.hdc(sequence_hv),
    })

    memory.remember_transition(
        conversation_id="incident-42",
        state=current,
        action=SemanticValue.hdc(action_hv),
        next_state=SemanticValue.hdc(next_state_hv),
        outcome="system telemetry recorded a failure",
        outcome_score=-1.0,
        provenance=EvidenceProvenance(
            source_type="system_telemetry",
            source_id="event-8841",
            trust_score=1.0,
            verified=True,
        ),
        source_event_id="event-8841",
    )

    frame = memory.evaluate_action(
        current,
        SemanticValue.hdc(action_hv),
        conversation_id="incident-42",
    )
    assert frame.assessment.decision is Decision.CHALLENGE
    print(frame.to_prompt_context())
```

## Three integration paths

### Native HDC assistant

Use `HDCAssistantAdapter`. The interpreter receives exact prior semantic state, working constraints, open loops, and governed evidence. Immediate continuity never invokes ANN.

### LLM assistant

Use `LLMAssistantAdapter`. It renders a bounded `GovernedMemoryFrame` with current state, perspective, included evidence, excluded/superseded evidence, source provenance, decision, and reasons. It does not dump arbitrary top-k history.

### RAG or document system

Use `HybridDocumentRetriever` for BM25 plus an optional semantic provider, then `RAGEvidenceAdapter` to persist validated chunks as versioned evidence. HNG governs validity, contradiction, trust, provenance, and actor applicability; it does not pretend to replace BM25.

## Safety and rollout

The default rollout mode is shadow. `GovernedShadowEvaluator` supports:

```text
shadow -> context augmentation -> advisory challenge -> explicit hard gate
```

Hard gating requires an explicit opt-in. It is not enabled by constructing `HNGMemory`.

### Real HDC assistant evidence

`HDCShadowABRecorder` observes actions only after the unchanged assistant has selected them. It records recalled state/evidence, recommendations, governance decisions, provenance, actual behavior, and later outcome labels in an append-only trace; it has no allow/block control surface and isolates HNG or logging failures. `ShadowABEvaluator` reports labeled denominators, paired action-routing judgments, continuity, repeated-failure, perspective, staleness, abstention, contradiction, provenance, task-success, regret, latency, and context-cost metrics.

This is experiment infrastructure, not a claim that real-user improvement has already been measured. See the protocol before collecting production traces.

## Documentation

- [Next architecture](../../NEXT_ARCHITECTURE.md)
- [Evidence governance](../../EVIDENCE_GOVERNANCE.md)
- [Migration from 0.5.1](../../MIGRATION_FROM_051.md)
- [Migration from 0.7.0rc1](MIGRATION_070RC2.md)
- [Package changelog](CHANGELOG.md)
- [Adversarial report](../../ADVERSARIAL_REPORT.md)
- [Benchmarks](../../BENCHMARKS.md)
- [HDC assistant guide](../../ASSISTANT_HDC_GUIDE.md)
- [LLM assistant guide](../../ASSISTANT_LLM_GUIDE.md)
- [RAG integration](../../RAG_INTEGRATION.md)
- [Real HDC shadow A/B protocol](REAL_HDC_SHADOW_PROTOCOL.md)
- [Independent baseline verdict](../../research_eval/EXECUTIVE_VERDICT.md)
- [Final old-vs-new evaluation](../../next_eval/FINAL_EVALUATION.md)
- [Closure audit](../../CLOSURE_AUDIT.md)
- [Final architecture diagrams](../../ARCHITECTURE_FINAL.md)
- [Provider recommendations](../../RETRIEVAL_PROVIDERS_FINAL.md)
- [Final public benchmarks](../../PUBLIC_BENCHMARKS_FINAL.md)
- [Fault injection](../../FAULT_INJECTION.md)
- [Performance profile](../../PERFORMANCE_PROFILE.md)


## Source layout

The release-candidate package is under `baseline_source/hng-frontier-0.5.1a1/`; the directory name is retained only to preserve the frozen release extraction path. Package metadata and runtime version are 0.7.0rc2. Original source ZIP/wheel artifacts and the frozen rc1 baseline remain unchanged.

`research_eval/` contains the independent baseline. `next_eval/` contains new scripts and raw outputs. Large corpora, vector slabs, runtime databases, and vendored binary dependencies are intentionally excluded from Git, not deleted locally.

## Evidence discipline

Published prior-art numbers and systems not run locally remain literature evidence. The closure release executes a governed retrieval evaluation on the first 20 official QMSum test meetings (134 specific queries). BM25 remains stronger than the deterministic HDC hybrid. No LongMemEval-V2, PersonaMem-v2, GovReport, or common-LLM behavioral score is claimed; the release is publication-ready as a documented research system, not state of the art or a production hard gate.


## 0.7 closure evidence

The closure implementation adds production-provider experiments (FAISS MultiHash and USearch), revision-aware actor policy, complete deterministic working state, first-class belief and consolidation stores, pluggable provenance verification, coherent-generation retries, complete HDC/LLM/RAG/tool adapters, decision traces, component profiling, and process fault injection. See `CLOSURE_AUDIT.md` at the repository root for the requirement-by-requirement result and limitations.

The default remains `faiss-auto` (Flat below 50K, IVF at larger scale). MultiHash and USearch are explicit modes because the measured distributions do not justify automatic selection. Hard action blocking remains opt-in.
