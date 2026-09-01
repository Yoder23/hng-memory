from __future__ import annotations

import json

import pytest

from breakthrough_eval.scripts import locomo_plus_pilot as pilot
from breakthrough_eval.scripts import locomo_reranker_holdout as reranker


def candidate(name: str) -> pilot.Candidate:
    return pilot.Candidate(name, name, "trajectory", 0, name)


class FakeReranker:
    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [self.scores[document] for _query, document in pairs]


def test_protocol_arms_include_real_reranker_and_governance_controls() -> None:
    assert reranker.ARMS == (
        "full_context",
        "bm25_k64",
        "dense_k64",
        "hybrid_k64",
        "reranked_k64",
        "strong_reranked_k64",
        "hng_reranked_k64",
    )


def test_rerank_union_is_deterministic_and_uses_both_first_stages() -> None:
    rows = [candidate("a"), candidate("b"), candidate("c"), candidate("d")]
    first_stage, ranked = reranker.rerank_union(
        rows,
        [rows[0], rows[1], rows[2], rows[3]],
        [rows[3], rows[2], rows[1], rows[0]],
        "query",
        FakeReranker({"a": 0.1, "b": 0.8, "c": 0.8, "d": 0.2}),
        first_stage_k=2,
    )
    assert [row.candidate_id for row in first_stage] == ["a", "b", "c", "d"]
    assert [row.candidate_id for row in ranked] == ["b", "c", "d", "a"]


def test_rerank_union_rejects_score_count_mismatch() -> None:
    class Broken:
        def score(self, _pairs):
            return []

    rows = [candidate("a")]
    with pytest.raises(RuntimeError, match="score count"):
        reranker.rerank_union(rows, rows, rows, "query", Broken())


def test_completed_keys_rejects_wrong_hng_identity(tmp_path) -> None:
    raw = tmp_path / "events.jsonl"
    invalid = {
        "event": "prediction",
        "source_index": 1,
        "arm": "hng_reranked_k64",
        "source_identity": "wrong",
    }
    valid = {
        "event": "prediction",
        "source_index": 2,
        "arm": "hng_reranked_k64",
        "source_identity": "LoCoMo-Plus",
    }
    raw.write_text(json.dumps(invalid) + "\n" + json.dumps(valid) + "\n", encoding="utf-8")
    assert reranker.completed_keys(raw) == {(2, "hng_reranked_k64")}


def test_frozen_model_and_window_parameters() -> None:
    assert reranker.FIRST_STAGE_K == 128
    assert reranker.TOP_K == 64
    assert reranker.DEFAULT_RERANKER_REVISION == (
        "e61197ed45024b0ed8a2d74b80b4d909f1255473"
    )
    assert reranker.DEFAULT_RERANKER_DIGEST == (
        "27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b"
    )

