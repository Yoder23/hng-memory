from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import math
import os
from pathlib import Path
import statistics
import threading
import time
from typing import Mapping
import uuid

from .governance import Decision, GovernedMemoryFrame, utc_now_iso
from .semantic import SemanticState, SemanticValue


TRACE_SCHEMA_VERSION = 1


class TextCaptureMode(str, Enum):
    """How potentially sensitive natural-language fields enter the trace."""

    OMIT = "omit"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class ActualAssistantTurn:
    """An action already selected by the unchanged production assistant."""

    conversation_id: str
    turn_id: str
    current_state: SemanticState
    actual_action_label: str = ""
    actual_action: SemanticValue | None = None
    user_text: str = ""
    actual_response: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    """Telemetry only: deliberately has no allow/block field or executable action."""

    trace_id: str
    persisted: bool
    decision: str | None
    recommended_actions: tuple[tuple[str, float], ...]
    latency_ms: float
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class ShadowOutcome:
    """Optional adjudication. Missing labels stay missing from every denominator."""

    outcome_code: str = ""
    outcome_score: float | None = None
    task_success: bool | None = None
    actual_action_correct: bool | None = None
    hng_recommendation_correct: bool | None = None
    hng_recommendation_better: bool | None = None
    carried_state_fixed_interpretation: bool | None = None
    prevented_repeat_failure: bool | None = None
    constraint_violation: bool | None = None
    stale_action: bool | None = None
    perspective_violation: bool | None = None
    unsupported_recommendation: bool | None = None
    should_abstain: bool | None = None
    contradiction_present: bool | None = None
    provenance_correct: bool | None = None
    action_regret: float | None = None
    next_state: SemanticState | None = None
    notes: str = ""
    adjudicator: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.action_regret is not None and self.action_regret < 0.0:
            raise ValueError("action_regret must be non-negative")


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_json_safe(item) for item in value]
    return repr(value)


def _semantic_value_view(value: SemanticValue, *, include_values: bool) -> dict[str, object]:
    if include_values:
        return _json_safe(value.as_storage())  # type: ignore[return-value]
    return {
        "kind": value.kind.value,
        "dimension": value.dimension,
        "model": value.model,
        "metadata_keys": sorted(map(str, value.metadata)),
        "value_omitted": True,
    }


def _state_view(state: SemanticState, *, include_values: bool) -> dict[str, object]:
    return {
        "revision": state.revision,
        "fields": {
            name: _semantic_value_view(value, include_values=include_values)
            for name, value in sorted(state.fields.items())
        },
    }


def _compare_states(actual: SemanticState, believed: SemanticState) -> dict[str, object]:
    heads = sorted(set(actual.fields) | set(believed.fields))
    similarities: dict[str, float | None] = {}
    for head in heads:
        left = actual.fields.get(head)
        right = believed.fields.get(head)
        similarities[head] = None if left is None or right is None else left.exact_similarity(right)
    comparable = [score for score in similarities.values() if score is not None]
    return {
        "actual_only_heads": sorted(set(actual.fields) - set(believed.fields)),
        "believed_only_heads": sorted(set(believed.fields) - set(actual.fields)),
        "exact_similarity_by_head": similarities,
        "mean_exact_similarity": None if not comparable else statistics.fmean(comparable),
    }


def _text_view(text: str, mode: TextCaptureMode) -> dict[str, object]:
    result: dict[str, object] = {"characters": len(text), "captured": mode is TextCaptureMode.FULL}
    if mode is TextCaptureMode.FULL:
        result["text"] = text
    return result


