from breakthrough_eval.scripts.provenance_ablation import run


def test_provenance_ablation_is_fixed_candidate_and_preserves_ties():
    result = run()
    summaries = result["summaries"]
    assert result["status"] == "PASS"
    assert result["invariants"]["scenario_count"] == 25
    assert result["invariants"]["no_provenance_equals_display_only_decisions"]
    assert summaries["no_provenance"] == summaries["provenance_displayed_only"]
    assert summaries["hng_provenance_governance"] == summaries["strong_structured_provenance_governance"]
    assert result["hng_vs_strong_accuracy_delta"] == 0.0
    assert result["paired_statistics"]["hng_vs_no_provenance"]["exact_two_sided_p"] < 1e-7
    assert result["paired_statistics"]["hng_vs_strong"]["exact_two_sided_p"] == 1.0
