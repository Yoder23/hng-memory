# Migrating from 0.7.0rc1 to 0.7.0rc2

No database migration is required and existing ToolAgentAdapter.execute calls continue to work.

Callers that operate across environment or policy versions should pass a TemporalValidity object.
Multi-user callers should also pass tenant_id, user_id, scope, role, and authority_level from
trusted server-side context. The adapter forwards these fields to the recorded outcome so later
action evaluation can enforce temporal, access, and actor applicability.

Example:

    adapter.execute(
        proposal,
        conversation_id="session-1",
        state=current_state,
        executor=execute_tool,
        outcome_semantics=encode_outcome,
        provenance=verified_source,
        validity=TemporalValidity(environment_version="v2", policy_version="policy-3"),
        tenant_id="tenant-a",
        user_id="user-7",
        scope="private",
        role="operator",
        authority_level=2,
    )

These values must come from authenticated application state. HNG does not authenticate callers,
and raw storage get/get_many primitives remain privileged and unscoped. ToolAgentAdapter remains
advisory unless hard-gate deployment is explicitly enabled elsewhere.