def _frame_view(frame: GovernedMemoryFrame) -> dict[str, object]:
    assessment = frame.assessment
    included = []
    for item in assessment.included:
        source = item.record.provenance
        included.append({
            "experience_id": item.record.experience_id,
            "evidence_group_id": item.record.evidence_group_id,
            "source_event_id": item.record.source_event_id,
            "stance": item.stance,
            "quality": item.quality,
            "semantic_scores": dict(item.semantic_scores),
            "provenance": {
                "source_type": source.source_type,
                "source_id": source.source_id,
                "trust_score": source.trust_score,
                "verified": source.verified,
                "verification_status": source.verification_status,
                "verifier": source.verifier,
                "observed_at": source.observed_at,
            },
            "content_omitted": True,
        })
    return {
        "schema_version": frame.schema_version,
        "query_mode": frame.mode,
        "generated_at": frame.generated_at,
        "decision": assessment.decision.value,
        "support_score": assessment.support_score,
        "challenge_score": assessment.challenge_score,
        "conflict_score": assessment.conflict_score,
        "independent_support_count": assessment.independent_support_count,
        "independent_challenge_count": assessment.independent_challenge_count,
        "evidence_quality": assessment.evidence_quality,
        "reasons": list(assessment.reasons),
        "missing_state": list(assessment.missing_state),
        "included": included,
        "excluded": [
            {"experience_id": item.experience_id, "reason": item.reason}
            for item in assessment.excluded
        ],
        "original_candidates": [item.as_dict() for item in assessment.original_candidates],
        "retrieved_candidates": frame.retrieved_candidates,
        "perspective_fields": sorted(map(str, frame.perspective)),
        "open_loop_count": len(frame.open_loops),
        "constraint_count": len(frame.constraints),
        "component_ms": dict(assessment.component_ms),
        "hng_latency_ms": assessment.latency_ms,
    }


