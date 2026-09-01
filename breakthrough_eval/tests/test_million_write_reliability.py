from __future__ import annotations

import argparse
import copy
import json

import pytest

from breakthrough_eval.scripts import million_write_reliability as million


def args() -> argparse.Namespace:
    return argparse.Namespace(
        records=1_000_000,
        tenants=100,
        restart_every=100_000,
        lifecycle_records=100,
        minimum_free_bytes=8_000_000_000,
    )


def test_preparation_freezes_full_qualifying_configuration() -> None:
    payload = million.prepared_payload(args())

    assert payload["status"] == "PREPARED_NOT_EXECUTED"
    assert payload["config"]["records"] == 1_000_000
    assert payload["config"]["tenants"] == 100
    assert payload["qualifying_command"][-1] == "COMMIT"
    assert set(payload["source_sha256"]) == {
        "breakthrough_eval/reliability/million_write/PROTOCOL.md",
        "breakthrough_eval/scripts/million_write_reliability.py",
        "breakthrough_eval/scripts/storage_reliability_probe.py",
        "baseline_source/hng-frontier-0.5.1a1/src/hngfrontier/storage_v2.py",
    }


def test_prepared_verifier_rejects_configuration_change() -> None:
    payload = million.prepared_payload(args())
    changed = copy.deepcopy(payload)
    changed["config"]["records"] = 999_999

    with pytest.raises(RuntimeError, match="configuration mismatch"):
        million.verify_prepared(changed, args())


def test_frozen_preparation_matches_current_sources() -> None:
    payload = json.loads(million.PREPARED.read_text(encoding="utf-8"))

    million.verify_prepared(payload, args())


def test_sha256_file_is_content_addressed(tmp_path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"hng-frontier")

    assert million.sha256_file(path) == "89b8d3166c5aa0dc573621c5143b3042974695f7d9b5c7d51baac54d6c357340"
