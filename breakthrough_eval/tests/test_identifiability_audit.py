from __future__ import annotations

import json
from pathlib import Path

from breakthrough_eval.scripts.identifiability_audit import audit_study


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_exact_prompt_reuse_is_not_identifiable(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_rows(path, [
        {"sample_id": "a", "arm": "strong", "prompt_sha256": "same", "prediction": "x"},
        {"sample_id": "a", "arm": "hng", "prompt_sha256": "same", "prediction": "x", "evaluation_reused": True},
    ])

    result = audit_study("fixture", path)

    assert result["paired_units"] == 1
    assert result["exact_prompt_reuse_for_all_pairs"] is True
    assert result["hng_effect_identifiable_from_reader_outputs"] is False


def test_distinct_memory_context_is_identifiable(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_rows(path, [
        {"case_id": "a", "system": "strong_structured", "memory_context_sha256": "left"},
        {"case_id": "a", "system": "hng", "memory_context_sha256": "right"},
    ])

    result = audit_study("fixture", path)

    assert result["paired_units"] == 1
    assert result["hng_effect_identifiable_from_reader_outputs"] is True
    assert result["comparisons"]["memory_context_sha256"] == {"different": 1}


def test_policy_decision_difference_is_counted(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_rows(path, [
        {"case_id": "a", "system": "strong_structured", "observed": "support"},
        {"case_id": "a", "system": "hng", "observed": "challenge"},
    ])

    result = audit_study("fixture", path)

    assert result["policy_decision_distinguishing_units"] == 1
