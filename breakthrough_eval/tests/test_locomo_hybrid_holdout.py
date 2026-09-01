from __future__ import annotations

import json

from breakthrough_eval.scripts import locomo_hybrid_holdout as hybrid
from breakthrough_eval.scripts import locomo_plus_pilot as pilot


def candidate(name: str) -> pilot.Candidate:
    return pilot.Candidate(name, name, "trajectory", 0, name)


def test_cosine_known_values():
    assert hybrid.cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert hybrid.cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_dense_rank_is_deterministic():
    rows = [candidate("a"), candidate("b"), candidate("c")]
    ranked = hybrid.rank_dense(rows, [1.0, 0.0], [[0.0, 1.0], [1.0, 0.0], [1.0, 0.0]])
    assert [row.candidate_id for row in ranked] == ["b", "c", "a"]


def test_rrf_rewards_cross_ranking_consensus():
    rows = [candidate("a"), candidate("b"), candidate("c")]
    ranked = hybrid.reciprocal_rank_fusion(rows, [rows[0], rows[1], rows[2]], [rows[1], rows[0], rows[2]])
    assert [row.candidate_id for row in ranked] == ["a", "b", "c"]
    assert ranked[0].bm25_score == ranked[1].bm25_score


def test_query_instruction_is_fixed():
    assert hybrid.query_text("question").endswith("Query: question")
    assert "Retrieve prior dialogue turns" in hybrid.query_text("question")


def test_completed_keys_rejects_wrong_hng_identity(tmp_path):
    raw = tmp_path / "events.jsonl"
    invalid = {"event": "prediction", "source_index": 1, "arm": "hng_hybrid_k64", "source_identity": "wrong"}
    valid = {"event": "prediction", "source_index": 2, "arm": "hng_hybrid_k64", "source_identity": "LoCoMo-Plus"}
    raw.write_text(json.dumps(invalid) + "\n" + json.dumps(valid) + "\n", encoding="utf-8")
    assert hybrid.completed_keys(raw) == {(2, "hng_hybrid_k64")}
