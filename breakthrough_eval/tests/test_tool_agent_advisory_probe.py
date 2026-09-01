from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts.tool_agent_advisory_probe import ARMS, run


def test_tool_agent_probe_freezes_candidates_and_executes_all_arms():
    result = run(36, "unit")
    assert result["status"] == "complete"
    assert result["episodes"] == 36
    assert result["invariants"]["candidate_pool_identical_across_arms"] is True
    assert result["invariants"]["same_episode_count_per_arm"] is True
    assert result["invariants"]["hard_gate_disabled"] is True
    assert set(result["summaries"]) == set(ARMS)
    assert len(result["events"]) == 36 * len(ARMS)
    assert all(summary["episodes"] == 36 for summary in result["summaries"].values())
    assert result["task_features"]["irreversible_effects"] is True
    assert result["task_features"]["conflicting_observations"] is True


def test_tool_agent_probe_rejects_non_phase_aligned_episode_count():
    try:
        run(35, "invalid")
    except ValueError as exc:
        assert "multiple of 36" in str(exc)
    else:
        raise AssertionError("expected phase-alignment validation")
