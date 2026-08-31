# HNG Frontier 0.5.0a1 release notes

## Perspective-conditioned memory

0.5 adds an explicit actor/perspective plane to the assistant architecture. It is aimed at cases where semantic intent is identical but the appropriate insight/action differs by user role, authority, expertise, abstraction level, responsibility, or priority.

### Added

- `PerspectiveProfile`, `PerspectiveOverride`, `EffectivePerspective`, `PerspectivePolicy`, `PerspectiveStore`.
- Durable user profiles and conversation-local acting-role overrides.
- `AssistantContext.perspective` and `MemoryFrame` schema v2 perspective output.
- Optional default HDC heads: `perspective`, `expertise`, `priority`.
- Per-experience perspective snapshots and profile revision.
- Exact `private` / `tenant` / `global` memory scope.
- Non-semantic role/authority/abstraction filtering before semantic ranking.
- Perspective-conditioned context, transition recall, action recommendation, and action gate wrappers.
- `examples/perspective_digital_twin_demo.py`.
- Perspective gauntlet and 7 new perspective/security tests.

### Validation

- 30/30 automated tests.
- 8,192-action synthetic perspective gauntlet: raw HDC 6.25% exact action top-1; semantic-only HNG 12.5%; role/authority-only 50% on a 128-query sample; full perspective-conditioned HNG 100% over 512 queries.
- Semantics-only role violation rate 75%; full perspective policy 0%.
- 64/64 acting-role switches correct.
- Private-memory leakage 0 in adversarial cross-user checks.
- Profile priority update changed subsequent routing without rewriting historical memories.

These are synthetic results. The next public gate is real-interpreter personalization on PersonaMem/PersonaMem-v2/LaMP-style tasks.

## 0.5.1a1 regression hardening

- Re-ran the original 0.3.1 assistant gauntlet unchanged against the perspective-enabled engine; all original correctness gates remain 100%.
- Added a cached effective-perspective path so conversations without active profiles do not issue SQLite perspective reads per turn.
- Changed actor/scope relational indexes to sparse partial indexes so global/unscoped writes do not maintain irrelevant perspective index entries.
- Added direct writer-to-eligibility-cache admission, removing the post-commit SQLite row reread.
- The 20,000-turn regression test now slightly exceeds 0.3.1 write throughput on this machine while retaining the 0.5 perspective/document capabilities.
- Added local exact BinaryFlat/composite/weighted/conjunctive baselines. HNG does not beat trivial exact composite retrieval on every fixed-intent query; it does match exhaustive conjunctive evidence correctness at substantially lower latency in the action-gate workload.
