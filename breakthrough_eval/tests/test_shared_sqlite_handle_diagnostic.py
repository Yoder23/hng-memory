from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
from pathlib import Path

import pytest

from breakthrough_eval.scripts import shared_sqlite_handle_diagnostic as matrix
from breakthrough_eval.scripts import shared_sqlite_handle_type_diagnostic as typed
from breakthrough_eval.scripts import shared_sqlite_handle_type_diagnostic_v2 as typed_v2
from breakthrough_eval.scripts import shared_sqlite_handle_type_diagnostic_v3 as typed_v3
from breakthrough_eval.scripts import shared_sqlite_handle_diagnostic_v2 as matrix_v2
from breakthrough_eval.scripts import windows_handle_snapshot


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


def test_v2_preparation_freezes_independent_sampler_and_lower_bound() -> None:
    names = (
        "OUTPUT_DIR", "PROTOCOL", "PREPARED", "RESULT", "EVENTS",
        "RUN_DATA", "WRAPPER", "V2_FAILURE", "OBSERVER_RESULT",
        "SOURCE_FILES", "matrix_worker", "classify",
    )
    original = {name: getattr(matrix, name) for name in names}
    args = qualifying_args()
    args.shared_support_slope_handles_per_minute = 10.0
    try:
        matrix_v2.configure()
        payload = json.loads(matrix_v2.PREPARED.read_text(encoding="utf-8"))
        matrix.verify_prepared(payload, args)
        assert payload["config"][
            "shared_support_slope_handles_per_minute"
        ] == 10.0
        assert matrix.matrix_worker is matrix_v2.threaded_matrix_worker
        assert matrix.classify is matrix_v2.classify_v2
        assert set(payload["source_sha256"]) == {
            "breakthrough_eval/reliability/shared_sqlite_handle_diagnostic/RESULTS.json",
            "breakthrough_eval/reliability/shared_sqlite_handle_diagnostic_v2/PROTOCOL.md",
            "breakthrough_eval/scripts/shared_sqlite_handle_diagnostic.py",
            "breakthrough_eval/scripts/shared_sqlite_handle_diagnostic_v2.py",
        }
    finally:
        for name, value in original.items():
            setattr(matrix, name, value)


def test_typed_preparation_freezes_handle_enumerator_and_thresholds() -> None:
    names = (
        "OUTPUT_DIR", "PROTOCOL", "PREPARED", "RESULT", "EVENTS",
        "RUN_DATA", "WRAPPER", "V2_FAILURE", "OBSERVER_RESULT",
        "SOURCE_FILES", "frozen_config", "matrix_worker", "run_condition",
        "classify", "run_matrix",
    )
    original = {name: getattr(matrix, name) for name in names}
    args = qualifying_args()
    args.condition_seconds = 60.0
    args.minimum_samples_per_child = 50
    args.shared_support_slope_handles_per_minute = 10.0
    try:
        typed.configure()
        payload = json.loads(typed.PREPARED.read_text(encoding="utf-8"))
        matrix.verify_prepared(payload, args)
        assert payload["config"]["minimum_dominance_fraction"] == 0.8
        assert payload["config"]["minimum_dominant_type_delta"] == 10.0
        assert payload["config"]["control_maximum_type_delta"] == 2
        assert set(payload["source_sha256"]) == {
            "breakthrough_eval/reliability/shared_sqlite_handle_diagnostic_v2/RESULTS.json",
            "breakthrough_eval/reliability/shared_sqlite_handle_type_diagnostic/PROTOCOL.md",
            "breakthrough_eval/scripts/shared_sqlite_handle_diagnostic.py",
            "breakthrough_eval/scripts/shared_sqlite_handle_type_diagnostic.py",
            "breakthrough_eval/scripts/windows_handle_snapshot.py",
        }
    finally:
        for name, value in original.items():
            setattr(matrix, name, value)


def test_typed_v2_preparation_pins_preserved_preflight_failure() -> None:
    names = (
        "OUTPUT_DIR", "PROTOCOL", "PREPARED", "RESULT", "EVENTS",
        "RUN_DATA", "WRAPPER", "V2_FAILURE", "OBSERVER_RESULT",
        "SOURCE_FILES", "frozen_config", "matrix_worker", "run_condition",
        "classify", "run_matrix",
    )
    original = {name: getattr(matrix, name) for name in names}
    args = qualifying_args()
    args.condition_seconds = 60.0
    args.minimum_samples_per_child = 50
    args.shared_support_slope_handles_per_minute = 10.0
    try:
        typed_v2.configure()
        payload = json.loads(typed_v2.PREPARED.read_text(encoding="utf-8"))
        matrix.verify_prepared(payload, args)
        assert payload["source_sha256"][
            "breakthrough_eval/reliability/shared_sqlite_handle_type_diagnostic/RESULTS.json"
        ] == "aacd71337084dfe198873ed164c7d6588f95a75f2da04d2e15931d409b7ffd2b"
        assert (
            "breakthrough_eval/scripts/shared_sqlite_handle_type_diagnostic_v2.py"
            in payload["source_sha256"]
        )
    finally:
        for name, value in original.items():
            setattr(matrix, name, value)


