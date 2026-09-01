from __future__ import annotations

import hashlib

from breakthrough_eval.scripts import real_hdc_readiness as readiness


def test_missing_manifest_fails_closed():
    result = readiness.evaluate_manifest(None, manifest_path=None)
    assert result["status"] == "BLOCKED_EXTERNAL"
    assert result["failure_count"] > len(readiness.REQUIRED_ARTIFACTS)


def test_complete_hashed_contract_is_ready(tmp_path):
    artifacts = {}
    for name in readiness.REQUIRED_ARTIFACTS:
        path = tmp_path / f"{name}.artifact"
        path.write_text(name, encoding="utf-8")
        artifacts[name] = {
            "path": path.name,
            "sha256": hashlib.sha256(name.encode()).hexdigest(),
        }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    manifest = {
        "evidence_class": "real",
        "synthetic_artifacts": False,
        "artifacts": artifacts,
        "paired_invariants": {name: True for name in readiness.REQUIRED_INVARIANTS},
        "primary_metrics": ["task_success"],
        "minimum_sample_size": 100,
    }
    result = readiness.evaluate_manifest(manifest, manifest_path=manifest_path)
    assert result["status"] == "READY_FOR_PAIRED_EXECUTION"
    assert result["failure_count"] == 0


def test_digest_mismatch_blocks(tmp_path):
    artifacts = {}
    for name in readiness.REQUIRED_ARTIFACTS:
        path = tmp_path / name
        path.write_text(name, encoding="utf-8")
        artifacts[name] = {"path": path.name, "sha256": "0" * 64}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    result = readiness.evaluate_manifest({
        "evidence_class": "real",
        "synthetic_artifacts": False,
        "artifacts": artifacts,
        "paired_invariants": {name: True for name in readiness.REQUIRED_INVARIANTS},
        "primary_metrics": ["task_success"],
        "minimum_sample_size": 1,
    }, manifest_path=manifest_path)
    assert result["status"] == "BLOCKED_EXTERNAL"
    assert any(item["code"].startswith("digest_mismatch_") for item in result["failures"])
