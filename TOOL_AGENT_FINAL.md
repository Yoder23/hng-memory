# Tool-agent integration

`ToolAgentAdapter` evaluates a proposed `ToolAction` through `memory.evaluate_action()` before execution. The result includes the structured decision, support/challenge evidence, provenance, and reasons.

Deployment modes progress from shadow to context augmentation, advisory challenge, and explicitly configured hard gate. Construction does not enable hard blocking. Every execution log records the proposed action/arguments, HNG assessment, final decision, deployment mode, and observed result. A supplied outcome encoder feeds the actual tool result back into transition memory.

Use hard gates only for narrow, well-tested domains with authenticated outcomes and an operational override. The final recommendation for general autonomous agents is advisory mode, not HNG as the sole safety authority.