def test_typed_v3_preparation_pins_queue_failure_and_drain_fix() -> None:
    names = (
        "OUTPUT_DIR", "PROTOCOL", "PREPARED", "RESULT", "EVENTS",
        "RUN_DATA", "WRAPPER", "V2_FAILURE", "OBSERVER_RESULT",
        "SOURCE_FILES", "frozen_config", "matrix_worker", "run_condition",
        "classify", "run_matrix",
    )
    original = {name: getattr(matrix, name) for name in names}
    args = qualifying_args()
    args.condition_seconds = 60.0
    args.minimum_samples_per_child = 50
    args.shared_support_slope_handles_per_minute = 10.0
    try:
        typed_v3.configure()
        payload = json.loads(typed_v3.PREPARED.read_text(encoding="utf-8"))
        matrix.verify_prepared(payload, args)
        assert payload["source_sha256"][
            "breakthrough_eval/reliability/shared_sqlite_handle_type_diagnostic_v2/RESULTS.json"
        ] == "760c97c46802f4474f71eb26956af695f6eb4aeb32604f22da85dcf3012c4704"
        assert matrix.run_condition is typed_v3.queue_safe_run_condition
        assert (
            "breakthrough_eval/scripts/shared_sqlite_handle_type_diagnostic_v3.py"
            in payload["source_sha256"]
        )
    finally:
        for name, value in original.items():
            setattr(matrix, name, value)


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


def detailed_condition(
    median: float, maximum: float, child_slope: float, valid: bool = True,
) -> dict[str, object]:
    return {
        "valid": valid,
        "median_slope_handles_per_minute": median,
        "maximum_slope_handles_per_minute": maximum,
        "per_child": [
            {"slope_handles_per_minute": child_slope} for _ in range(12)
        ],
    }


def test_v2_replicated_lower_bound_rule() -> None:
    args = qualifying_args()
    args.shared_support_slope_handles_per_minute = 10.0
    results = {
        "idle_12": detailed_condition(0.5, 1.0, 0.5),
        "isolated_sqlite_12": detailed_condition(0.7, 1.0, 0.7),
        "shared_sqlite_12_a": detailed_condition(31.0, 32.0, 30.0),
        "shared_sqlite_12_b": detailed_condition(17.0, 18.0, 16.0),
    }

    assert matrix_v2.classify_v2(results, args) == (
        "SUPPORTS_SHARED_SQLITE_CAUSE"
    )


def typed_condition(
    slope: float, maximum: float, event_delta: int,
) -> dict[str, object]:
    reports = [
        {
            "handle_type_delta": {"Event": event_delta, "File": 0},
        }
        for _ in range(12)
    ]
    return {
        "valid": True,
        "median_slope_handles_per_minute": slope,
        "maximum_slope_handles_per_minute": maximum,
        "per_child": [
            {"slope_handles_per_minute": slope} for _ in range(12)
        ],
        "reports": reports,
    }


def test_typed_diagnostic_identifies_replicated_dominant_type() -> None:
    args = qualifying_args()
    args.shared_support_slope_handles_per_minute = 10.0
    results = {
        "idle_12": typed_condition(0.5, 1.0, 0),
        "isolated_sqlite_12": typed_condition(0.7, 1.0, 1),
        "shared_sqlite_12_a": typed_condition(30.0, 31.0, 25),
        "shared_sqlite_12_b": typed_condition(32.0, 33.0, 27),
    }

    assert typed.classify_typed(results, args) == (
        "IDENTIFIES_DOMINANT_HANDLE_TYPE"
    )
    assert typed.summarize_types(results)["shared_sqlite_12_a"][
        "dominant_type"
    ] == "Event"


@pytest.mark.skipif(
    matrix.sustained.psutil is None
    or not hasattr(matrix.sustained.psutil.Process(), "num_handles"),
    reason="Windows psutil num_handles is required",
)
def test_windows_handle_type_snapshot_accounts_for_handle_total() -> None:
    process = matrix.sustained.psutil.Process()
    before = process.num_handles()
    histogram = windows_handle_snapshot.current_process_handle_types()
    after = process.num_handles()

    assert "<query-error>" not in histogram
    assert min(before, after) - 2 <= sum(histogram.values()) <= max(before, after) + 2


