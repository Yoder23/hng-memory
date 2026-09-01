# Changelog

## 0.7.0rc3

- Adds the installed `hng-eval` console entry point after a fresh-clone rc2 installation proved
  that the documented repository reproduction surface had no installed dispatcher.
- `hng-eval --repo-root PATH --dry-run core` validates the checkout and forwards arguments to
  `breakthrough_eval/scripts/reproduce.py` using the installed Python interpreter and no shell.
- Adds unit and isolated fresh-clone/install coverage for entry-point presence and dispatch.

This release changes no memory behavior, model, database schema, or evidence result. It is a
backward-compatible reproducibility and packaging correction over rc2.

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
