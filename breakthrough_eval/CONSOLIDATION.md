# Memory consolidation

The production consolidator was exercised on 240 raw evidence records arranged as 12 groups, five
independent events per group, and four copied rows per event. One rare challenge event was placed in
the first group. The probe compares raw-only action evaluation with raw plus persisted consolidation
and audits the persisted patterns directly.

Consolidation produces 12 reversible patterns without deleting any raw record. It collapses copied
rows to independent source events, preserves the rare challenge and every source/provenance link,
and pattern invalidation leaves the raw evidence intact. Raw-only and raw-plus-consolidation action
evaluations are exactly identical.

The release has no patterns-only action-evaluation consumer: consolidated patterns are persisted but
are not indexed as governed `EvidenceRecordV2` inputs to `evaluate_action`. Therefore patterns-only
action quality is `NOT_EXECUTABLE`, and consolidation currently shows audit/size utility rather than
a downstream behavioral gain. Machine evidence is `consolidation/RESULTS.json`.

This is a synthetic production-component probe, not a public workload. If downstream consolidation
does not produce a measured benefit after a consumer is implemented, the simpler raw evidence path
should remain the default.
