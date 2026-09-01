# Adversarial 250

Status: executed synthetic governance test. This is neither a public benchmark nor a real
assistant result.

## Frozen design

The generator creates 250 cases: ten adversarial families times 25 variants. Fifty cases are
labeled development and 200 holdout before inference. Every comparison receives the identical
ordered candidates and full metadata. Families are:

1. duplicated copies of one source event;
2. stale environment versions;
3. wrong tenant;
4. wrong role;
5. repeated untrusted model-inference poison;
6. superseded evidence;
7. genuinely balanced conflict;
8. irrelevant exact state;
9. sparse verified evidence against repeated rumors;
10. insufficient actor authority.

The frozen expected outputs are support, challenge, conflicted, or insufficient_evidence.
Raw per-case/system events are in fixed_candidate/raw/deterministic_events.jsonl. The generator
seed is 20260831.

## Result

| System | Correct | Accuracy | p50 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| Ordinary raw majority | 25/250 | 10.0% | 0.009 ms | 0.011 ms | 0.019 ms |
| StrongStructuredBaseline | 225/250 | 90.0% | 0.023 ms | 0.035 ms | 0.080 ms |
| HNG 0.7 production aggregator | 225/250 | 90.0% | 0.096 ms | 0.179 ms | 0.476 ms |

HNG versus raw majority has +80.0 percentage points, paired bootstrap 95% CI +74.8 to
+84.8 points, exact McNemar p=1.2446e-60. This is deliberately not presented as a compelling
baseline win: raw majority is a diagnostic corruption baseline, not strong memory.

HNG and StrongStructuredBaseline have zero discordant cases, delta 0, and McNemar p=1.0.
The simpler baseline is about 5.1 times faster at p95 in this small in-process measurement.

## Preserved loss

All 25 misses are duplicate_attack. HNG collapses six copied support rows to one independent
event, then compares that one support event with two independent challenge events. Its configured
conflict boundary treats a 1:2 quality ratio as materially balanced and returns conflicted; the
frozen expectation is challenge. StrongStructuredBaseline intentionally implements the same
boundary and has the same loss.

The expectation was not changed after observation. Any threshold change requires a broader
development distribution with varied evidence ratios, then evaluation on the untouched holdout.

## Calibration limitation

The current confidence proxy is absolute support/challenge margin. It assigns confidence zero to
both correct true-conflict and correct no-evidence cases, so it is not a calibrated probability of
correctness. The raw calibration bins are retained, but no calibration claim is made.
