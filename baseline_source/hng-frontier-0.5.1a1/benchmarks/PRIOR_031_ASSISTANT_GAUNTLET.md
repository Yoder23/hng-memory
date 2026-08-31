# HNG Frontier 0.3.1a1 — HDC Assistant Gauntlet

This benchmark is an adversarial **synthetic HDC assistant integration test**, not a claim about the user's production interpreter. Its purpose is to answer a narrower question: if the assistant emits useful native HDC states, can HNG preserve them turn-to-turn, recall them across chats, use historical outcomes to narrow a large HDC action library, survive contradictory/changed experience, and reconstruct state after restart?

## Workload

- 4,096-bit binary HDC heads.
- Six persisted semantic heads: `state`, `goal`, `entity`, `sequence`, `action`, `next_state`.
- 512 hard-neighbor context archetypes.
- 10,240 historical transition records.
- Every historical transition is in a separate `conversation_id`, producing 10,240 historical chats.
- Historical chats deliberately reuse `episode_id=1` to detect cross-chat episode contamination.
- 16,384-action HDC library: 1,024 action families × 16 deliberately close variants/family.
- Each context has five successful precedents for one context-specific action variant and negative outcomes for the other 15 variants.
- 256 new cross-chat recall/action-routing queries.
- 256 live chats with an ambiguous second turn, explicit correction, open-loop resolution and a new constraint.
- 96 temporal-shift cases where the previously successful action becomes obsolete after a `sequence`/version change.
- 160 action-gate cases per class: correct, known bad and unseen.
- Query-noise stress at 2%, 5%, 10% and 15% bit corruption.
- Separate 20,000-turn single-chat pressure/restart test.

The context prototypes share substantial structure, and action variants inside one family are intentionally close. This prevents the benchmark from reducing to independent random-vector lookup.

## Results

### Cross-chat episodic memory

| Metric | Result |
|---|---:|
| New-chat episode recall | **100%** |
| Cross-chat episode contamination | **0** |
| Median recall | **3.30 ms** |
| p95 | **4.56 ms** |
| Median exact full-HV fraction | **0.195%** |

The zero-contamination result is significant because all historical chats intentionally reuse the same local `episode_id=1`. During this gauntlet a bug was found and fixed: assistant episode reconstruction is now scoped by `(conversation_id, episode_id)`.

### Large HDC action library

The synthetic action intent identifies the correct **action family** but deliberately omits which of the 16 close variants historically works in this context.

| Router | Top-1 | Top-16 | Median |
|---|---:|---:|---:|
| Raw 16,384-action HDC scan | **7.42%** | **100%** | 5.08 ms |
| HNG historical action recommendation | **100%** | **100% top-5** | **3.09 ms** |

HNG returned a median eight historically grounded action candidates. The result should be interpreted as **memory disambiguating an intentionally ambiguous action family**, not as a claim that HNG always beats direct HDC action routing.

### Turn-to-turn continuity

The live second turn is intentionally equivalent to an elliptical phrase such as “what about that?” and is not independently informative.

| Method | Correct historical context |
|---|---:|
| Retrieval from ambiguous utterance alone | **0%** |
| HNG carried previous `next_state` as current HDC `state` | **100%** |

Working-state updates—goal, correction, open-loop resolution and constraint—were **100% correct** live.

The 256 live chats were intentionally allowed to accumulate as an unindexed tail beyond the normal rebuild heuristic. Correctness remained 100%, but median recall rose to **19.45 ms**. After rebuilding the index, the exact same live-chat recall was still **100%** with **3.03 ms median / 3.91 ms p95**. This demonstrates the intended behavior: stale-tail search preserves freshness/correctness, while rebuilds restore normal latency.

### Changed world / obsolete experience

For 96 contexts, a sequence/version shift changes which action works. Old evidence is more numerous than new evidence.

| Query | Result |
|---|---:|
| `state + goal + entity + sequence` | **100% chooses new action** |
| same context with `sequence` omitted | **100% prefers obsolete action** |
| new-era evidence still in stale tail | **100% chooses new action** |

This is a direct demonstration of why independently addressable semantic heads matter: if the assistant fails to represent the changed sequence/version, memory correctly cannot know that the old precedent is obsolete.

### External action evidence gate

A second issue was found during the gauntlet: close actions cannot safely share the same similarity floor as broad contextual state. HNG now supports an independent `action_floor`; the final test used context floor `0.80` and action-identity floor `0.97`.

| Proposed action | Expected | Result |
|---|---|---:|
| historically successful | `support` | **100%** |
| historically failed | `challenge` | **100%** |
| unrelated/unseen | `insufficient_evidence` | **100%** |

Median gate latency across all three classes was **4.51 ms**, p95 **11.71 ms**.

The automated suite separately verifies balanced positive/negative evidence returns `conflicted`.

### HDC query noise

Historical action selection remained 100% correct in the sampled workload through 15% query-side bit corruption with adaptive probing.

| Query bit noise | Accuracy | Median |
|---|---:|---:|
| 2% | **100%** | 4.12 ms |
| 5% | **100%** | 3.45 ms |
| 10% | **100%** | 3.23 ms |
| 15% | **100%** | 3.04 ms |

The unusually flat timing is workload/index specific. Real interpreter geometry is the required next validation.

### Restart and multi-chat persistence

After closing and reopening the memory engine:

- deterministic working state: **100%**;
- prior semantic heads available for turn continuation: **100%**;
- cross-chat historically grounded action selection: **100%**.

### 20,000-turn single chat

| Metric | Result |
|---|---:|
| Turns | 20,000 |
| Throughput | **3,348 turns/sec** |
| Median append | **0.174 ms** |
| Median append, final 1,000 turns | **0.174 ms** |
| p95 append | **0.268 ms** |
| Immediate context retained | **8 turns** |
| Cold deterministic replay after restart | **~515 ms** |
| Rebuilt working state correct | **yes** |

The flat final-1,000-turn latency shows normal live turn admission does not replay the whole conversation every turn. Full working-state replay is a cold-start/reconstruction operation.

## Bugs found because of the gauntlet

1. **Cross-chat episode scoping.** Local episode IDs could be merged across conversations. Episode reconstruction is now conversation-scoped.
2. **Action identity threshold.** Close action variants could leak evidence into one another when the context similarity floor was reused for action identity. `action_floor` is now independently configurable and exact-verified.

Both have regression tests.

## What this proves—and what it does not

This run gives strong synthetic evidence that the **assistant memory mechanics** work together:

- deterministic native-HDC continuity between turns;
- cross-chat associative recall;
- strict separation between chat-local working state and global historical memory;
- historically grounded narrowing of a large action library;
- explicit positive/negative/unknown evidence behavior;
- semantic disambiguation of obsolete experience through multiple heads;
- stale-index freshness;
- bounded recent context;
- restart reconstruction.

It does **not** prove that the production HDC interpreter emits semantic states with the same geometry. The final integration gate remains replaying real assistant traces in shadow mode. The important difference is that the architecture no longer needs a synthetic feature to be invented before that integration: the adapter accepts the assistant's native heads directly.
