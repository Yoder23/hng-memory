# Assistant-memory design

## Research target

HNG Frontier 0.5 targets a memory hierarchy for HDC-native assistants, not a replacement context window and not a text RAG database.

The key invariant is:

> Known current state is carried deterministically. Approximate semantic retrieval is only used to navigate older experience, and returned semantic evidence is verified against full stored HDC states.

## Transition as the unit of experience

A transition can carry these independently addressable semantic heads:

```text
state_t
goal_t
entity_t
sequence_t
action_t
outcome_t
next_state_t
```

The authoritative experience record also stores the observation/source, human-readable action/outcome labels, outcome score, episode/conversation identity, metadata, and a replayable `WorkingUpdate`.

A later query can retrieve historical transitions by semantic conjunction and directly expose the historical action/outcome. `next_state` allows future work on transition prediction and state-change similarity without reconstructing it from text.

## Working memory is a materialized view, not a second truth store

Each committed transition may carry deterministic operations:

- set/clear current goal;
- add fact/open loop/commitment/constraint/entity/topic;
- resolve an item;
- supersede an item.

The live process incrementally advances an in-memory materialized view. After restart, the same state is reconstructed by replaying committed transition deltas from SQLite.

This prevents ANN from being responsible for pronouns, "that", "same issue", current goals, or explicit corrections.

## HDC carry-forward

The integration context exposes the last transition's HDC state directly. When `next_state` exists it becomes the next turn's current `state`; goal/entity/sequence heads are also available by exact slot lookup.

This is deliberately separate from long-term recall.

## MemoryFrame v2

The stable assistant-facing contract contains:

- deterministic working state;
- exact immediate context;
- recalled historical episodes;
- support/contradiction evidence;
- prior actions/outcomes;
- open loops, commitments, constraints, corrections;
- provenance with slot, episode, per-head exact similarities;
- decision/confidence and retrieval diagnostics.

An HDC assistant can consume `MemoryFrame.as_dict()` or the typed object. An LLM can optionally consume a bounded `to_context_text()` rendering.

## Action gate

A proposed action can become a required semantic head, with per-head full-HV similarity floors. Historical outcome scores are aggregated into an external evidence decision:

```text
support
challenge
conflicted
insufficient_evidence
```

`insufficient_evidence` is distinct from `support`.

The gate is evidence retrieval, not a proof of correctness or safety. Bad/poisoned/stale memory can still produce bad evidence and must be tested explicitly.

## Crash boundary

Vector rows are written before the SQLite memory commit. SQLite owns the committed count.

- crash before SQLite commit: prewritten vector row is outside the committed prefix and invisible;
- crash after SQLite commit but before the working-state cache advances: reopening replays the committed transition delta and reconstructs state.

This removes a separate working-state commit protocol.


## Perspective as a first-class coordinate

0.5 adds an explicit actor model because semantic intent alone does not determine the appropriate answer or action. An identical database-performance state can imply implementation work for an IC, team prioritization for a manager, or portfolio decisions for an executive.

HNG separates this into:

```text
access identity     -> hard private / tenant / global boundary
actor eligibility  -> role / authority / abstraction
semantic perspective -> perspective / expertise / priority HDC heads
```

Access and authority are never overridden by a high semantic score. The effective user perspective is supplied to the assistant's HDC adapter every turn and snapshot onto each historical experience by profile revision.

A durable profile and a conversation-local active perspective are separate. This lets one person switch into an acting role without rewriting their long-term profile or historical evidence.
