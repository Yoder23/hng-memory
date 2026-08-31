# Perspective-conditioned memory

HNG Frontier 0.5 adds an explicit **actor perspective** to assistant memory. The motivation is simple: the same semantic problem can require different evidence, abstraction, and actions depending on who is asking.

## Three different jobs

HNG does not collapse personalization into one similarity vector.

1. **Access identity is a hard boundary.** Memories are `private`, `tenant`, or `global`. Private/tenant eligibility is evaluated from exact in-memory string codes, never semantic similarity or probabilistic hashes.
2. **Role / authority / abstraction are eligibility.** A semantically excellent executive precedent can be rejected for an IC before exact semantic ranking. Unscoped general knowledge may be allowed explicitly.
3. **Perspective / expertise / priority are optional native HDC heads.** They participate in the same approximate-route -> compact-sketch -> exact-full-HV pipeline as state, goal, entity, and sequence.

This separation prevents a strong topical match from overpowering an invalid actor context.

## Durable profile versus active perspective

`PerspectiveProfile` is the durable, user-controlled profile:

- `user_id`, `tenant_id`;
- canonical role;
- authority level (0-5);
- abstraction level (0-4);
- domain expertise scores;
- responsibilities;
- priorities;
- application-defined extra fields;
- revision.

`PerspectiveOverride` is conversation-local. The same person can normally be an IC but explicitly enter an acting-manager conversation without rewriting the durable profile.

The resolved `EffectivePerspective` is passed to `AssistantSemanticAdapter` on every turn. HNG does **not** infer role, expertise, or priorities from text; the assistant/interpreter owns that inference.

## Memory snapshots

Every committed transition records the effective actor metadata and profile revision that existed when the experience occurred. Updating a user profile does not rewrite history.

## Retrieval policy

Assistant-facing context/action APIs apply `PerspectivePolicy` by default when a conversation has an active perspective. Callers can disable or customize it for research/debugging.

The default policy:

- exposes global memory;
- exposes tenant memory only to the same tenant;
- exposes private memory only to the same user;
- requires role compatibility for scoped actor memories;
- prevents recommendations above the user's authority level;
- keeps abstraction within a small configurable tolerance;
- allows explicitly unscoped general memories.

## Model-agnostic integration

A native HDC assistant can encode `perspective`, `expertise`, and `priority` heads directly. An LLM harness can use exactly the same profile as an external eligibility/evidence layer rather than relying only on a persona paragraph inside the prompt.

The intended concept is **perspective-conditioned assistance**, not a claim that the stored profile is a literal psychological "digital twin" of a person. Profiles should be inspectable, editable, provenance-aware, and governed by the platform's privacy/access rules.
