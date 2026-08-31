# Research status — 0.5.0a1

HNG Frontier is a research architecture for persistent native semantic state. 0.5 adds perspective-conditioned memory to the existing transition, evidence-control, multi-chat, and document-memory work.

## What is demonstrated synthetically

- deterministic HDC state continuity across turns;
- associative recall across chats;
- state/action/outcome evidence gates;
- large action-library narrowing from historical outcomes;
- changed-world discrimination through independent semantic heads;
- hierarchical HDC document state and provenance;
- actor-conditioned memory using role, authority, expertise, abstraction, and priorities;
- exact private/tenant/global memory isolation;
- durable profile revisions and conversation-local acting-role overrides.

The 0.5 perspective gauntlet uses 8,192 actions and identical semantic problems across eight personas. Full perspective-conditioned HNG reaches 100% exact action selection with 0% role violations, while semantics-only memory reaches 12.5% and violates role perspective 75% of the time in that synthetic workload.

## Closest public personalization work

Personalization itself is an active research area and is not novel to HNG. LaMP established retrieval-augmented profile personalization. PersonaMem evaluates dynamic user profiling over long multi-session histories, and PersonaMem-v2 explicitly studies agentic memory for implicit personalization. PersonaAgent combines personalized memory and personalized actions.

The HNG-specific research hypothesis is narrower: **can native HDC semantic state plus non-semantic actor eligibility create a persistent evidence/control substrate where identical semantic queries are interpreted differently according to a user's explicit role, authority, skills, priorities, and active perspective—without relying on a generative model to reconstruct the user profile on every turn?**

## Required public gates

1. Run the assistant with real HDC interpreter traces.
2. Evaluate personalized response/action selection on PersonaMem/PersonaMem-v2 and LaMP-style tasks.
3. Compare profile-in-prompt, retrieval-augmented profile memory, soft HDC perspective, and HNG hard+semantic perspective conditioning.
4. Report perspective violation rate, cross-user leakage, profile-update adaptation, action success/regret, and ordinary task metrics.
5. Keep document/public long-memory benchmarks from 0.4 in the same publication program.

Synthetic results justify integration and publication as a research preview. They do not justify claiming solved personalization.
