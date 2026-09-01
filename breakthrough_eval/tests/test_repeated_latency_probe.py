from __future__ import annotations

from breakthrough_eval.scripts import repeated_latency_probe as latency


def test_bootstrap_mean_interval_contains_observed_mean():
    result = latency.bootstrap_mean_ci([1.0, 2.0, 3.0, 4.0], samples=1000)
    assert result["ci95_low"] <= result["mean"] <= result["ci95_high"]
    assert result["run_min"] == 1.0
    assert result["run_max"] == 4.0


def test_compile_repeats_requires_stable_behavior_and_reports_p99():
    runs = []
    for repeat in range(2):
        events = []
        for arm_index, arm in enumerate(latency.probe.ARMS):
            for episode in range(2):
                events.append({
                    "episode": episode, "arm": arm, "action": arm_index,
                    "task_success": True, "decisions": {},
                    "decision_latency_ms": float(repeat + episode + arm_index + 1),
                })
        runs.append({"events": events})
    result = latency.compile_repeats(runs)
    assert result["behavior_identical_across_repeats"]
    assert result["arms"]["hng_advisory"]["repeat_count"] == 2
    assert "p99" in result["arms"]["hng_advisory"]["across_repeat_bootstrap_95_ci_ms"]