class HDCShadowABRecorder:
    """Append-only real-turn shadow recorder with no behavioral control surface.

    Call ``capture`` only after the production assistant has selected its action.
    All HNG and trace-write failures are converted to telemetry so the shadow cannot
    interrupt the live assistant. One process should own a trace file; readers may
    evaluate it concurrently.
    """

    def __init__(self, memory: object, path: str | Path, *,
                 text_capture: TextCaptureMode = TextCaptureMode.OMIT,
                 include_semantic_values: bool = False,
                 include_metadata: bool = False,
                 collect_recommendations: bool = True):
        self.memory = memory
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.text_capture = TextCaptureMode(text_capture)
        self.include_semantic_values = bool(include_semantic_values)
        self.include_metadata = bool(include_metadata)
        self.collect_recommendations = bool(collect_recommendations)
        self._lock = threading.Lock()
        self._known_trace_ids: set[str] = set()
        self._load_known_ids()

    def _load_known_ids(self) -> None:
        if not self.path.exists():
            return
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("event_type") == "prediction" and row.get("trace_id"):
                    self._known_trace_ids.add(str(row["trace_id"]))
        except OSError:
            pass

    def _append(self, event: Mapping[str, object]) -> None:
        encoded = json.dumps(_json_safe(event), sort_keys=True, separators=(",", ":")) + "\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

    def capture(self, turn: ActualAssistantTurn, *, lexical_query: str = "") -> ShadowObservation:
        """Observe an already chosen action; never raises and never changes it."""

        trace_id = str(uuid.uuid4())
        started = time.perf_counter()
        error_type: str | None = None
        believed = SemanticState()
        frame: GovernedMemoryFrame | None = None
        recommendations: tuple[tuple[str, float], ...] = ()
        try:
            believed = self.memory.working_state(turn.conversation_id).prior_semantic_state
            if turn.actual_action is None:
                frame = self.memory.context(
                    turn.conversation_id, query=turn.current_state, lexical_query=lexical_query
                )
            else:
                frame = self.memory.evaluate_action(
                    turn.current_state,
                    turn.actual_action,
                    conversation_id=turn.conversation_id,
                    lexical_query=lexical_query,
                )
            if self.collect_recommendations:
                try:
                    recommendations = tuple(
                        (str(label), float(score))
                        for label, score in self.memory.recommend_actions(
                            turn.current_state, conversation_id=turn.conversation_id
                        )
                    )
                except Exception as exc:  # shadow recommendation failure is non-fatal
                    error_type = f"recommendation:{type(exc).__name__}"
        except Exception as exc:  # shadow memory failure is non-fatal
            error_type = f"memory:{type(exc).__name__}"
        elapsed = (time.perf_counter() - started) * 1000.0
        try:
            frame_payload = None if frame is None else _frame_view(frame)
            if frame_payload is not None:
                frame_payload["serialized_context_bytes"] = len(
                    json.dumps(frame_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
                )
            metadata: object = (
                _json_safe(turn.metadata) if self.include_metadata else {
                    "keys": sorted(map(str, turn.metadata))
                }
            )
            event = {
                "trace_schema_version": TRACE_SCHEMA_VERSION,
                "event_type": "prediction",
                "trace_id": trace_id,
                "captured_at": utc_now_iso(),
                "deployment": {
                    "mode": "shadow",
                    "behavioral_influence": False,
                    "can_block": False,
                    "actual_action_selected_before_capture": True,
                },
                "actual": {
                    "conversation_id": turn.conversation_id,
                    "turn_id": turn.turn_id,
                    "current_state": _state_view(
                        turn.current_state, include_values=self.include_semantic_values
                    ),
                    "actual_action_label": turn.actual_action_label,
                    "actual_action": None if turn.actual_action is None else _semantic_value_view(
                        turn.actual_action, include_values=self.include_semantic_values
                    ),
                    "user_text": _text_view(turn.user_text, self.text_capture),
                    "actual_response": _text_view(turn.actual_response, self.text_capture),
                    "metadata": metadata,
                },
                "shadow": {
                    "believed_state": _state_view(
                        believed, include_values=self.include_semantic_values
                    ),
                    "state_comparison": _compare_states(turn.current_state, believed),
                    "frame": frame_payload,
                    "recommended_actions": [
                        {"label": label, "score": score} for label, score in recommendations
                    ],
                    "observer_latency_ms": elapsed,
                    "error_type": error_type,
                },
            }
        except Exception as exc:  # malformed telemetry must not reach the action path
            error_type = error_type or f"instrumentation:{type(exc).__name__}"
            event = {
                "trace_schema_version": TRACE_SCHEMA_VERSION,
                "event_type": "prediction",
                "trace_id": trace_id,
                "captured_at": utc_now_iso(),
                "deployment": {
                    "mode": "shadow",
                    "behavioral_influence": False,
                    "can_block": False,
                    "actual_action_selected_before_capture": True,
                },
                "actual": {
                    "conversation_id": str(turn.conversation_id),
                    "turn_id": str(turn.turn_id),
                    "telemetry_omitted": True,
                },
                "shadow": {
                    "frame": None,
                    "recommended_actions": [],
                    "observer_latency_ms": elapsed,
                    "error_type": error_type,
                },
            }
        persisted = True
        try:
            self._append(event)
            self._known_trace_ids.add(trace_id)
        except Exception as exc:  # trace I/O must not enter the production action path
            persisted = False
            error_type = error_type or f"persistence:{type(exc).__name__}"
        decision = None if frame is None else frame.assessment.decision.value
        return ShadowObservation(trace_id, persisted, decision, recommendations, elapsed, error_type)

    def record_outcome(self, trace_id: str, outcome: ShadowOutcome) -> None:
        """Append a label/revision after an outcome is known; does not train HNG."""

        trace_id = str(trace_id)
        if trace_id not in self._known_trace_ids:
            raise KeyError(f"unknown trace_id: {trace_id}")
        labels = {
            name: getattr(outcome, name)
            for name in (
                "outcome_score", "task_success", "actual_action_correct",
                "hng_recommendation_correct", "hng_recommendation_better",
                "carried_state_fixed_interpretation", "prevented_repeat_failure",
                "constraint_violation", "stale_action", "perspective_violation",
                "unsupported_recommendation", "should_abstain", "contradiction_present",
                "provenance_correct", "action_regret",
            )
        }
        event = {
            "trace_schema_version": TRACE_SCHEMA_VERSION,
            "event_type": "outcome",
            "trace_id": trace_id,
            "captured_at": utc_now_iso(),
            "outcome": {
                "outcome_code": outcome.outcome_code,
                "labels": labels,
                "next_state": None if outcome.next_state is None else _state_view(
                    outcome.next_state, include_values=self.include_semantic_values
                ),
                "notes": _text_view(outcome.notes, self.text_capture),
                "adjudicator": outcome.adjudicator,
                "metadata": _json_safe(outcome.metadata) if self.include_metadata else {
                    "keys": sorted(map(str, outcome.metadata))
                },
            },
        }
        self._append(event)


def _wilson(successes: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denominator
    radius = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def _rate(values: list[bool]) -> dict[str, object]:
    successes = sum(values)
    total = len(values)
    return {
        "n": total,
        "true": successes,
        "false": total - successes,
        "rate": None if total == 0 else successes / total,
        "wilson_95": _wilson(successes, total),
    }


def _distribution(values: list[float]) -> dict[str, object]:
    if not values:
        return {"n": 0, "mean": None, "p50": None, "p95": None, "min": None, "max": None}
    ordered = sorted(values)
    percentile = lambda fraction: ordered[min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)]
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "min": ordered[0],
        "max": ordered[-1],
    }


