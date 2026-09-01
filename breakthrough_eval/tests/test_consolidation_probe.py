from breakthrough_eval.scripts.consolidation_probe import run


def test_consolidation_is_reversible_but_does_not_change_action_quality():
    result = run(groups=3, events_per_group=3, copies_per_event=2)
    assert result["status"] == "PASS"
    assert result["patterns"] == 3
    assert result["raw_records"] == 18
    assert result["raw_evidence_deleted"] is False
    assert result["action_quality_changed"] is False
    assert result["rare_event_preserved"]
    assert result["duplicate_resistance_passed"]
    assert result["provenance_reversible"]
    assert result["pattern_invalidation_preserves_raw"]
    assert result["patterns_only"]["status"] == "NOT_EXECUTABLE"
