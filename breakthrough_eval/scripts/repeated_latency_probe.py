#!/usr/bin/env python3
"""Repeated-run latency intervals for the synthetic executing tool-agent probe."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts import tool_agent_advisory_probe as probe  # noqa: E402


SEED = 20260901


def percentile(values: Sequence[float], fraction: float) -> float:
    return probe.percentile(values, fraction)


def bootstrap_mean_ci(values: Sequence[float], *, samples: int = 10_000, seed: int = SEED) -> dict[str, float]:
    if len(values) < 2:
        raise ValueError("at least two independent run values required")
    rng = random.Random(seed)
    draws = []
    for _ in range(samples):
        draws.append(statistics.mean(values[rng.randrange(len(values))] for _ in values))
    return {
        "mean": statistics.mean(values),
        "ci95_low": percentile(draws, 0.025),
        "ci95_high": percentile(draws, 0.975),
        "run_min": min(values),
        "run_max": max(values),
    }


def compile_repeats(runs: Sequence[Mapping[str, object]]) -> dict[str, object]:
    behavior_hashes = []
    for run in runs:
        events = run["events"]
        behavior_hashes.append(probe.stable_hash([
            {
                "episode": row["episode"],
                "arm": row["arm"],
                "action": row["action"],
                "task_success": row["task_success"],
                "decisions": row["decisions"],
            }
            for row in events
        ]))
    arms = {}
    for arm in probe.ARMS:
        per_run = []
        for run in runs:
            values = [float(row["decision_latency_ms"]) for row in run["events"] if row["arm"] == arm]
            per_run.append({
                "mean": statistics.mean(values),
                "p50": percentile(values, 0.50),
                "p95": percentile(values, 0.95),
                "p99": percentile(values, 0.99),
            })
        arms[arm] = {
            "repeat_count": len(per_run),
            "episodes_per_repeat": len([row for row in runs[0]["events"] if row["arm"] == arm]),
            "across_repeat_bootstrap_95_ci_ms": {
                statistic: bootstrap_mean_ci([row[statistic] for row in per_run], seed=SEED + offset)
                for offset, statistic in enumerate(("mean", "p50", "p95", "p99"))
            },
            "per_repeat_ms": per_run,
        }
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "benchmark": "repeated_synthetic_tool_agent_decision_latency",
        "claim_boundary": (
            "Independent process-local store runs on one Windows host; intervals estimate the mean "
            "of per-run latency statistics under this synthetic workload, not deployment SLOs or cross-host variation."
        ),
        "repeat_count": len(runs),
        "behavior_identical_across_repeats": len(set(behavior_hashes)) == 1,
        "behavior_sha256": behavior_hashes[0],
        "arms": arms,
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--episodes", type=int, default=108)
    parser.add_argument("--output", type=Path, default=ROOT / "breakthrough_eval" / "latency" / "RESULTS.json")
    parser.add_argument("--raw", type=Path, default=ROOT / "breakthrough_eval" / "latency" / "raw" / "events.jsonl")
    args = parser.parse_args()
    if args.repeats < 2:
        raise ValueError("repeats must be at least two")
    if args.output.exists() or args.raw.exists():
        raise FileExistsError("refusing to overwrite repeated latency evidence")
    runs = [probe.run(args.episodes, f"latency_repeat_{index:02d}") for index in range(args.repeats)]
    result = compile_repeats(runs)
    args.raw.parent.mkdir(parents=True, exist_ok=True)
    with args.raw.open("x", encoding="utf-8", newline="\n") as handle:
        for repeat, run in enumerate(runs):
            for event in run["events"]:
                handle.write(json.dumps({"repeat": repeat, **event}, sort_keys=True) + "\n")
    result["raw_log"] = args.raw.resolve().relative_to(ROOT).as_posix()
    result["raw_event_count"] = sum(len(run["events"]) for run in runs)
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "repeats": args.repeats, "raw_events": result["raw_event_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