class ShadowABEvaluator:
    """Offline evaluator for append-only prediction/outcome events."""

    ABSTENTION_DECISIONS = {
        Decision.INSUFFICIENT_EVIDENCE.value,
        Decision.INSUFFICIENT_STATE.value,
        Decision.UNTRUSTED_EVIDENCE.value,
        Decision.PROFILE_UNCERTAIN.value,
    }
    CONTRADICTION_DECISIONS = {Decision.CHALLENGE.value, Decision.CONFLICTED.value}

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def summarize(self) -> dict[str, object]:
        predictions: dict[str, dict[str, object]] = {}
        outcomes: dict[str, dict[str, object]] = {}
        outcome_revisions: dict[str, int] = {}
        malformed = unknown_events = orphan_outcomes = 0
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                trace_id = str(row.get("trace_id") or "")
                if row.get("event_type") == "prediction" and trace_id:
                    predictions[trace_id] = row
                elif row.get("event_type") == "outcome" and trace_id:
                    if trace_id not in predictions:
                        orphan_outcomes += 1
                    outcomes[trace_id] = row
                    outcome_revisions[trace_id] = outcome_revisions.get(trace_id, 0) + 1
                else:
                    unknown_events += 1

        joined = [trace_id for trace_id in predictions if trace_id in outcomes]
        labels_by_trace: dict[str, dict[str, object]] = {
            trace_id: dict(outcomes[trace_id].get("outcome", {}).get("labels", {}))
            for trace_id in joined
        }

        def booleans(name: str) -> list[bool]:
            return [bool(labels[name]) for labels in labels_by_trace.values() if labels.get(name) is not None]

        def numbers(name: str) -> list[float]:
            return [float(labels[name]) for labels in labels_by_trace.values() if labels.get(name) is not None]

        decisions: dict[str, int] = {}
        latency: list[float] = []
        context_bytes: list[float] = []
        retrieved: list[float] = []
        included: list[float] = []
        influence_violations = shadow_errors = 0
        for row in predictions.values():
            deployment = dict(row.get("deployment") or {})
            influence_violations += int(
                deployment.get("behavioral_influence") is not False
                or deployment.get("can_block") is not False
            )
            shadow = dict(row.get("shadow") or {})
            shadow_errors += int(bool(shadow.get("error_type")))
            latency.append(float(shadow.get("observer_latency_ms") or 0.0))
            frame = shadow.get("frame")
            if isinstance(frame, dict):
                decision = str(frame.get("decision") or "unknown")
                decisions[decision] = decisions.get(decision, 0) + 1
                context_bytes.append(float(frame.get("serialized_context_bytes") or 0.0))
                retrieved.append(float(frame.get("retrieved_candidates") or 0.0))
                included.append(float(len(frame.get("included") or ())))
            else:
                decisions["unavailable"] = decisions.get("unavailable", 0) + 1

        paired = [
            labels for labels in labels_by_trace.values()
            if labels.get("actual_action_correct") is not None
            and labels.get("hng_recommendation_correct") is not None
        ]
        actual_correct = [bool(labels["actual_action_correct"]) for labels in paired]
        hng_correct = [bool(labels["hng_recommendation_correct"]) for labels in paired]

        contradiction_expected: list[bool] = []
        contradiction_predicted: list[bool] = []
        abstention_expected: list[bool] = []
        abstention_predicted: list[bool] = []
        for trace_id in joined:
            labels = labels_by_trace[trace_id]
            frame = dict(predictions[trace_id].get("shadow") or {}).get("frame")
            if not isinstance(frame, dict):
                continue
            decision = str(frame.get("decision") or "")
            if labels.get("contradiction_present") is not None:
                contradiction_expected.append(bool(labels["contradiction_present"]))
                contradiction_predicted.append(decision in self.CONTRADICTION_DECISIONS)
            if labels.get("should_abstain") is not None:
                abstention_expected.append(bool(labels["should_abstain"]))
                abstention_predicted.append(decision in self.ABSTENTION_DECISIONS)

        def classification(expected: list[bool], predicted: list[bool]) -> dict[str, object]:
            tp = sum(e and p for e, p in zip(expected, predicted))
            fp = sum((not e) and p for e, p in zip(expected, predicted))
            tn = sum((not e) and (not p) for e, p in zip(expected, predicted))
            fn = sum(e and (not p) for e, p in zip(expected, predicted))
            total = len(expected)
            return {
                "n": total, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
                "accuracy": None if total == 0 else (tp + tn) / total,
                "precision": None if tp + fp == 0 else tp / (tp + fp),
                "recall": None if tp + fn == 0 else tp / (tp + fn),
            }

        metric_names = (
            "task_success", "actual_action_correct", "hng_recommendation_correct",
            "hng_recommendation_better", "carried_state_fixed_interpretation",
            "prevented_repeat_failure", "constraint_violation", "stale_action",
            "perspective_violation", "unsupported_recommendation", "should_abstain",
            "contradiction_present", "provenance_correct",
        )
        coverage = {
            name: {"labeled": len(booleans(name)), "total_predictions": len(predictions)}
            for name in metric_names
        }
        return {
            "trace_schema_version": TRACE_SCHEMA_VERSION,
            "data_quality": {
                "predictions": len(predictions),
                "outcomes": len(outcomes),
                "joined": len(joined),
                "unlabeled_predictions": len(predictions) - len(joined),
                "malformed_lines": malformed,
                "unknown_events": unknown_events,
                "orphan_outcomes": orphan_outcomes,
                "outcome_revisions": sum(max(0, value - 1) for value in outcome_revisions.values()),
                "label_coverage": coverage,
            },
            "zero_influence_audit": {
                "violations": influence_violations,
                "passes": influence_violations == 0,
                "shadow_errors": shadow_errors,
            },
            "decisions": decisions,
            "outcomes": {
                "task_success": _rate(booleans("task_success")),
                "continuity_fixed_interpretation": _rate(booleans("carried_state_fixed_interpretation")),
                "hng_recommendation_better": _rate(booleans("hng_recommendation_better")),
                "repeat_failure_preventable": _rate(booleans("prevented_repeat_failure")),
                "constraint_violation": _rate(booleans("constraint_violation")),
                "stale_action": _rate(booleans("stale_action")),
                "perspective_violation": _rate(booleans("perspective_violation")),
                "unsupported_recommendation": _rate(booleans("unsupported_recommendation")),
                "provenance_correct": _rate(booleans("provenance_correct")),
                "action_regret": _distribution(numbers("action_regret")),
                "outcome_score": _distribution(numbers("outcome_score")),
            },
            "paired_action_routing": {
                "n": len(paired),
                "actual_correct": _rate(actual_correct),
                "hng_correct": _rate(hng_correct),
                "absolute_accuracy_delta": None if not paired else (
                    sum(hng_correct) - sum(actual_correct)
                ) / len(paired),
            },
            "contradiction_detection": classification(
                contradiction_expected, contradiction_predicted
            ),
            "abstention": classification(abstention_expected, abstention_predicted),
            "operational_cost": {
                "observer_latency_ms": _distribution(latency),
                "serialized_context_bytes": _distribution(context_bytes),
                "retrieved_candidates": _distribution(retrieved),
                "included_evidence": _distribution(included),
            },
        }
