from __future__ import annotations

from collections import Counter
import json

import pytest

from breakthrough_eval.scripts import fixed_candidate_cross_reader_holdout as holdout


def test_selection_is_disjoint_balanced_and_untouched() -> None:
    selected = holdout.selected_scenarios()
    assert len(selected) == holdout.FIXED_CASES
    assert len({item.case_id for item in selected}) == holdout.FIXED_CASES
    assert Counter(item.family for item in selected) == {family: 3 for family in {
        "duplicate_attack", "stale_environment", "wrong_tenant", "wrong_role",
        "untrusted_poison", "superseded", "true_conflict", "irrelevant_state",
        "sparse_verified", "authority_mismatch",
    }}
    assert {int(item.case_id.rsplit("-", 1)[1]) for item in selected} == {8, 9, 10}


def test_each_reader_uses_all_six_orders_exactly_five_times() -> None:
    selected = holdout.selected_scenarios()
    for reader in holdout.READERS:
        orders = holdout.counterbalanced_orders(selected, reader)
        assert set(orders.values()) == set(holdout.PERMUTATIONS)
        assert set(Counter(orders.values()).values()) == {5}


def test_prepared_payload_has_180_events_and_fixed_inputs() -> None:
    payload = holdout.prepared_payload()
    assert payload["sample_count"] == 30
    assert payload["expected_events"] == 180
    assert all(len(row["candidate_pool_sha256"]) == 64 for row in payload["cases"])
    assert all(set(row["system_order"]) == set(holdout.READERS) for row in payload["cases"])


def test_prepare_is_immutable(tmp_path) -> None:
    first = holdout.prepare(tmp_path)
    before = (tmp_path / "PREPARED.json").read_bytes()
    assert holdout.prepare(tmp_path) == first
    assert (tmp_path / "PREPARED.json").read_bytes() == before
    changed = dict(first)
    changed["sample_count"] = 29
    (tmp_path / "PREPARED.json").write_text(__import__("json").dumps(changed), encoding="utf-8")
    with pytest.raises(RuntimeError, match="changed"):
        holdout.prepare(tmp_path)


def test_joint_comparison_threshold_is_fail_closed() -> None:
    passing = {
        "paired_bootstrap_accuracy": {"delta": 0.2, "ci95_low": 0.01, "ci95_high": 0.4},
        "mcnemar": {"exact_two_sided_p": 0.024},
    }
    assert holdout.comparison_pass(passing) is True
    for key, value in (("delta", 0.0), ("ci95_low", 0.0)):
        changed = json.loads(json.dumps(passing))
        changed["paired_bootstrap_accuracy"][key] = value
        assert holdout.comparison_pass(changed) is False
    changed = json.loads(json.dumps(passing))
    changed["mcnemar"]["exact_two_sided_p"] = 0.025
    assert holdout.comparison_pass(changed) is False


def test_180_event_audit_rejects_order_mutation(tmp_path) -> None:
    prepared = holdout.prepared_payload()
    expected_by_case = {item.case_id: item.expected for item in holdout.selected_scenarios()}
    for reader, spec in holdout.READERS.items():
        rows = []
        for case in prepared["cases"]:
            order = case["system_order"][reader]
            for system in order:
                rows.append({
                    "status": "completed", "case_id": case["case_id"], "system": system,
                    "candidate_ids": case["candidate_ids"],
                    "candidate_pool_sha256": case["candidate_pool_sha256"],
                    "memory_context_sha256": case["memory_context_sha256"][system],
                    "expected": expected_by_case[case["case_id"]],
                    "system_order": order, "execution_order_index": order.index(system),
                    "model": spec["model"], "model_digest": spec["digest"],
                    "protocol": holdout.PROTOCOL, "preregistered_commit": "commit",
                    "outer_prompt_template_sha256": "outer",
                })
        path = tmp_path / "readers" / reader / "raw" / "llm_events.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    audit = holdout.audit_events(
        prepared, tmp_path, preregistered_commit="commit",
        outer_prompt_template_sha256="outer",
    )
    assert audit["all_invariants_pass"] is True
    path = tmp_path / "readers" / "qwen" / "raw" / "llm_events.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["execution_order_index"] = 99
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    assert holdout.audit_events(
        prepared, tmp_path, preregistered_commit="commit",
        outer_prompt_template_sha256="outer",
    )["all_invariants_pass"] is False
