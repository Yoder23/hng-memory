# Assistant Integration Ready gate — 0.5.0a1

## Green in 0.3.1a1

- [x] First-class transition records with state/goal/action/outcome/next-state heads.
- [x] Deterministic working-state continuity; ANN is not used for the immediately previous turn.
- [x] Previous `next_state` HDC vector is directly carried forward as current `state`.
- [x] Exact recent context window independent of semantic search.
- [x] Persistent open loops, commitments, constraints, facts, entities and topics.
- [x] Explicit supersession/correction history.
- [x] Multi-head historical recall with full-HV verification.
- [x] Transition/action-outcome recall.
- [x] External action evidence decisions: support/challenge/conflicted/insufficient_evidence.
- [x] Fail-closed no-evidence behavior.
- [x] Stable `MemoryFrame` schema v2 with effective user perspective, structured HDC form and LLM-rendered form.
- [x] Adapter boundary that receives prior HDC heads plus deterministic working state.
- [x] Shadow JSONL logging and labeled summary.
- [x] Behavioral replay evaluator API.
- [x] Restart reconstruction.
- [x] Crash before commit leaves no visible transition.
- [x] Crash after commit but before cache advance reconstructs working state on reopen.
- [x] Fresh committed transitions remain searchable before ANN rebuild.
- [x] Source-tree tests and installed-wheel smoke test.
- [x] Cross-chat episode reconstruction is scoped by `(conversation_id, episode_id)`; local episode IDs cannot merge chats.
- [x] Memory-guided large-action-library candidate narrowing (`recommend_actions`).
- [x] Separate exact action-identity threshold (`action_floor`) for close HDC action variants.
- [x] 10,240-chat / 16,384-action synthetic assistant gauntlet.
- [x] 20,000-turn single-chat pressure/restart test.

## Must be green on the real assistant before memory affects live behavior

- [ ] Replay actual conversations using the production HDC interpreter heads.
- [ ] Establish real episode-recall thresholds.
- [ ] Measure correction/open-loop continuity on real turns.
- [ ] Label proposed-action cases and measure false challenge / unsupported support.
- [ ] Run HNG in shadow mode under production-like traffic.
- [ ] Establish p50/p95/p99 memory latency on the deployment hardware.
- [ ] Test stale, contradictory, poisoned and missing evidence from real semantic distributions.

Until these are measured, 0.3.1a1 should augment nothing in the live assistant. It is designed to be wired in **shadow mode first**.

## Perspective-conditioned readiness

- [x] Durable `PerspectiveProfile` with revision history.
- [x] Conversation-local `PerspectiveOverride` for acting-role changes without rewriting the user profile.
- [x] Exact private / tenant / global memory access boundaries.
- [x] Role, authority and abstraction eligibility before semantic ranking.
- [x] Optional native HDC `perspective`, `expertise` and `priority` heads.
- [x] Every experience snapshots the effective actor and profile revision that produced it.
- [x] Effective perspective is available directly to `AssistantSemanticAdapter`.
- [x] 8,192-action / eight-persona synthetic perspective gauntlet: 100% conditioned action selection, 0% role violations.
- [x] Same durable user can switch acting perspective per conversation and route correctly.
- [x] Private memory does not cross users; tenant memory does not cross tenants.
- [ ] Run PersonaMem/PersonaMem-v2 or an equivalent real personalization benchmark with the production HDC interpreter.
- [ ] Measure real perspective-violation rate, profile-update adaptation, and false personalization on production traces.
