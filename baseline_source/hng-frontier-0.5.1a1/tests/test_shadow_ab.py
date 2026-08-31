from __future__ import annotations

import json

import numpy as np

from hngfrontier.control import HNGMemory
from hngfrontier.governance import EvidenceKind, EvidenceProvenance
from hngfrontier.semantic import SemanticState, SemanticValue
from hngfrontier.shadow_ab import (
    ActualAssistantTurn,
    HDCShadowABRecorder,
    ShadowABEvaluator,
    ShadowOutcome,
)


def hv(seed: int) -> SemanticValue:
    return SemanticValue.hdc(
        np.random.default_rng(seed).integers(0, 2, 256, dtype=np.uint8), dimension=256
    )


def state(seed: int = 1) -> SemanticState:
    return SemanticState({"state": hv(seed), "goal": hv(seed + 1), "sequence": hv(seed + 2)})


def test_real_turn_capture_is_zero_influence_and_private_by_default(tmp_path):
    trace = tmp_path / "shadow.jsonl"
    actual_state = state()
    chosen_action = hv(9)
    with HNGMemory(tmp_path / "memory", semantic_backend="reference-hng") as memory:
        memory.update_state("conversation", state(20))
        recorder = HDCShadowABRecorder(memory, trace)
        turn = ActualAssistantTurn(
            "conversation",
            "turn-1",
            actual_state,
            actual_action_label="production-router-action",
            actual_action=chosen_action,
            user_text="USER-SECRET-MUST-NOT-APPEAR",
            actual_response="RESPONSE-SECRET-MUST-NOT-APPEAR",
            metadata={"sensitive": "METADATA-SECRET-MUST-NOT-APPEAR"},
        )

        observation = recorder.capture(turn)

    assert observation.persisted is True
    assert chosen_action is turn.actual_action
    row = json.loads(trace.read_text(encoding="utf-8"))
    assert row["deployment"] == {
        "mode": "shadow",
        "behavioral_influence": False,
        "can_block": False,
        "actual_action_selected_before_capture": True,
    }
    assert row["actual"]["user_text"] == {"captured": False, "characters": 27}
    assert row["actual"]["actual_action"]["value_omitted"] is True
    encoded = trace.read_text(encoding="utf-8")
    assert "USER-SECRET-MUST-NOT-APPEAR" not in encoded
    assert "RESPONSE-SECRET-MUST-NOT-APPEAR" not in encoded
    assert "METADATA-SECRET-MUST-NOT-APPEAR" not in encoded


def test_challenge_and_recalled_evidence_cannot_change_actual_action(tmp_path):
    trace = tmp_path / "shadow.jsonl"
    actual_state, chosen_action = state(), hv(9)
    with HNGMemory(tmp_path / "memory", semantic_backend="reference-hng") as memory:
        memory.ingest_evidence(
            content="EVIDENCE-CONTENT-MUST-NOT-APPEAR",
            semantics=actual_state.merged({"action": chosen_action}, revision=0),
            provenance=EvidenceProvenance("system_telemetry", "failed-action", 1.0, True),
            kind=EvidenceKind.OUTCOME,
            outcome_score=-1.0,
            source_event_id="failed-action",
            evidence_group_id="failed-action",
            metadata={"action_label": "avoid-this-action"},
        )
        recorder = HDCShadowABRecorder(memory, trace)
        turn = ActualAssistantTurn(
            "c", "t", actual_state,
            actual_action_label="already-selected-action", actual_action=chosen_action,
        )
        observation = recorder.capture(turn)

    assert observation.decision == "challenge"
    assert observation.recommended_actions == (("avoid-this-action", -1.0),)
    assert turn.actual_action is chosen_action
    row = json.loads(trace.read_text(encoding="utf-8"))
    assert row["shadow"]["frame"]["included"][0]["content_omitted"] is True
    assert row["deployment"]["can_block"] is False
    assert "EVIDENCE-CONTENT-MUST-NOT-APPEAR" not in trace.read_text(encoding="utf-8")


class BrokenMemory:
    def working_state(self, conversation_id):
        raise RuntimeError("must not escape")


def test_shadow_memory_and_persistence_failures_never_escape_capture(tmp_path):
    recorder = HDCShadowABRecorder(BrokenMemory(), tmp_path / "trace.jsonl")
    result = recorder.capture(ActualAssistantTurn("c", "t", state()))
    assert result.persisted is True
    assert result.error_type == "memory:RuntimeError"

    directory_as_file = tmp_path / "not-a-file"
    directory_as_file.mkdir()
    recorder = HDCShadowABRecorder(BrokenMemory(), directory_as_file)
    result = recorder.capture(ActualAssistantTurn("c", "t2", state()))
    assert result.persisted is False
    assert result.error_type == "memory:RuntimeError"

    malformed = SemanticState({"not-a-semantic-value": object()})
    recorder = HDCShadowABRecorder(BrokenMemory(), tmp_path / "malformed.jsonl")
    result = recorder.capture(ActualAssistantTurn("c", "t3", malformed))
    assert result.persisted is True


def test_outcomes_survive_restart_and_latest_adjudication_wins(tmp_path):
    trace = tmp_path / "shadow.jsonl"
    with HNGMemory(tmp_path / "memory", semantic_backend="reference-hng") as memory:
        first = HDCShadowABRecorder(memory, trace).capture(
            ActualAssistantTurn("c", "t", state(), actual_action_label="actual", actual_action=hv(9))
        )
        reopened = HDCShadowABRecorder(memory, trace)
        reopened.record_outcome(
            first.trace_id,
            ShadowOutcome(
                task_success=False,
                actual_action_correct=True,
                hng_recommendation_correct=False,
                action_regret=0.5,
                contradiction_present=False,
                should_abstain=True,
                adjudicator="reviewer-a",
            ),
        )
        reopened.record_outcome(
            first.trace_id,
            ShadowOutcome(
                task_success=True,
                actual_action_correct=True,
                hng_recommendation_correct=False,
                action_regret=0.0,
                contradiction_present=False,
                should_abstain=True,
                adjudicator="reviewer-b",
            ),
        )

    report = ShadowABEvaluator(trace).summarize()
    assert report["data_quality"]["predictions"] == 1
    assert report["data_quality"]["outcome_revisions"] == 1
    assert report["outcomes"]["task_success"]["rate"] == 1.0
    assert report["outcomes"]["action_regret"]["mean"] == 0.0
    assert report["paired_action_routing"]["absolute_accuracy_delta"] == -1.0
    assert report["zero_influence_audit"]["passes"] is True


def test_evaluator_uses_explicit_label_denominators(tmp_path):
    trace = tmp_path / "shadow.jsonl"
    with HNGMemory(tmp_path / "memory", semantic_backend="reference-hng") as memory:
        recorder = HDCShadowABRecorder(memory, trace)
        labeled = recorder.capture(ActualAssistantTurn("c", "t1", state()))
        recorder.capture(ActualAssistantTurn("c", "t2", state()))
        recorder.record_outcome(
            labeled.trace_id,
            ShadowOutcome(task_success=True, constraint_violation=False),
        )

    report = ShadowABEvaluator(trace).summarize()
    quality = report["data_quality"]
    assert quality["predictions"] == 2
    assert quality["joined"] == 1
    assert quality["unlabeled_predictions"] == 1
    assert quality["label_coverage"]["task_success"]["labeled"] == 1
    assert quality["label_coverage"]["provenance_correct"]["labeled"] == 0
    assert report["outcomes"]["task_success"]["n"] == 1
    assert report["outcomes"]["provenance_correct"]["rate"] is None
