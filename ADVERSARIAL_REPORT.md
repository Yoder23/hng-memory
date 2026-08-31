# Adversarial report: HNG 0.6.0rc1

## Result

The canonical independent suite improves from **5/11 on 0.5.1** to **11/11 on 0.6.0rc1**. Expected outcomes were not weakened.

| Scenario | 0.5.1 | 0.6.0rc1 | Mechanism |
|---|---|---|---|
| Balanced positive/negative | conflicted | conflicted | independent two-sided aggregation |
| 100 stale successes, 3 current failures | support | challenge | environment-version prefilter |
| Poisoned experiences | support | untrusted evidence | configurable provenance trust |
| Duplicate amplification | support | insufficient evidence | source-event deduplication |
| Missing sequence | support | insufficient state | required-state contract |
| Changed sequence supplied | insufficient | insufficient | exact sequence floor preserved |
| Unseen action | insufficient | insufficient | fail-closed no-evidence path |
| Close wrong action | insufficient | insufficient | central 0.97 action floor |
| Caller requests loose action floor | support | insufficient | caller cannot weaken central safety floor |
| Incorrect inferred profile | support | profile uncertain | confidence/source-aware profile |
| Authority-inappropriate precedent | blocked | blocked | exact structured authority eligibility |

Raw result: `next_eval/raw/ADVERSARIAL_11.json`.

## Expanded suite

The package now has 72 passing tests: 30 inherited and 42 new governed-memory cases. The new cases cover more than 30 distinct adversarial/integration conditions, including:

- hypotheses, beliefs, and claims repeated by a model;
- poisoned documents;
- missing state, goal, and sequence independently;
- changed sequence and wrong contexts;
- unseen and 5%-different actions;
- unsafe caller threshold configuration;
- low-confidence inferred profiles;
- role changes, authority changes, and conversation overrides;
- private collision, tenant collision, and global sharing;
- explicit supersession, invalidation, expiry, future validity, environment mismatch, and policy mismatch;
- many low-trust sources against one verified failure;
- genuinely independent moderate-trust observations;
- low-confidence current evidence;
- indefinitely valid authoritative evidence;
- persisted deterministic state and restart;
- RAG provenance;
- bounded explanations;
- shadow-mode non-blocking behavior;
- reversible deduplicated consolidation;
- exact metadata document filtering;
- concurrent readers/writers;
- duplicate insert rollback;
- interrupted index rebuild and recovery;
- FAISS or explicit reference fallback.

## Interpretation

Passing is architectural, not a universal security proof. Attackers who can falsely mark evidence as verified telemetry or mint fake authoritative source identities can bypass policy. Production deployments still need authentication, signatures, source authorization, audit retention, rate limits, and held-out red-team data.

Hard gates remain disabled by default.

