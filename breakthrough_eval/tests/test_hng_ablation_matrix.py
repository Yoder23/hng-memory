from __future__ import annotations

import json

from breakthrough_eval.scripts import hng_ablation_matrix as matrix


def test_counterfactuals_preserve_scenario_count_and_candidate_ids():
    scenarios = matrix.generate_scenarios()
    assert len(scenarios) == 250
    scenario = scenarios[0]
    for transform in matrix.TRANSFORMS.values():
        changed = transform(scenario)
        assert changed.case_id == scenario.case_id
        assert changed.candidate_ids == scenario.candidate_ids


def test_trust_ablation_uses_a_recognized_max_trust_source():
    scenario = next(item for item in matrix.generate_scenarios() if item.family == "untrusted_poison")
    changed = matrix.no_provenance_or_trust(scenario)
    assert all(item.provenance.source_type == "system_telemetry" for item in changed.candidates)
    assert all(item.provenance.verified for item in changed.candidates)


def test_compiled_revision_two_matrix_is_complete():
    path = matrix.OUTPUT / "RESULTS.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["status"] == "complete"
    assert result["protocol_revision"] == 2
    assert result["scenario_count"] == 250
    assert result["failure_count"] == 0
    assert result["summaries"]["full_hng"]["accuracy"] == 0.9
    assert result["summaries"]["minus_provenance_and_trust"]["accuracy"] == 0.7
