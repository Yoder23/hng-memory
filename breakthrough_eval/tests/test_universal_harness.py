from __future__ import annotations

import json

from breakthrough_eval.universal_harness import (
    BM25Adapter,
    Candidate,
    DenseAdapter,
    ExperimentSpec,
    FullContextAdapter,
    HybridAdapter,
    ModelResult,
    NoneAdapter,
    RecentContextAdapter,
    UniversalHarness,
)


def spec() -> ExperimentSpec:
    return ExperimentSpec(
        experiment_id="exp-1",
        case_id="case-1",
        evidence_class="synthetic",
        task={"query": "database timeout"},
        model_id="fixed-model",
        model_digest="sha256:model",
        prompt_template="TASK {task}\nMEMORY {memory_context}",
        state={"environment": "v2"},
        tools=("search",),
        data_revision="fixture-v1",
        seed=7,
        fixed_candidates=True,
    )


def candidates() -> tuple[Candidate, ...]:
    return (
        Candidate("a", "database timeout retry", "2026-01-01", dense_score=0.8),
        Candidate("b", "unrelated deployment", "2026-02-01", dense_score=0.2),
        Candidate("c", "database timeout backoff", "2026-03-01", dense_score=0.9),
    )


def test_retrieval_adapters_are_deterministic():
    experiment = spec()
    pool = candidates()
    assert RecentContextAdapter(2).prepare(experiment, pool).selected_ids == ("b", "c")
    assert BM25Adapter(2).prepare(experiment, pool).selected_ids == ("a", "c")
    assert DenseAdapter(2).prepare(experiment, pool).selected_ids == ("c", "a")
    first = HybridAdapter(2).prepare(experiment, pool)
    second = HybridAdapter(2).prepare(experiment, pool)
    assert first.selected_ids == second.selected_ids
    assert first.context == second.context


def test_harness_freezes_invariants_and_logs_standard_events(tmp_path):
    log = tmp_path / "events.jsonl"

    def runner(experiment, prompt):
        return ModelResult({"decision": "ok"}, 10, 2, 1.5, {"test": True})

    events = UniversalHarness(log, runner).run_case(
        spec(),
        candidates(),
        (NoneAdapter(), FullContextAdapter(), BM25Adapter(2)),
    )
    assert len(events) == 3
    assert len({event["candidate_pool_sha256"] for event in events}) == 1
    assert len({event["invariant_sha256"] for event in events}) == 1
    assert len({event["model_digest"] for event in events}) == 1
    assert len(log.read_text(encoding="utf-8").splitlines()) == 3
    assert all(json.loads(line)["schema_version"] == 1 for line in log.read_text().splitlines())


def test_dense_adapter_rejects_unfrozen_scores():
    pool = (Candidate("a", "text"),)
    try:
        DenseAdapter().prepare(spec(), pool)
    except ValueError as error:
        assert "frozen dense_score" in str(error)
    else:
        raise AssertionError("missing dense scores must not be silently generated")
