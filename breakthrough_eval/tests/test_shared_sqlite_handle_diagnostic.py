from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from breakthrough_eval.scripts import shared_sqlite_handle_diagnostic as matrix


def qualifying_args() -> argparse.Namespace:
    return argparse.Namespace(
        preregistered_commit="commit",
        condition_seconds=90.0,
        sample_interval_seconds=1.0,
        writer_workers=4,
        reader_workers=8,
        seed_records=1000,
        tenants=100,
        minimum_samples_per_child=80,
        shared_support_slope_handles_per_minute=20.0,
        shared_replication_tolerance_handles_per_minute=15.0,
        control_maximum_slope_handles_per_minute=5.0,
        process_count_support_slope_handles_per_minute=20.0,
    )


def test_preparation_freezes_four_condition_root_cause_matrix() -> None:
    payload = matrix.prepared_payload(qualifying_args())

    assert payload["status"] == "PREPARED_NOT_EXECUTED"
    assert payload["config"]["conditions"] == list(matrix.CONDITIONS)
    assert payload["config"]["condition_seconds"] == 90.0
    assert payload["config"]["writer_workers"] == 4
    assert payload["config"]["reader_workers"] == 8
    assert set(payload["source_sha256"]) == {
        "breakthrough_eval/reliability/shared_sqlite_handle_diagnostic/PROTOCOL.md",
        "breakthrough_eval/scripts/shared_sqlite_handle_diagnostic.py",
        "baseline_source/hng-frontier-0.5.1a1/src/hngfrontier/storage_v2.py",
        "breakthrough_eval/reliability/sustained_2h_v2/FAILURE_ANALYSIS.json",
        "breakthrough_eval/reliability/handle_observer_diagnostic_v3/RESULTS.json",
    }
    assert "Root-cause diagnostic only" in payload["claim_boundary"]


def test_frozen_preparation_matches_current_sources() -> None:
    payload = json.loads(matrix.PREPARED.read_text(encoding="utf-8"))

    matrix.verify_prepared(payload, qualifying_args())


def condition(slope: float, valid: bool = True) -> dict[str, object]:
    return {"valid": valid, "median_slope_handles_per_minute": slope}


def test_frozen_classification_rules() -> None:
    args = qualifying_args()

    shared = {
        "idle_12": condition(0.0),
        "isolated_sqlite_12": condition(1.0),
        "shared_sqlite_12_a": condition(30.0),
        "shared_sqlite_12_b": condition(32.0),
    }
    process_count = {name: condition(25.0) for name in matrix.CONDITIONS}
    quiet = {name: condition(0.0) for name in matrix.CONDITIONS}
    invalid = {**quiet, "shared_sqlite_12_b": condition(0.0, False)}

    assert matrix.classify(shared, args) == "SUPPORTS_SHARED_SQLITE_CAUSE"
    assert matrix.classify(process_count, args) == "SUPPORTS_PROCESS_COUNT_CAUSE"
    assert matrix.classify(quiet, args) == "DOES_NOT_REPRODUCE"
    assert matrix.classify(invalid, args) == "INVALID"


@pytest.mark.skipif(
    matrix.sustained.psutil is None
    or not hasattr(matrix.sustained.psutil.Process(), "num_handles"),
    reason="Windows psutil num_handles is required",
)
def test_short_multiprocess_matrix_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "matrix"
    monkeypatch.setattr(matrix, "OUTPUT_DIR", output)
    monkeypatch.setattr(matrix, "RESULT", output / "RESULTS.json")
    monkeypatch.setattr(matrix, "EVENTS", output / "events.jsonl")
    monkeypatch.setattr(matrix, "RUN_DATA", output / "run_data")
    args = qualifying_args()
    args.condition_seconds = 2.0
    args.sample_interval_seconds = 0.2
    args.writer_workers = 1
    args.reader_workers = 1
    args.seed_records = 20
    args.tenants = 2
    args.minimum_samples_per_child = 5

    result = matrix.run_matrix(args)

    assert result["status"] == "PASS"
    assert set(result["conditions"]) == set(matrix.CONDITIONS)
    assert all(item["valid"] for item in result["conditions"].values())
    assert all(
        item["exitcodes"] == [0, 0]
        for item in result["conditions"].values()
    )
