# Real HDC Assistant Shadow A/B Protocol

## Claim boundary

HNG Frontier 0.7 has architectural, adversarial, public-benchmark, and synthetic-assistant evidence. It does **not** yet have evidence that switching on governed memory improves the real HDC assistant. This protocol collects that missing evidence. Example traces and tests are instrumentation validation, not real-user results.

The first deployment is observation only:

```text
real user turn
   |
   +--> current assistant (unchanged) --> selected action/response --> outcome
   |
   `--> HNG shadow --> recalled state/evidence/recommendation/decision --^
```

The production assistant selects its action before `HDCShadowABRecorder.capture` is called. The recorder has no allow/block return value, catches HNG failures, catches trace-write failures, and emits `behavioral_influence=false` and `can_block=false` in every prediction event. `record_outcome` only appends an adjudication event; it does not train HNG or modify working memory.

## Integration sequence

1. Let the existing assistant interpret the turn and select its semantic action exactly as it does today.
2. Execute or send that action on the existing path.
3. Pass the already selected action, actual state, and actual response to the shadow recorder. Run this off the latency-critical thread where possible.
4. When the outcome can be observed, append a `ShadowOutcome`. A corrected adjudication is another append; the evaluator uses the latest while reporting revision count.
5. Store any transition in HNG through the normal authenticated evidence-ingestion path only if the deployment separately intends the HNG shadow to learn it. The recorder intentionally does not do this implicitly.

```python
turn = ActualAssistantTurn(
    conversation_id=conversation_id,
    turn_id=turn_id,
    current_state=assistant_state,
    actual_action_label=router_label,
    actual_action=semantic_action,
    user_text=user_text,
    actual_response=response,
)

# The action above has already been selected; this result is telemetry, not control.
observation = recorder.capture(turn)

# Later, after observation or blinded human/replay adjudication:
recorder.record_outcome(
    observation.trace_id,
    ShadowOutcome(task_success=True, action_regret=0.0, adjudicator="blind-review-2"),
)
```

## Trace contract

The JSONL log is append-only and durable (`flush` plus `fsync`). Use one writer process per trace file and any number of offline readers. Correlation is by random `trace_id`.

Prediction events contain:

- actual conversation/turn identifiers, actual action label, and structural summaries of actual state/action;
- a structural summary of HNG's carried/believed state and exact per-head comparison with the actual state;
- recalled candidate and included evidence IDs, stance, quality, exact scores, and provenance;
- governance decision, support/challenge/conflict scores, reasons, missing heads, and exclusions;
- HNG recommended action labels and scores;
- observer latency, serialized safe-frame bytes, candidate count, included evidence count, and component timings;
- immutable zero-influence assertions and any isolated error type.

Outcome events may label:

- actual task success and outcome score;
- correctness of the actual router action and HNG recommendation;
- whether HNG would have been better and the counterfactual regret;
- whether carried state fixed an ambiguous interpretation;
- whether HNG would have prevented a repeated failed strategy;
- constraint, staleness, perspective, unsupported-recommendation, abstention, contradiction, and provenance judgments.

Missing labels remain `null`. The evaluator reports the labeled denominator for every result and never converts missing labels to failures or successes.

## Privacy and retention

Defaults omit raw user text, assistant responses, evidence content, semantic vector values, outcome notes, and metadata values. Lengths, field kinds/dimensions, metadata keys, evidence IDs, and provenance remain for evaluation. This is data minimization, not anonymization: conversation IDs, source IDs, action labels, and provenance can still identify people or records.

Before real-user collection:

- replace identifiers with deployment-owned pseudonyms if the raw IDs are sensitive;
- keep tenant trace files and encryption boundaries separate;
- document purpose, consent or lawful basis, access, deletion, retention, and incident response;
- avoid `TextCaptureMode.FULL` and `include_semantic_values=True` unless the experiment truly requires them and has an approved handling plan;
- never publish raw traces. Release aggregates plus a carefully de-identified schema/sample.

## Adjudication and analysis

Freeze the hypotheses, label guide, eligible-turn rules, minimum sample, exclusion policy, and primary metric before reading results. Use blinded adjudicators when practical. Measure inter-rater agreement on a shared subset and resolve disagreements without seeing which action was HNG's.

The bundled evaluator reports:

- labeled task-success, continuity-fix, recommendation-better, repeat-failure, constraint, staleness, perspective, unsupported-recommendation, and provenance rates with Wilson 95% intervals;
- paired action-routing accuracy and its absolute delta when both actions are adjudicated;
- contradiction and abstention confusion matrices;
- non-negative action regret and observed outcome-score distributions;
- observer latency and context-cost distributions;
- missing-label coverage, malformed/orphan events, outcome revisions, HNG errors, and zero-influence violations.

Observed outcomes cannot establish a counterfactual when HNG recommended a different action. `hng_recommendation_better`, `hng_recommendation_correct`, and regret therefore require replay, simulation, or blinded expert adjudication. Report them as counterfactual judgments, not observed causal effects. A later randomized advisory A/B is required for a causal task-success claim.

## Evaluation slices

Pre-register at least these slices:

| Slice | Question |
|---|---|
| Ambiguous reference | Did deterministic carried state fix interpretation? |
| Semantic action routing | Was HNG's recommended action better than the existing router's? |
| Repeated strategy | Would governed episodic evidence prevent repeating a failed approach? |
| Perspective | Did it reduce role-, authority-, or expertise-inappropriate advice? |
| Changed environment/policy | Did it reject stale or superseded experience? |
| Evidence conflict | Did it challenge contradictions without excessive false challenges? |
| Insufficient evidence | Did it abstain when it should, and proceed when it should? |
| End-to-end | Did the assistant complete tasks better? |

Report per-slice sample sizes. Do not let a large easy slice conceal a small high-risk one.

## Rollout gates

1. **Shadow:** zero influence. Require zero influence-audit violations, acceptable privacy review, stable logging, bounded p95 overhead, and enough labeled data to estimate false-challenge and abstention behavior.
2. **Advisory:** inject the frame/challenge into reasoning, but HNG cannot block or execute. Use a randomized or otherwise defensible comparison against the unchanged assistant. Measure actual task success, not only reviewer preference.
3. **Selective governance:** consider mandatory reconsideration or human approval only in domains with enough independent evidence, very low false-challenge rates, explicit rollback, and continuous monitoring. HNG remains a memory/evidence control plane, not the primary autonomous safety authority.

No stage is justified by the example, unit tests, or prior synthetic ablations. Promotion requires results from the deployment's own real interactions and declared risk tolerance.
