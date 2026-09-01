from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

from breakthrough_eval.scripts import shared_sqlite_handle_diagnostic as matrix
from breakthrough_eval.scripts import wal_checkpoint_rotation_diagnostic as rotation


def smoke_args() -> argparse.Namespace:
    return argparse.Namespace(
        prepare_only=False,
        preregistered_commit="commit",
        baseline_seconds=2.0,
        treatment_replications=1,
        treatment_epochs=2,
        treatment_epoch_seconds=1.0,
        writer_workers=1,
        reader_workers=1,
        seed_records=20,
        tenants=2,
        sample_interval_seconds=0.2,
        baseline_minimum_samples_per_child=5,
        treatment_minimum_samples_per_child=3,
        baseline_minimum_shm_unit_delta=1,
        baseline_minimum_maximum_process_handles=1,
        treatment_maximum_process_handles=1000,
        treatment_maximum_section_delta_per_epoch=100,
        maximum_post_checkpoint_wal_bytes=32768,
        minimum_treatment_throughput_ratio=0.01,
    )


def qualifying_args() -> argparse.Namespace:
    return argparse.Namespace(
        prepare_only=False,
        preregistered_commit="commit",
        baseline_seconds=120.0,
        treatment_replications=2,
        treatment_epochs=4,
        treatment_epoch_seconds=30.0,
        writer_workers=4,
        reader_workers=8,
        seed_records=1000,
        tenants=100,
        sample_interval_seconds=1.0,
        baseline_minimum_samples_per_child=100,
        treatment_minimum_samples_per_child=25,
        baseline_minimum_shm_unit_delta=60,
        baseline_minimum_maximum_process_handles=300,
        treatment_maximum_process_handles=300,
        treatment_maximum_section_delta_per_epoch=40,
        maximum_post_checkpoint_wal_bytes=32768,
        minimum_treatment_throughput_ratio=0.5,
    )


def test_preparation_freezes_rotation_checkpoint_treatment() -> None:
    payload = json.loads(rotation.PREPARED.read_text(encoding="utf-8"))

    rotation.verify_prepared(payload, qualifying_args())
    assert payload["config"]["checkpoint_mode"] == "TRUNCATE"
    assert payload["config"]["treatment_epochs"] == 4
    assert payload["config"]["treatment_replications"] == 2
    assert payload["config"]["treatment_maximum_process_handles"] == 300
    assert payload["source_sha256"][
        "breakthrough_eval/reliability/shared_sqlite_wal_index_diagnostic/RESULTS.json"
    ] == "6a9f8e438ab4f97be867e547749814699f3a3472fcd811613bae8fb7eed0a498"


@pytest.mark.skipif(
    matrix.sustained.psutil is None
    or not hasattr(matrix.sustained.psutil.Process(), "num_handles"),
    reason="Windows psutil num_handles is required",
)
def test_short_rotation_checkpoint_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "rotation"
    monkeypatch.setattr(rotation, "OUTPUT_DIR", output)
    monkeypatch.setattr(rotation, "RESULT", output / "RESULTS.json")
    monkeypatch.setattr(rotation, "EVENTS", output / "events.jsonl")
    monkeypatch.setattr(rotation, "RUN_DATA", output / "run_data")

    result = rotation.run_diagnostic(smoke_args())

    assert result["status"] == "PASS"
    assert result["baseline"]["summary"]["valid"]
    assert result["baseline"]["identity"]["passed"]
    treatment = result["treatments"][0]
    assert treatment["identity"]["passed"]
    assert len(treatment["epochs"]) == 2
    assert all(epoch["summary"]["valid"] for epoch in treatment["epochs"])
    assert all(epoch["checkpoint"]["passed"] for epoch in treatment["epochs"])
    assert all(
        epoch["checkpoint"]["file_state"]["wal_bytes"] <= 32768
        for epoch in treatment["epochs"]
    )


def test_terminal_rotation_result_is_content_addressed_and_bounded() -> None:
    result_path = rotation.RESULT
    events_path = rotation.EVENTS
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == (
        "2a36539c6e27140c6d9246c2055f468127bc1161c5f48ad8862feb45f726186b"
    )
    assert hashlib.sha256(events_path.read_bytes()).hexdigest() == (
        "cf74b802e6ae8333bbb8a7703f3e3b0a2edc348d9e5ae568f7359f65cd5c3d30"
    )
    assert result["status"] == "PASS"
    assert result["outcome"] == "SUPPORTS_ROTATE_CHECKPOINT_WAL_BOUNDING"
    baseline = result["baseline"]
    assert baseline["summary"]["maximum_process_handles"] == 329
    assert baseline["summary"]["maximum_section_delta"] == 99
    assert baseline["summary"]["median_shm_unit_delta"] == 99.0
    assert baseline["identity"]["passed"]
    assert [
        max(epoch["summary"]["maximum_process_handles"] for epoch in treatment["epochs"])
        for treatment in result["treatments"]
    ] == [252, 256]
    assert [
        max(epoch["summary"]["maximum_section_delta"] for epoch in treatment["epochs"])
        for treatment in result["treatments"]
    ] == [21, 25]
    assert all(
        treatment["identity"]["passed"]
        and treatment["throughput_operations_per_second"]
        >= baseline["throughput_operations_per_second"]
        and all(
            epoch["checkpoint"]["passed"]
            and epoch["checkpoint"]["busy"] == 0
            and epoch["checkpoint"]["file_state"]["wal_bytes"] == 0
            for epoch in treatment["epochs"]
        )
        for treatment in result["treatments"]
    )
