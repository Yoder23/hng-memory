from breakthrough_eval.scripts.belief_revision_probe import run


def test_belief_revision_probe_preserves_strong_baseline_tie():
    result = run(4)
    arms = result["arms"]
    hng = arms["hng_belief_store_authority"]
    strong = arms["strong_structured_authority"]
    assert hng["current_belief_accuracy"] == 1.0
    assert hng["contradiction_recognition_rate"] == 1.0
    assert hng["historical_reconstruction_rate"] == 1.0
    assert hng["provenance_preservation_rate"] == 1.0
    assert hng == strong
    assert result["hng_vs_strong_structured"]["accuracy_delta"] == 0.0


def test_untrusted_contradiction_does_not_replace_current_hng_belief():
    result = run(1)
    sample = result["samples"][0]
    assert sample["hng"]["current_statement"] == "state-0-c"
    assert [item["statement"] for item in sample["hng"]["history"]] == [
        "state-0-a", "state-0-b", "state-0-c"
    ]
    assert sample["timeline"][2]["id"] in sample["hng"]["preserved_evidence_ids"]
