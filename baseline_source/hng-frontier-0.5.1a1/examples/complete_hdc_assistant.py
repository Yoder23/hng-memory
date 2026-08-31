"""Complete model-independent HDC assistant loop using the governed control plane."""
from __future__ import annotations

from pathlib import Path
import tempfile

import numpy as np

from hngfrontier import (Commitment, EvidenceProvenance, HDCAssistantAdapter, HNGMemory,
                         SemanticState, SemanticValue, WorkingCorrection)

DIM = 2048


def atom(seed: int) -> SemanticValue:
    return SemanticValue.hdc(np.random.default_rng(seed).choice([-1, 1], size=DIM), dimension=DIM,
                             model="example-hdc-interpreter-v1")


def interpreter(text: str, *, prior_state, working_context, perspective, governed_frame):
    """Stand-in for an application's HDC interpreter; no LLM or embedding API is used."""
    fields = dict(prior_state.fields)
    fields.setdefault("state", atom(1)); fields.setdefault("goal", atom(2)); fields.setdefault("sequence", atom(3))
    # A real interpreter binds/bundles `text` with these exact carried heads.
    fields["entity"] = atom(abs(hash(text)) % 1_000_000)
    assert "recent_exact_turns" in working_context
    assert governed_frame.assessment.decision.value
    return SemanticState(fields, prior_state.revision + 1)


def main(root: str | Path | None = None) -> None:
    path = Path(root) if root is not None else Path(tempfile.mkdtemp(prefix="hng-hdc-example-"))
    provenance = EvidenceProvenance("system_telemetry", "example-runtime", 1, True)
    with HNGMemory(path, semantic_backend="reference-hng") as memory:
        initial = SemanticState({"state": atom(1), "goal": atom(2), "sequence": atom(3)})
        memory.record_turn("chat", turn_id="1", speaker="user", content="Investigate API latency", semantics=initial)
        memory.update_working_state("chat", active_episode="incident-42", current_goal=atom(2),
                                    current_facts=("latency started after deploy 27",),
                                    open_loops=("check database saturation",), constraints=("do not restart primary",))
        memory.add_correction("chat", WorkingCorrection("fix-1", "deploy 26", "deploy 27", "user correction"))
        memory.add_commitment("chat", Commitment("commit-1", "preserve primary availability"))

        action = atom(10)
        memory.remember_transition(conversation_id="history", state=initial, action=action,
                                   next_state=atom(11), outcome="restart caused an outage", outcome_score=-1,
                                   provenance=provenance, source_event_id="telemetry:restart-outage")
        adapter = HDCAssistantAdapter(memory, interpreter)
        encoded = adapter.encode_turn("Could that restart hurt availability?", conversation_id="chat")
        assessment = memory.evaluate_action(encoded, action, conversation_id="chat")
        print(assessment.to_prompt_context(max_tokens=800))

        memory.record_turn("chat", turn_id="2", speaker="user",
                           content="Could that restart hurt availability?", semantics=encoded)
        assert memory.working_state("chat").recent_turns[-1].turn_id == "2"


if __name__ == "__main__":
    main()
