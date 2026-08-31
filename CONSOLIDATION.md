# Consolidation and forgetting

`PersistedConsolidator` groups records by evidence group and writes reversible pattern records containing the source experience IDs and distinct source-event groups. Consolidation never deletes or rewrites raw evidence, so every pattern remains auditable and duplicate copies do not acquire independent voting power.

`RetentionPolicy` makes forgetting eligibility explicit by age, kind, trust, and exemptions. Authoritative facts, constraints, system events, and configured safety-critical evidence are retention-exempt. `evaluate_retention()` returns policy decisions; it does not destructively erase evidence. Any physical archival/deletion mechanism must be implemented by a deployment with its own recovery and compliance policy.

