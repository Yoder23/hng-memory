# Assistant integration plan

## Phase 1 — shadow only

1. Keep the existing assistant behavior unchanged.
2. At each turn, have the real HDC interpreter emit the semantic heads it already owns.
3. Call `record_transition()` after the turn outcome is known.
4. Before the next turn, call `integration_context()` and let the interpreter consume the prior HDC heads plus deterministic working state.
5. Generate a `MemoryFrame`, but log it instead of injecting it into behavior.
6. Use `ShadowEvaluator` with human/automatic labels where available.

Recommended initial acceptance metrics:

- immediate-turn continuity: effectively 100%;
- corrections/current-fact accuracy: 100% on deterministic updates;
- open-loop/commitment persistence after restart: 100%;
- historical episode recall: set a threshold from real replay data;
- unsupported `support` decisions: target zero in the labeled action-control set;
- false `challenge` rate: explicitly measured and bounded;
- p95 memory latency within the assistant's turn SLO.

## Phase 2 — context augmentation

Allow `MemoryFrame` to influence reasoning/context, but do not let the action gate block tools/actions. Compare task success and contradiction rates to the pre-HNG assistant.

## Phase 3 — advisory action challenge

Surface `challenge`/`conflicted` evidence to the assistant and require re-reasoning, but do not hard block.

## Phase 4 — hard gate only for domains that pass stricter validation

Hard blocking should require calibrated thresholds, adversarial/poisoning tests, audit-quality provenance, and a demonstrated low false-challenge rate.

## Real HDC interpreter contract

HNG does not prescribe how semantic heads are constructed. The assistant should pass native binary/bipolar vectors to `record_transition()` and return native heads from `AssistantSemanticAdapter.encode()`.

The adapter receives:

- `context.working_state` — current deterministic goal/items/corrections;
- `context.semantic_heads` — prior committed HDC state/goal/entity/sequence;
- `context.recent_records` — exact recent transitions.

This is the point where elliptical user language should be resolved by your HDC semantic interpreter before long-term recall.

## Large action libraries

Do not make the memory harness evaluate every possible action one-by-one. Use `recommend_actions()` to narrow a large library from historical context/outcome evidence, then map the returned labels/IDs back to the assistant's native HDC action vectors. For final proposed-action evidence, use `evaluate_action()`.

When action vectors are deliberately close, set an `action_floor` stricter than the broad context `semantic_floor`. The 0.3.1 synthetic gauntlet used a context floor of `0.80` and action floor of `0.97`. Calibrate both on real interpreter data.

## Multi-chat episode IDs

Episode IDs may be local to each chat. Assistant-facing reconstruction is scoped by `(conversation_id, episode_id)`, so two chats can both use `episode_id=1` without their episode records being merged. Cross-chat associative recall remains global unless a `MemoryFilter` restricts it.


## Perspective-conditioned assistant integration (0.5)

Register an explicit durable profile once, then activate it for each conversation. The profile is not inferred by HNG.

```python
from hngfrontier import PerspectiveProfile, PerspectiveOverride

memory.set_user_profile(PerspectiveProfile(
    user_id="alex", tenant_id="acme", role="individual-contributor",
    authority_level=1, abstraction_level=1,
    expertise={"backend": .9},
    responsibilities=("own service implementation",),
    priorities=("reliability", "delivery"),
))
memory.activate_perspective(conversation_id, "alex")
```

The real HDC adapter receives `context.perspective` together with prior semantic heads and deterministic working state. It may encode native `perspective`, `expertise`, and `priority` heads. HNG's default assistant-facing retrieval also applies exact actor eligibility before ranking.

For a temporary acting role:

```python
memory.activate_perspective(
    conversation_id, "alex",
    PerspectiveOverride(role="engineering-manager", authority_level=3, abstraction_level=2,
                        responsibilities=("acting team lead",), priorities=("team delivery",)),
)
```

Do not use semantic vectors as access control. `private`, `tenant`, and `global` memory scope is evaluated separately from HDC similarity. Profiles should be inspectable and user-editable; hidden personality inference is outside the HNG memory layer.
