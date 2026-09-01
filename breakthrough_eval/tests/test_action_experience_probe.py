from breakthrough_eval.scripts.action_experience_probe import run


def test_action_experience_executes_and_preserves_strong_baseline_comparison():
    result = run(100)
    summaries = result["summaries"]
    hng = summaries["hng_governed_transitions"]
    strong = summaries["strong_structured"]
    semantic = summaries["semantic_action_router"]
    assert result["status"] == "PASS"
    assert result["model_weights_changed"] is False
    assert hng["attempts"] == 100
    assert hng["action_success_rate"] > semantic["action_success_rate"]
    assert result["hng_vs_strong"]["success_rate_delta"] == 0.0
    assert result["hng_vs_strong"]["regret_delta"] == 0
    assert len(hng["performance_curve"]) == 5
    assert hng["correct_abstention_coverage"] == 1.0
    assert hng["unsolved_state_environments"] == 0
