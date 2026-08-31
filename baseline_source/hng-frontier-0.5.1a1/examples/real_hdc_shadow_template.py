"""Instrumentation smoke/template only; it is not a real-user experiment result."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

import numpy as np

from hngfrontier import (
    ActualAssistantTurn,
    HDCShadowABRecorder,
    HNGMemory,
    SemanticState,
    SemanticValue,
    ShadowABEvaluator,
    ShadowOutcome,
)


def hdc(seed: int) -> SemanticValue:
    bits = np.random.default_rng(seed).integers(0, 2, 1024, dtype=np.uint8)
    return SemanticValue.hdc(bits, dimension=1024, model="assistant-native-hdc")


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="hng-shadow-template-"))
    trace = root / "real_hdc_shadow.jsonl"
    actual_state = SemanticState({"state": hdc(1), "goal": hdc(2), "sequence": hdc(3)})

    with HNGMemory(root / "memory", semantic_backend="reference-hng") as memory:
        recorder = HDCShadowABRecorder(memory, trace)

        # In production, the unchanged assistant/router must select this first.
        selected_action = hdc(4)
        response = "Synthetic response from the unchanged example assistant."

        observation = recorder.capture(ActualAssistantTurn(
            conversation_id="synthetic-conversation",
            turn_id="synthetic-turn-1",
            current_state=actual_state,
            actual_action_label="synthetic-router-choice",
            actual_action=selected_action,
            user_text="Synthetic user turn",
            actual_response=response,
        ))

        # This hand-written label only proves the append/evaluation path works.
        recorder.record_outcome(observation.trace_id, ShadowOutcome(
            outcome_code="synthetic_smoke_only",
            task_success=True,
            actual_action_correct=True,
            action_regret=0.0,
            adjudicator="example-fixture",
        ))

    report = ShadowABEvaluator(trace).summarize()
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Synthetic trace: {trace}")


if __name__ == "__main__":
    main()