def test_terminal_v2_matrix_is_content_addressed_and_supports_shared_sqlite() -> None:
    output = matrix.ROOT / (
        "breakthrough_eval/reliability/shared_sqlite_handle_diagnostic_v2"
    )
    result_path = output / "RESULTS.json"
    events_path = output / "events.jsonl"
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == (
        "d8d061fd4e2807565fb595714d76e342347925b565b26e4351e7f630934f5e1d"
    )
    assert hashlib.sha256(events_path.read_bytes()).hexdigest() == (
        "902d2af03484d98154a9c8e3cf9f6a00e02840dae1bb4d4dd65ebba1ca55f75e"
    )
    assert result["status"] == "PASS"
    assert result["outcome"] == "SUPPORTS_SHARED_SQLITE_CAUSE"
    assert result["preregistered_commit"] == (
        "245090724cfbb1552388b44a4d17a939321b6fe8"
    )
    assert all(item["valid"] for item in result["conditions"].values())
    assert all(
        min(child["samples"] for child in item["per_child"]) >= 80
        for item in result["conditions"].values()
    )
    assert max(
        result["conditions"][name]["maximum_slope_handles_per_minute"]
        for name in ("idle_12", "isolated_sqlite_12")
    ) < 5.0
    assert all(
        min(child["slope_handles_per_minute"] for child in item["per_child"])
        >= 10.0
        for name, item in result["conditions"].items()
        if name.startswith("shared_sqlite")
    )


def test_typed_v2_queue_failure_is_content_addressed_and_invalid() -> None:
    result_path = typed_v2.RESULT
    events_path = typed_v2.EVENTS
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == (
        "760c97c46802f4474f71eb26956af695f6eb4aeb32604f22da85dcf3012c4704"
    )
    assert hashlib.sha256(events_path.read_bytes()).hexdigest() == (
        "5f62a7c5cab0aa5e5b65202ba2b7e770991452f1cba865b418d51dc60141a6b7"
    )
    assert result["status"] == "ERROR"
    assert result["outcome"] == "INVALID"
    assert result["dominant_handle_type"] == "Section"
    assert all(
        len(item["reports"]) == 9 and not item["valid"]
        for item in result["conditions"].values()
    )
    assert all(
        not item["validity"]["all_children_reported"]
        and not item["validity"]["all_child_exitcodes_zero"]
        and item["validity"]["handle_type_snapshots_complete"]
        for item in result["conditions"].values()
    )
    for name in ("shared_sqlite_12_a", "shared_sqlite_12_b"):
        analysis = result["handle_type_analysis"][name]
        assert analysis["dominant_type"] == "Section"
        assert analysis["dominance_fraction_of_positive_median_delta"] > 0.9


def test_typed_v3_result_is_content_addressed_and_identifies_sections() -> None:
    result_path = typed_v3.RESULT
    events_path = typed_v3.EVENTS
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == (
        "8c8ae43b0600bd338d8e692b355090a89a4aa19570a6b4e1201a5c8a54382cd2"
    )
    assert hashlib.sha256(events_path.read_bytes()).hexdigest() == (
        "c73439e68864cb3d6ebda4a5c43c6c990a04466f8db83abed3b9b18e6cef9c62"
    )
    assert result["status"] == "PASS"
    assert result["outcome"] == "IDENTIFIES_DOMINANT_HANDLE_TYPE"
    assert result["dominant_handle_type"] == "Section"
    assert all(
        item["valid"] and len(item["reports"]) == 12
        and item["exitcodes"] == [0] * 12
        and item["report_drain_order"] == "concurrent_before_join"
        for item in result["conditions"].values()
    )
    for name in ("shared_sqlite_12_a", "shared_sqlite_12_b"):
        analysis = result["handle_type_analysis"][name]
        assert analysis["dominant_type"] == "Section"
        assert analysis["dominant_type_median_delta"] == 48.0
        assert analysis["dominance_fraction_of_positive_median_delta"] > 0.94
    for name in ("idle_12", "isolated_sqlite_12"):
        assert result["handle_type_analysis"][name]["median_delta_by_type"][
            "Section"
        ] == 0.0


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


