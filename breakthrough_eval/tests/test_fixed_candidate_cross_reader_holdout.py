from __future__ import annotations

from collections import Counter

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
