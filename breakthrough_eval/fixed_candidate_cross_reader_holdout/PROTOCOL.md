# Disjoint fixed-candidate cross-reader holdout protocol

## Purpose and boundary

This score-blind follow-up addresses the surviving weakness in the completed Qwen/Mistral
replication: both readers were evaluated on the same previously used 30 synthetic cases. The new
holdout uses the next 30 untouched generated cases while keeping the ten-family balance, exact
candidate identity, three memory systems, prompt, and exact-match scoring contract fixed.

This remains synthetic evidence. It is not a public benchmark, real assistant/HDC evaluation,
canonical unit, multiple-seed stochastic study, or contemporary-system comparison. Execution is
disabled until the complete harness, manifest, protocol, prepared file, tests, and exact model
digests are committed and pushed.

## Frozen design

- Protocol: `fixed_candidate_disjoint_cross_reader_holdout`.
- Seed: 20260831.
- Cases: variants 08, 09, and 10 from each of the ten frozen adversarial families; 30 total.
- Prior-window overlap: zero; variants 05, 06, and 07 are excluded by their frozen case IDs.
- Prepared SHA-256: `6af5cd25a5f08b1254cbc447c3a16783f5276116aea42a1adecab52121104094`.
- Systems: `ordinary_rag`, `strong_structured`, and `hng`.
- Qwen reader: `qwen3.8:27b-q4_K_M`, digest
  `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`.
- Mistral reader: `mistral-small3.1:24b-instruct-2503-q4_K_M`, digest
  `b9aaf0c2586a8ed8105feab808c0f034bd4d346203822f048e2366165a13f4ea`.
- Generation: temperature 0, seed 20260831, `num_predict=32`, `num_ctx=32768`.
- Expected calls: 30 cases x 3 systems x 2 readers = 180.

Within each reader, case order is frozen by the prepared rows. System execution order is assigned
by a reader-specific SHA-256 rank: all six system permutations occur exactly five times. Readers
run in fixed Qwen-then-Mistral blocks to avoid repeated 24B/27B model swaps. No direct reader-speed
claim is allowed because block order and warm-cache conditions are not counterbalanced.

Every system receives the same ordered candidate IDs for a case. Only its already-frozen memory
context differs. The expected decision is not included in the prompt. Candidate, context, prompt,
model, case-selection, order, and preregistration-commit hashes must pass before a result can be
complete.

## Preregistered comparisons

For each reader separately, the primary comparison is paired exact decision accuracy for
`hng - ordinary_rag`. Family-wise success requires both reader-specific tests to satisfy all of:

1. positive accuracy delta;
2. paired-bootstrap 95% lower bound above zero; and
3. two-sided exact McNemar `p < 0.025` (Bonferroni for two reader-family primary tests).

The complexity control is `hng - strong_structured` within each reader. HNG-specific superiority
requires the same three conditions in both readers at `p < 0.025`. If the primary family-wise rule
passes but this control does not, the result supports structured/governed context but fails HNG
attribution. Any tie, loss, interval containing zero, or threshold failure is preserved.

Reader-by-reader family breakdowns, tokens, and latency are diagnostic only. Cross-reader score
differences are descriptive because the models are not experimental arms with matched training or
capacity. No diagnostic result can replace the joint primary or complexity-control rule.

## Execution and failure policy

The run must use the exact clean pushed preregistration commit. Raw logs are append-only and
separated by reader. Failed attempts remain visible; recovery may append but not overwrite. No
interim scoring, stopping, case exclusion, threshold change, or arm-order change is permitted.

Completeness requires 180 unique reader/case/system completed keys, exact prepared-input and order
matches, one full model digest per reader, one preregistration commit, zero unexpected keys, and
the frozen outer prompt-template hash. Otherwise status remains partial. Results, including losses
and recovered failures, must be compiled and pushed separately from the preregistration commit.
