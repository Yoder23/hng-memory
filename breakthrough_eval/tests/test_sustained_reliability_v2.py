from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import pytest

from breakthrough_eval.scripts import sustained_reliability_v2 as v2


def qualifying_args() -> argparse.Namespace:
    return argparse.Namespace(
        duration_seconds=7200.0,
        writer_workers=4,
        reader_workers=8,
        tenants=100,
        seed_records=1000,
        rotation_seconds=900.0,
        minimum_worker_epochs=8,
        backup_interval_seconds=600.0,
        writer_pause_timeout_seconds=30.0,
        backup_timeout_seconds=180.0,
        sample_interval_seconds=60.0,
        minimum_writes=100_000,
        minimum_reads=100_000,
        minimum_backup_cycles=12,
        minimum_resource_samples=100,
        maximum_rss_per_process_bytes=1_500_000_000,
        maximum_handles_per_process=1024,
        minimum_free_bytes=40_000_000_000,
        runtime_free_floor_bytes=30_000_000_000,
    )


def test_preparation_freezes_failure_driven_recovery_contract() -> None:
    payload = v2.prepared_payload(qualifying_args())

    assert payload["status"] == "PREPARED_NOT_EXECUTED"
    assert payload["predecessor_failure"].endswith("INTERRUPTED.json")
    assert payload["config"]["duration_seconds"] == 7200.0
    assert payload["config"]["minimum_worker_epochs"] == 8
    assert payload["config"]["minimum_backup_cycles"] == 12
    assert payload["config"]["backup_timeout_seconds"] == 180.0
    assert payload["config"]["backup_contract"] == (
        "writers_paused_at_transaction_boundary_readers_live"
    )
    assert payload["qualifying_command"][-1] == "COMMIT"
    assert set(payload["source_sha256"]) == {
        "breakthrough_eval/reliability/sustained_2h_v2/PROTOCOL.md",
        "breakthrough_eval/scripts/sustained_reliability_v2.py",
        "breakthrough_eval/scripts/sustained_reliability.py",
        "breakthrough_eval/scripts/storage_reliability_probe.py",
        (
            "baseline_source/hng-frontier-0.5.1a1/src/"
            "hngfrontier/storage_v2.py"
        ),
    }


def test_prepared_verifier_rejects_changed_backup_timeout() -> None:
    payload = v2.prepared_payload(qualifying_args())
    changed = copy.deepcopy(payload)
    changed["config"]["backup_timeout_seconds"] = 181.0

    with pytest.raises(RuntimeError, match="configuration mismatch"):
        v2.verify_prepared(changed, qualifying_args())


def test_frozen_v2_preparation_matches_current_sources() -> None:
    payload = json.loads(v2.PREPARED.read_text(encoding="utf-8"))

    v2.verify_prepared(payload, qualifying_args())


def test_terminal_v2_failure_is_content_addressed_and_fail_closed() -> None:
    result = json.loads(v2.RESULT.read_text(encoding="utf-8"))
    analysis_path = v2.OUTPUT_DIR / "FAILURE_ANALYSIS.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

    assert result["status"] == "ERROR"
    assert result["error"] == "RuntimeError: runtime handle cap exceeded"
    assert analysis["status"] == "ERROR_SAFETY_CAP"
    assert analysis["qualifying_result_exists"] is False
    assert analysis["execution"]["exit_code"] == 1
    assert analysis["execution"]["workers_live_after_termination"] == 0
    assert analysis["completed_work"]["backup_restore_cycles_passed"] == 6
    assert analysis["execution"]["worker_epochs_passed"] == 4
    assert analysis["failure"]["observed_maximum_process_handles"] == 1059
    assert "duration_reached" in analysis["unmet_frozen_criteria"]
    assert analysis["observer_effect_hypothesis"]["status"] == "UNPROVEN"

    tracked = {
        item["path"]: item
        for item in analysis["preserved_artifacts"]
        if item["tracked"]
    }
    for relative, item in tracked.items():
        path = v2.ROOT / relative
        assert path.stat().st_size == item["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_runtime_safety_rejects_each_cap() -> None:
    args = qualifying_args()
    sample = {
        "maximum_process_rss_bytes": 1,
        "maximum_process_handles": 1,
        "free_bytes": args.runtime_free_floor_bytes,
    }
    v2.enforce_runtime_safety(sample, args)
    with pytest.raises(RuntimeError, match="RSS"):
        v2.enforce_runtime_safety({
            **sample,
            "maximum_process_rss_bytes": (
                args.maximum_rss_per_process_bytes + 1
            ),
        }, args)
    with pytest.raises(RuntimeError, match="handle"):
        v2.enforce_runtime_safety({
            **sample,
            "maximum_process_handles": (
                args.maximum_handles_per_process + 1
            ),
        }, args)
    with pytest.raises(RuntimeError, match="free-space"):
        v2.enforce_runtime_safety({
            **sample,
            "free_bytes": args.runtime_free_floor_bytes - 1,
        }, args)


@pytest.mark.skipif(
    v2.v1.psutil is None,
    reason="psutil is required only for sustained evaluation",
)
def test_v2_multiprocess_pause_backup_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "sustained-v2"
    monkeypatch.setattr(v2, "OUTPUT_DIR", output)
    monkeypatch.setattr(v2, "RUN_DATA", output / "run_data")
    monkeypatch.setattr(
        v2, "DATABASE", output / "run_data" / "sustained-v2.sqlite"
    )
    monkeypatch.setattr(v2, "EVENTS", output / "events.jsonl")
    monkeypatch.setattr(v2, "RESULT", output / "RESULTS.json")
    args = argparse.Namespace(
        duration_seconds=8.0,
        writer_workers=4,
        reader_workers=4,
        tenants=4,
        seed_records=40,
        rotation_seconds=4.0,
        minimum_worker_epochs=2,
        backup_interval_seconds=2.0,
        writer_pause_timeout_seconds=10.0,
        backup_timeout_seconds=30.0,
        sample_interval_seconds=0.5,
        minimum_writes=10,
        minimum_reads=10,
        minimum_backup_cycles=4,
        minimum_resource_samples=8,
        maximum_rss_per_process_bytes=1_500_000_000,
        maximum_handles_per_process=1024,
        minimum_free_bytes=1_000_000,
        runtime_free_floor_bytes=1,
    )

    result = v2.run_soak(args)

    assert result["status"] == "PASS"
    assert len(result["worker_epochs"]) >= 2
    assert len(result["backup_restore_cycles"]) >= 4
    assert all(
        item["passed"] for item in result["backup_restore_cycles"]
    )
    assert all(
        item["writer_pause_acknowledgement_seconds"] <= 10.0
        for item in result["backup_restore_cycles"]
    )
    assert result["backup_restore_cycles"][-1][
        "expected_live_identity"
    ] is True
    assert result["criteria"]["runtime_disk_floor_respected"] is True
