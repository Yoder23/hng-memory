# Evidence governance

## Decision contract

The stable `Decision` enum contains:

- `SUPPORT`
- `CHALLENGE`
- `CONFLICTED`
- `INSUFFICIENT_EVIDENCE`
- `INSUFFICIENT_STATE`
- `SUPERSEDED`
- `UNTRUSTED_EVIDENCE`
- `PROFILE_UNCERTAIN`

Every decision returns an `EvidenceAssessment` with separate support/challenge/conflict scores, independent counts, quality, included evidence, excluded evidence and reason, missing fields, latency, and human-readable reasons.

## Applicability sequence

Evidence is not scored until it passes:

1. exact access visibility;
2. required query-state validation;
3. environment and policy version prefilter;
4. invalidation and supersession;
5. validity interval;
6. structured actor role/authority eligibility;
7. exact semantic floors against original vectors/values;
8. trust policy;
9. independence grouping.

ANN rank never bypasses these checks.

## Quality calculation

For an eligible independent event, the auditable quality contribution is:

```text
min(record trust, configured source weight)
* configured evidence-type weight
* verification factor
* record confidence
* mean exact semantic match
* bounded outcome strength
```

The individual terms are preserved in the record or derivable from the assessment. They are not hidden behind a learned opaque score. The default policy is conservative and configurable.

## Independence

Rows sharing `source_event_id` contribute at most once. The highest-quality copy is retained for assessment and remaining copies are listed as `duplicate_event`. This defeats re-ingestion, copied documents, and malicious duplicate amplification.

Distinct events can contribute independently even when they share an evidence group. `EvidenceConsolidator` uses the same rule and retains links to every source row. It never deletes raw experience.

## Temporal truth

Evidence may specify `valid_from`, `valid_until`, `environment_version`, `policy_version`, `invalidated_at`, `supersedes`, and `superseded_by`.

Version constraints are structured prefilters before ANN. Explicit supersession overrides raw counts: one new rule may invalidate 100 old successes. Facts with no version or expiry can remain valid indefinitely.

## Trust and belief/fact separation

Evidence categories have different default authority. System events and verified outcomes can drive action evidence. Claims, beliefs, and hypotheses are weaker. Unverified model inference and text cannot become authoritative merely through repetition.

`EvidenceProvenance` records source type, source ID, trust, verification, observed time, actor, and optional signature. Trust policy is application-configurable; the package does not claim a universal hierarchy.

## Profile uncertainty

Known identity/access and role/authority are structured. Each `PerspectiveField` includes confidence, source, user confirmation, revision, and update time. Critical plans require sufficiently confident authoritative role and authority fields when a profile is active. Inferred role at 0.42 confidence yields `PROFILE_UNCERTAIN`, not a hard gate based on a guessed identity.

## Example explanation

```json
{
  "decision": "challenge",
  "reasons": [
    "3 independent current challenge groups outweigh support",
    "prefiltered 100 records before ANN: environment_version_mismatch"
  ],
  "independent_support_count": 0,
  "independent_challenge_count": 3
}
```

The full frame also exposes per-head exact scores, included provenance, and exclusion reasons.

## Policy cautions

- Do not mark model-generated text as verified telemetry.
- Do not reuse `source_event_id` for genuinely independent observations.
- Do not generate a new source-event ID merely to evade deduplication.
- Do not enable hard gates before calibrating trust and thresholds on target adversaries.
- Preserve evidence even after consolidation; invalidation and supersession should be reversible/auditable.

