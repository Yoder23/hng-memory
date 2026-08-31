# Native HDC assistant guide

## Principle

The interpreter owns semantic meaning. HNG stores and governs its named HDC heads. Immediate continuity is direct:

```text
next_state[t] -> state[t+1]
```

Do not call ANN to rediscover the previous committed state.

## Typed values

```python
from hngfrontier import SemanticState, SemanticValue

state = SemanticState({
    "state": SemanticValue.hdc(state_hv),
    "goal": SemanticValue.hdc(goal_hv),
    "sequence": SemanticValue.hdc(sequence_hv),
})
```

HDC values are packed and persisted exactly. ANN uses the packed bits directly; final floors compare the originals.

## Interpreter adapter

```python
from hngfrontier import HNGMemory, HDCAssistantAdapter, SemanticState

def encode(turn, *, prior_state, working_context):
    # Your native HDC interpreter resolves ellipsis using prior_state directly.
    return SemanticState(interpreter.encode(
        turn,
        prior=prior_state.fields,
        open_loops=working_context["open_loops"],
        constraints=working_context["constraints"],
    ))

memory = HNGMemory("./memory", semantic_backend="faiss-auto")
adapter = HDCAssistantAdapter(memory, encode)
query_state = adapter.encode_turn("What about that?", conversation_id="chat-7")
```

## Record transitions

Use stable source-event IDs from the actual observation/telemetry system. Do not generate a new event ID for copies.

```python
memory.remember_transition(
    conversation_id="chat-7",
    state=query_state,
    action=SemanticValue.hdc(action_hv),
    next_state=SemanticValue.hdc(next_state_hv),
    outcome="allocator pressure recovered",
    outcome_score=1.0,
    provenance=telemetry_provenance,
    source_event_id="telemetry:incident-443:step-9",
)
```

The next state is written to deterministic working state immediately.

## Action evaluation

The default action plan requires state, goal, sequence, and action. Missing sequence returns `INSUFFICIENT_STATE`. Exact action similarity is centrally floored at 0.97 even if a caller submits a lower value.

Consume `frame.assessment.decision` and `frame.assessment.reasons`; do not derive a second decision from ANN score.

## Zero-service operation

Use `semantic_backend="reference-hng"` for no FAISS dependency. It is exact and dependency-free but not the high-scale production default. No embedding service or LLM is required in either mode.

