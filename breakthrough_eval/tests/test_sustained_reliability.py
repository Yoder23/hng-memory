from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import pytest

from breakthrough_eval.scripts import sustained_reliability as sustained


def qualifying_args() -> argparse.Namespace:
    return argparse.Namespace(
        duration_seconds=7200.0,
        writer_workers=4,
        reader_workers=8,
        tenants=100,
        seed_records=1000,
        rotation_seconds=900.0,
        backup_interval_seconds=600.0,
        sample_interval_seconds=60.0,
        minimum_writes=100_000,
        minimum_reads=100_000,
        minimum_backup_cycles=12,
        minimum_resource_samples=100,
        maximum_rss_per_process_bytes=1_500_000_000,
        maximum_handles_per_process=1024,
        minimum_free_bytes=40_000_000_000,
    )


def test_preparation_freezes_two_hour_multiprocess_protocol() -> None:
    payload = sustained.prepared_payload(qualifying_args())

    assert payload["status"] == "PREPARED_NOT_EXECUTED"
    assert payload["config"]["duration_seconds"] == 7200.0
    assert payload["config"]["writer_workers"] == 4
    assert payload["config"]["reader_workers"] == 8
    assert payload["config"]["minimum_backup_cycles"] == 12
    assert payload["qualifying_command"][-1] == "COMMIT"
    assert set(payload["source_sha256"]) == {
        "breakthrough_eval/reliability/sustained_2h/PROTOCOL.md",
        "breakthrough_eval/scripts/sustained_reliability.py",
        "breakthrough_eval/scripts/storage_reliability_probe.py",
        (
            "baseline_source/hng-frontier-0.5.1a1/src/"
            "hngfrontier/storage_v2.py"
        ),
    }


def test_prepared_verifier_rejects_changed_duration() -> None:
    payload = sustained.prepared_payload(qualifying_args())
    changed = copy.deepcopy(payload)
    changed["config"]["duration_seconds"] = 7199.0

    with pytest.raises(RuntimeError, match="configuration mismatch"):
        sustained.verify_prepared(changed, qualifying_args())


def test_frozen_preparation_matches_current_sources() -> None:
    payload = json.loads(
        sustained.PREPARED.read_text(encoding="utf-8")
    )

    sustained.verify_prepared(payload, qualifying_args())


def test_interrupted_run_is_preserved_as_failure_not_result() -> None:
    interrupted = json.loads(
        (
            sustained.OUTPUT_DIR / "INTERRUPTED.json"
        ).read_text(encoding="utf-8")
    )
    events = sustained.EVENTS.read_bytes()

    assert interrupted["status"] == "INTERRUPTED_FAIL"
    assert interrupted["qualifying_result_exists"] is False
    assert interrupted["execution"]["result_json_written"] is False
    assert interrupted["failure"]["backup_completion_event_present"] is False
    assert interrupted["failure"]["rotation_event_present"] is False
    assert interrupted["unmet_frozen_criteria"]
    assert sustained.RESULT.exists() is False
    event_artifact = next(
        item for item in interrupted["preserved_artifacts"]
        if item["path"].endswith("events.jsonl")
    )
    assert event_artifact["sha256"] == sustained.hashlib.sha256(
        events
    ).hexdigest()


def test_latency_histograms_merge_without_retaining_samples() -> None:
    first = sustained.histogram()
    second = sustained.histogram()
    for value in (0.5, 3.0, 12.0):
        sustained.observe(first, value)
    for value in (1.5, 30.0):
        sustained.observe(second, value)

    summary = sustained.histogram_summary(
        sustained.merge_histograms((first, second))
    )

    assert summary["count"] == 5
    assert summary["p50_upper_bound_ms"] == 5.0
    assert summary["p95_upper_bound_ms"] == 50.0
    assert sum(summary["bucket_counts"]) == 5


def test_logical_digest_is_stable_across_backup(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    backup_path = tmp_path / "backup.sqlite"
    store = sustained.SQLiteEvidenceStore(source_path)
    try:
        for index in range(20):
            store.append(sustained.base_record(index, 2))
        destination = sustained.sqlite3.connect(backup_path)
        try:
            store.snapshot().backup(destination)
        finally:
            destination.close()
    finally:
        store.close()

    assert sustained.logical_digest(source_path) == sustained.logical_digest(
        backup_path
    )


@pytest.mark.skipif(
    sustained.psutil is None,
    reason="psutil is required only for the sustained evaluation",
)
def test_short_multiprocess_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "sustained"
    monkeypatch.setattr(sustained, "OUTPUT_DIR", output)
    monkeypatch.setattr(sustained, "RUN_DATA", output / "run_data")
    monkeypatch.setattr(
        sustained, "DATABASE", output / "run_data" / "sustained.sqlite"
    )
    monkeypatch.setattr(sustained, "EVENTS", output / "events.jsonl")
    monkeypatch.setattr(sustained, "RESULT", output / "RESULTS.json")
    args = argparse.Namespace(
        duration_seconds=8.0,
        writer_workers=4,
        reader_workers=4,
        tenants=4,
        seed_records=40,
        rotation_seconds=4.0,
        backup_interval_seconds=2.0,
        sample_interval_seconds=0.5,
        minimum_writes=10,
        minimum_reads=10,
        minimum_backup_cycles=4,
        minimum_resource_samples=8,
        maximum_rss_per_process_bytes=1_500_000_000,
        maximum_handles_per_process=1024,
        minimum_free_bytes=1,
    )

    result = sustained.run_soak(args)

    assert result["status"] == "PASS"
    assert result["writes"]["completed"] >= 10
    assert result["reads"]["completed"] >= 10
    assert len(result["backup_restore_cycles"]) >= 4
    assert all(item["passed"] for item in result["backup_restore_cycles"])
    assert result["final_live_logical"]["evidence_count"] == (
        result["expected_final_evidence_count"]
    )
