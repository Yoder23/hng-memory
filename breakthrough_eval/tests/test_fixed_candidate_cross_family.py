from __future__ import annotations

import json

import pytest

from breakthrough_eval.scripts import fixed_candidate_cross_family as cross


def test_prepared_payload_reuses_exact_frozen_holdout_shape() -> None:
    payload = cross.prepared_payload(30)
    assert payload["sample_count"] == 30
    assert payload["systems"] == ["ordinary_rag", "strong_structured", "hng"]
    assert len({row["case_id"] for row in payload["cases"]}) == 30
    assert all(row["split"] == "holdout" for row in payload["cases"])
    assert all(len(row["candidate_pool_sha256"]) == 64 for row in payload["cases"])


def test_prepared_payload_exactly_matches_frozen_qwen_inputs() -> None:
    payload = cross.prepared_payload(cross.FIXED_CASES)
    event_path = cross.ROOT / "breakthrough_eval" / "fixed_candidate" / "raw" / "llm_events.jsonl"
    frozen = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]
    frozen_by_key = {(row["case_id"], row["system"]): row for row in frozen}
    assert len(frozen_by_key) == cross.FIXED_CASES * len(cross.SYSTEMS)
    for case in payload["cases"]:
        for system in cross.SYSTEMS:
            row = frozen_by_key[(case["case_id"], system)]
            assert row["candidate_ids"] == case["candidate_ids"]
            assert row["candidate_pool_sha256"] == case["candidate_pool_sha256"]
            assert row["memory_context_sha256"] == case["memory_context_sha256"][system]


def test_non_frozen_case_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="exactly 30"):
        cross.prepared_payload(29)


def test_prepare_is_byte_stable(tmp_path) -> None:
    first = cross.prepare(tmp_path, 30)
    before = (tmp_path / "PREPARED.json").read_bytes()
    second = cross.prepare(tmp_path, 30)
    assert first == second
    assert (tmp_path / "PREPARED.json").read_bytes() == before


def test_prepare_rejects_mutation(tmp_path) -> None:
    cross.prepare(tmp_path, 30)
    path = tmp_path / "PREPARED.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cases"][0]["case_id"] = "changed"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="changed"):
        cross.prepare(tmp_path, 30)


def test_existing_log_provenance_must_match(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    expected = {
        "protocol": cross.PROTOCOL,
        "model": cross.DEFAULT_MODEL,
        "model_digest": "digest-a",
        "preregistered_commit": "commit-a",
    }
    path.write_text(json.dumps(expected) + "\n", encoding="utf-8")
    cross.validate_existing_log(
        path, model=cross.DEFAULT_MODEL, model_digest="digest-a",
        preregistered_commit="commit-a",
    )
    with pytest.raises(RuntimeError, match="provenance mismatch"):
        cross.validate_existing_log(
            path, model=cross.DEFAULT_MODEL, model_digest="digest-b",
            preregistered_commit="commit-a",
        )


def test_completed_audit_requires_exact_prepared_inputs(tmp_path) -> None:
    prepared = cross.prepared_payload(cross.FIXED_CASES)
    rows = []
    for case in prepared["cases"]:
        for system in cross.SYSTEMS:
            rows.append({
                "status": "completed",
                "case_id": case["case_id"],
                "system": system,
                "candidate_ids": case["candidate_ids"],
                "candidate_pool_sha256": case["candidate_pool_sha256"],
                "memory_context_sha256": case["memory_context_sha256"][system],
                "outer_prompt_template_sha256": "frozen-prompt",
                "expected": next(
                    item.expected for item in cross.fixed.generate_scenarios()
                    if item.case_id == case["case_id"]
                ),
            })
    path = tmp_path / "events.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    assert cross.audit_completed(
        prepared, path, outer_prompt_template_sha256="frozen-prompt"
    )["all_fixed_candidate_invariants_pass"] is True
    rows[0]["candidate_pool_sha256"] = "changed"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    assert cross.audit_completed(
        prepared, path, outer_prompt_template_sha256="frozen-prompt"
    )["all_fixed_candidate_invariants_pass"] is False


def test_git_guard_allows_only_cross_family_runtime_outputs(monkeypatch) -> None:
    runtime = cross.DEFAULT_OUTPUT
    allowed = (
        "?? breakthrough_eval/fixed_candidate_cross_family/raw/llm_events.jsonl\n"
        "?? breakthrough_eval/fixed_candidate_cross_family/LLM_RESULTS.json\n"
    )
    monkeypatch.setattr(cross.subprocess, "check_output", lambda *_args, **_kwargs: allowed)
    assert cross.git_is_clean_except_runtime(runtime) is True
    changed_code = allowed + " M breakthrough_eval/scripts/fixed_candidate_cross_family.py\n"
    monkeypatch.setattr(cross.subprocess, "check_output", lambda *_args, **_kwargs: changed_code)
    assert cross.git_is_clean_except_runtime(runtime) is False


def test_reader_family_rejects_qwen_or_missing_metadata() -> None:
    assert cross.reader_family({"details": {"family": "mistral3"}}) == "mistral3"
    with pytest.raises(RuntimeError, match="not the preregistered Mistral"):
        cross.reader_family({"details": {"family": "qwen3"}})
    with pytest.raises(RuntimeError, match="not the preregistered Mistral"):
        cross.reader_family({})


def test_manifest_verification_fails_on_frozen_file_change(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cross, "ROOT", tmp_path)
    frozen = tmp_path / "frozen.txt"
    frozen.write_text("before", encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    manifest = {
        "status": "PREREGISTERED_SCORE_BLIND",
        "protocol": cross.PROTOCOL,
        "model": cross.DEFAULT_MODEL,
        "model_digest": "digest",
        "sample_count": cross.FIXED_CASES,
        "expected_events": cross.FIXED_CASES * len(cross.SYSTEMS),
        "frozen_files": {"frozen.txt": cross.file_sha256(frozen)},
    }
    (output / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    cross.verify_manifest(output, model=cross.DEFAULT_MODEL, model_digest="digest")
    frozen.write_text("after", encoding="utf-8")
    with pytest.raises(RuntimeError, match="file digest mismatch"):
        cross.verify_manifest(output, model=cross.DEFAULT_MODEL, model_digest="digest")


def test_qualification_is_immutable_and_failures_are_append_only(tmp_path, monkeypatch) -> None:
    existing = {
        "status": "QUALIFIED",
        "model": cross.DEFAULT_MODEL,
        "model_digest": "digest",
    }
    path = tmp_path / "MODEL_QUALIFICATION.json"
    path.write_text(json.dumps(existing), encoding="utf-8")
    monkeypatch.setattr(
        cross.fixed, "ollama_decide",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not rerun")),
    )
    assert cross.qualify_model(
        tmp_path, model=cross.DEFAULT_MODEL, model_digest="digest",
        endpoint="http://unused", timeout=1.0, installed={},
    ) == existing
    path.unlink()
    monkeypatch.setattr(
        cross.fixed, "ollama_decide",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("smoke failed")),
    )
    with pytest.raises(RuntimeError, match="smoke failed"):
        cross.qualify_model(
            tmp_path, model=cross.DEFAULT_MODEL, model_digest="digest",
            endpoint="http://unused", timeout=1.0, installed={},
        )
    failures = (tmp_path / "MODEL_QUALIFICATION_FAILURES.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(failures) == 1
    assert json.loads(failures[0])["status"] == "FAILED"
