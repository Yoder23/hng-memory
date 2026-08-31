# Migrating from HNG 0.5.1

## Compatibility promise

The 0.5 `AssistantMemory`, `MultiHeadMemory`, `MemoryHarness`, document API, working-state classes, and perspective API remain importable. The original 30 tests and assistant/perspective/turn-stream gauntlets run unchanged through the compatibility layer.

0.5 artifacts are not silently rewritten into governed evidence. Migration is explicit because old records lack stable source-event identity, trust, validity, and profile-confidence metadata.

## API mapping

| 0.5 | 0.6 control-plane equivalent |
|---|---|
| `AssistantMemory.record_transition` | `HNGMemory.remember_transition` |
| `prepare_context` | `context` or `recall` |
| `evaluate_action` | `evaluate_action` returning `GovernedMemoryFrame` |
| `PerspectiveProfile` | `GovernedProfile` + `PerspectiveField` |
| `MemoryFilter` access fields | exact store visibility derived from effective profile |
| `MultiHeadMemory.rebuild_index` | `rebuild_retrieval` |
| HNGIX options | `semantic_backend="faiss-auto"` or explicit provider mode |
| arbitrary string decision | `Decision` enum |

## Required migration metadata

For each imported experience choose, rather than fabricate:

- a stable `experience_id`;
- the underlying `source_event_id`;
- an `evidence_group_id`;
- evidence kind;
- source type, source ID, trust, and verification;
- validity/version fields;
- scope, tenant, and user;
- profile revision where actor-conditioned.

Records without defensible source identity should be imported as unverified claims, not observations or facts.

## Example

```python
from hngfrontier import HNGMemory, EvidenceProvenance, EvidenceKind

memory.ingest_evidence(
    experience_id=f"legacy-slot:{record.slot}",
    source_event_id=record.extra.get("source_event_id", f"unknown:{record.slot}"),
    evidence_group_id=f"legacy-episode:{record.episode_id}",
    content=record.source,
    semantics=converted_semantic_state,
    kind=EvidenceKind.CLAIM,
    outcome_score=record.outcome_score,
    provenance=EvidenceProvenance(
        source_type="unverified_text",
        source_id=f"hng051:{record.slot}",
        trust_score=0.25,
        verified=False,
    ),
)
```

Only elevate records after external validation.

## Behavioral migration

Run 0.6 first in shadow mode. Compare the legacy action decision, governed decision, actual assistant action, and observed outcome. Move to context augmentation, then advisory challenge. Hard gating is a separate explicit deployment decision.

## Index migration

HNGIX files are derived state and need not be converted. Rebuild FAISS from the original full-resolution HDC values. Keep raw vectors because exact verification remains mandatory.

## Known non-migrations

The custom 0.5 document hierarchy is retained for compatibility but is not the production default. Use `HybridDocumentRetriever` and import validated chunks with `RAGEvidenceAdapter`.
