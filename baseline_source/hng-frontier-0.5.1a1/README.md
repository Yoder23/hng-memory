+# HNG Frontier Memory

HNG is an evidence-governed memory and control layer for intelligent assistants. It maintains durable working state and episodic experience, evaluates whether retrieved memories are current, independent, trustworthy, and actor-appropriate, and exposes structured evidence to HDC-native or LLM-based reasoning systems.

Version: **0.6.0rc1**

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

The inherited 0.5.1 release remains preserved in the release artifacts and `research_eval/`. Its independent verdict was **C - Valuable specialized system**.

The 0.6.0rc1 architecture addresses the principal failures:

| Check | 0.5.1 baseline | 0.6.0rc1 |
|---|---:|---:|
| Original source tests | 30/30 | 30/30 unchanged |
| Full test suite | 30 | 72 passing |
| Canonical adversarial suite | 5/11 | 11/11 |
| Missing sequence | unsafe support | `INSUFFICIENT_STATE` |
| Duplicate amplification | unsafe support | one source event counts once |
| Stale version majority | unsafe support | current version challenges |
| Poisoned low-trust memory | unsafe support | `UNTRUSTED_EVIDENCE` |
| Uncertain inferred profile | unsafe support | `PROFILE_UNCERTAIN` |
| Default production ANN | HNGIX | FAISS binary, reference fallback |
| Windows restart/durability path | `fsync` failure | native tests and gauntlets pass |

The 100K FAISS provider benchmark reached 100% exact top-1 agreement at 0.679 ms median. The synthetic end-to-end governed action harness reached 100% task success at 3.99 ms median. These are local Tier A results, not public end-to-end assistant claims.

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

## Documentation

- [Next architecture](../../NEXT_ARCHITECTURE.md)
- [Evidence governance](../../EVIDENCE_GOVERNANCE.md)
- [Migration from 0.5.1](../../MIGRATION_FROM_051.md)
- [Adversarial report](../../ADVERSARIAL_REPORT.md)
- [Benchmarks](../../BENCHMARKS.md)
- [HDC assistant guide](../../ASSISTANT_HDC_GUIDE.md)
- [LLM assistant guide](../../ASSISTANT_LLM_GUIDE.md)
- [RAG integration](../../RAG_INTEGRATION.md)
- [Independent baseline verdict](../../research_eval/EXECUTIVE_VERDICT.md)
- [Final old-vs-new evaluation](../../next_eval/FINAL_EVALUATION.md)

## Source layout

The release-candidate package is under `baseline_source/hng-frontier-0.5.1a1/`; the directory name is retained only to preserve the frozen release extraction path. Package metadata and runtime version are 0.6.0rc1. Original source ZIP/wheel artifacts remain unchanged at repository root.

`research_eval/` contains the independent baseline. `next_eval/` contains new scripts and raw outputs. Large corpora, vector slabs, runtime databases, and vendored binary dependencies are intentionally excluded from Git, not deleted locally.

## Evidence discipline

Published prior-art numbers and systems not run locally remain literature evidence. The new architecture has not yet established state-of-the-art performance on LongMemEval-V2, PersonaMem-v2, full QMSum, GovReport, or a common-LLM behavioral benchmark. Those are release gates for a research-paper claim, not claims implied by this RC.