@pytest.mark.skipif(
    matrix.sustained.psutil is None
    or not hasattr(matrix.sustained.psutil.Process(), "num_handles"),
    reason="Windows psutil num_handles is required",
)
def test_v2_independent_sampler_multiprocess_smoke(tmp_path: Path) -> None:
    names = (
        "OUTPUT_DIR", "PROTOCOL", "PREPARED", "RESULT", "EVENTS",
        "RUN_DATA", "WRAPPER", "V2_FAILURE", "OBSERVER_RESULT",
        "SOURCE_FILES", "matrix_worker", "classify",
    )
    original = {name: getattr(matrix, name) for name in names}
    output = tmp_path / "matrix-v2"
    args = qualifying_args()
    args.condition_seconds = 2.0
    args.sample_interval_seconds = 0.2
    args.writer_workers = 1
    args.reader_workers = 1
    args.seed_records = 20
    args.tenants = 2
    args.minimum_samples_per_child = 5
    args.shared_support_slope_handles_per_minute = 10.0
    try:
        matrix_v2.configure()
        matrix.OUTPUT_DIR = output
        matrix.RESULT = output / "RESULTS.json"
        matrix.EVENTS = output / "events.jsonl"
        matrix.RUN_DATA = output / "run_data"
        result = matrix.run_matrix(args)

        assert result["status"] == "PASS"
        assert all(
            min(child["samples"] for child in item["per_child"]) >= 5
            for item in result["conditions"].values()
        )
        assert all(
            item["exitcodes"] == [0, 0]
            for item in result["conditions"].values()
        )
    finally:
        for name, value in original.items():
            setattr(matrix, name, value)


@pytest.mark.skipif(
    matrix.sustained.psutil is None
    or not hasattr(matrix.sustained.psutil.Process(), "num_handles"),
    reason="Windows psutil num_handles is required",
)
def test_typed_snapshot_multiprocess_smoke(tmp_path: Path) -> None:
    names = (
        "OUTPUT_DIR", "PROTOCOL", "PREPARED", "RESULT", "EVENTS",
        "RUN_DATA", "WRAPPER", "V2_FAILURE", "OBSERVER_RESULT",
        "SOURCE_FILES", "frozen_config", "matrix_worker", "run_condition",
        "classify", "run_matrix",
    )
    original = {name: getattr(matrix, name) for name in names}
    output = tmp_path / "matrix-typed"
    args = qualifying_args()
    args.condition_seconds = 2.0
    args.sample_interval_seconds = 0.2
    args.writer_workers = 1
    args.reader_workers = 1
    args.seed_records = 20
    args.tenants = 2
    args.minimum_samples_per_child = 5
    args.shared_support_slope_handles_per_minute = 10.0
    try:
        typed.configure()
        matrix.OUTPUT_DIR = output
        matrix.RESULT = output / "RESULTS.json"
        matrix.EVENTS = output / "events.jsonl"
        matrix.RUN_DATA = output / "run_data"
        result = matrix.run_matrix(args)

        assert result["status"] == "PASS"
        assert result["benchmark"] == (
            "shared_sqlite_child_handle_type_diagnostic"
        )
        assert all(
            item["validity"]["handle_type_snapshots_complete"]
            for item in result["conditions"].values()
        )
        assert all(
            "handle_type_delta" in report
            for item in result["conditions"].values()
            for report in item["reports"]
        )
    finally:
        for name, value in original.items():
            setattr(matrix, name, value)


@pytest.mark.skipif(
    matrix.sustained.psutil is None
    or not hasattr(matrix.sustained.psutil.Process(), "num_handles"),
    reason="Windows psutil num_handles is required",
)
def test_typed_v3_drains_twelve_reports_before_join(tmp_path: Path) -> None:
    names = (
        "OUTPUT_DIR", "PROTOCOL", "PREPARED", "RESULT", "EVENTS",
        "RUN_DATA", "WRAPPER", "V2_FAILURE", "OBSERVER_RESULT",
        "SOURCE_FILES", "frozen_config", "matrix_worker", "run_condition",
        "classify", "run_matrix",
    )
    original = {name: getattr(matrix, name) for name in names}
    output = tmp_path / "matrix-typed-v3"
    args = qualifying_args()
    args.condition_seconds = 2.0
    args.sample_interval_seconds = 0.2
    args.writer_workers = 4
    args.reader_workers = 8
    args.seed_records = 20
    args.tenants = 2
    args.minimum_samples_per_child = 5
    args.shared_support_slope_handles_per_minute = 10.0
    try:
        typed_v3.configure()
        matrix.RUN_DATA = output / "run_data"
        matrix.RUN_DATA.mkdir(parents=True)
        events_path = output / "events.jsonl"
        with events_path.open("x", encoding="utf-8", newline="\n") as events:
            result = typed_v3.queue_safe_run_condition(
                mp.get_context("spawn"), "idle_12", 0, args, events
            )

        assert result["valid"]
        assert result["report_drain_order"] == "concurrent_before_join"
        assert len(result["reports"]) == 12
        assert result["exitcodes"] == [0] * 12
        assert result["validity"]["handle_type_snapshots_complete"]
    finally:
        for name, value in original.items():
            setattr(matrix, name, value)
