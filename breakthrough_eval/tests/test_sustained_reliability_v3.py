from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from breakthrough_eval.scripts import sustained_reliability_v3 as v3


def qualifying_args() -> argparse.Namespace:
    return argparse.Namespace(
        duration_seconds=7200.0,
        writer_workers=4,
        reader_workers=8,
        tenants=100,
        seed_records=1000,
        rotation_seconds=30.0,
        minimum_worker_epochs=216,
        backup_interval_seconds=600.0,
        writer_pause_timeout_seconds=30.0,
        backup_timeout_seconds=180.0,
        sample_interval_seconds=30.0,
        minimum_writes=100_000,
        minimum_reads=100_000,
        minimum_backup_cycles=12,
        minimum_resource_samples=216,
        maximum_rss_per_process_bytes=1_500_000_000,
        maximum_handles_per_process=1024,
        minimum_free_bytes=40_000_000_000,
        runtime_free_floor_bytes=30_000_000_000,
    )


def test_preparation_freezes_checkpoint_bounded_contract() -> None:
    payload = v3.prepared_payload(qualifying_args())

    assert payload["status"] == "PREPARED_NOT_EXECUTED"
    assert payload["config"]["rotation_seconds"] == 30.0
    assert payload["config"]["minimum_worker_epochs"] == 216
    assert payload["config"]["maximum_handles_per_process"] == 1024
    assert payload["config"]["checkpoint_contract"] == (
        "fully_quiescent_truncate_after_every_worker_epoch"
    )
    assert payload["config"]["maximum_post_checkpoint_wal_bytes"] == 32_768
    assert payload["qualifying_command"][-1] == "COMMIT"
    assert any(
        path.endswith("wal_checkpoint_rotation_diagnostic/RESULTS.json")
        for path in payload["source_sha256"]
    )


def test_frozen_v3_preparation_matches_current_sources() -> None:
    payload = json.loads(v3.PREPARED.read_text(encoding="utf-8"))

    v3.verify_prepared(payload, qualifying_args())


def test_checkpoint_evidence_is_conjunctive() -> None:
    args = qualifying_args()
    args.minimum_worker_epochs = 1
    base = {
        "worker_epochs": [{"epoch": 0, "passed": True}],
        "criteria": {"base": True},
    }
    v3.CHECKPOINT_CYCLES[:] = [{
        "passed": True,
        "fully_quiescent": True,
        "post_close_wal_bytes": 0,
        "duration_seconds": 0.1,
    }]

    result = v3.attach_checkpoint_evidence(base, args)

    assert result["status"] == "PASS"
    assert all(result["criteria"].values())
    v3.CHECKPOINT_CYCLES[0]["post_close_wal_bytes"] = 32_769
    failed = v3.attach_checkpoint_evidence({
        "worker_epochs": [{"epoch": 0, "passed": True}],
        "criteria": {"base": True},
    }, args)
    assert failed["status"] == "FAIL"
    assert failed["criteria"]["all_checkpoint_wals_bounded"] is False


@pytest.mark.skipif(
    v3.v1.psutil is None,
    reason="psutil is required only for sustained evaluation",
)
def test_v3_multiprocess_checkpoint_backup_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "sustained-v3"
    monkeypatch.setattr(v3, "OUTPUT_DIR", output)
    monkeypatch.setattr(v3, "RUN_DATA", output / "run_data")
    monkeypatch.setattr(v3, "DATABASE", output / "run_data" / "sustained-v3.sqlite")
    monkeypatch.setattr(v3, "EVENTS", output / "events.jsonl")
    monkeypatch.setattr(v3, "RESULT", output / "RESULTS.json")
    args = argparse.Namespace(
        duration_seconds=6.0,
        writer_workers=2,
        reader_workers=2,
        tenants=4,
        seed_records=40,
        rotation_seconds=3.0,
        minimum_worker_epochs=2,
        backup_interval_seconds=2.0,
        writer_pause_timeout_seconds=10.0,
        backup_timeout_seconds=30.0,
        sample_interval_seconds=0.5,
        minimum_writes=10,
        minimum_reads=10,
        minimum_backup_cycles=3,
        minimum_resource_samples=6,
        maximum_rss_per_process_bytes=1_500_000_000,
        maximum_handles_per_process=1024,
        minimum_free_bytes=1_000_000,
        runtime_free_floor_bytes=1,
    )

    result = v3.run_soak(args)

    assert result["status"] == "PASS"
    assert len(result["checkpoint_cycles"]) == len(result["worker_epochs"])
    assert all(item["busy"] == 0 for item in result["checkpoint_cycles"])
    assert all(item["quick_check"] == "ok" for item in result["checkpoint_cycles"])
    assert result["criteria"]["all_checkpoint_wals_bounded"] is True
    text = v3.EVENTS.read_text(encoding="utf-8")
    assert '"checkpoint_after_stop"' in text
