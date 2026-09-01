# Changelog

## 0.7.0rc2

- ToolAgentAdapter.execute accepts optional temporal validity, tenant, user, scope, role,
  authority, abstraction, and profile-revision context for recorded outcomes.
- Outcome context is forwarded unchanged to HNGMemory.remember_transition.
- A regression proves a private v1 tool success is excluded from a v2 decision and retains its
  access and perspective fields.
- The executing 108-episode evaluation and complete pre-change loss are preserved under
  breakthrough_eval/tool_agent.

This release changes no database schema. Existing ToolAgentAdapter callers remain source
compatible because every added parameter is optional.

## 0.7.0rc1

The frozen evidence-governed memory release used as the Breakthrough Program baseline. Its package
and benchmark artifacts remain immutable under breakthrough_eval/baseline_070.
