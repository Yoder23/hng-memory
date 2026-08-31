from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from hngfrontier import (
    AssistantMemory, CallableAssistantAdapter, ShadowEvaluator,
    WorkingItemSpec, WorkingUpdate,
)


def hv(seed: int, dim: int = 2048) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.choice(np.array([-1, 1], dtype=np.int8), size=dim)


def noisy(v: np.ndarray, frac: float, seed: int) -> np.ndarray:
    out = v.copy()
    rng = np.random.default_rng(seed)
    n = int(round(out.size * frac))
    idx = rng.choice(out.size, size=n, replace=False)
    out[idx] *= -1
    return out


def heads(seed: int, dim: int = 2048):
    return {
        "state": hv(seed + 1, dim),
        "goal": hv(seed + 2, dim),
        "entity": hv(seed + 3, dim),
        "sequence": hv(seed + 4, dim),
        "action": hv(seed + 5, dim),
        "outcome": hv(seed + 6, dim),
        "next_state": hv(seed + 7, dim),
    }


def test_transition_working_state_and_restart(tmp_path: Path):
    root = tmp_path / "mem"
    h1 = heads(100)
    h2 = heads(200)
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False) as mem:
        r1 = mem.record_transition(
            h1, "Redis memory spikes during ingestion", conversation_id=7, episode_id=11,
            action="inspect ingestion workers", outcome="workers correlate with pressure", outcome_score=0.5,
            working_update=WorkingUpdate(
                set_goal="diagnose latency",
                add=(
                    WorkingItemSpec("open_loop", "logs", "inspect worker logs"),
                    WorkingItemSpec("fact", "deploy_day", "Tuesday"),
                    WorkingItemSpec("entity", "redis", "Redis service"),
                ),
            ),
        )
        assert r1.before.turn_index == 0
        assert r1.after.turn_index == 1
        assert r1.after.goal == "diagnose latency"
        assert {x.key for x in r1.after.open_loops} == {"logs"}

        r2 = mem.record_transition(
            h2, "Actually deployment is Thursday; logs are attached", conversation_id=7, episode_id=11,
            action="inspect logs", outcome="allocator pressure confirmed", outcome_score=1.0,
            working_update=WorkingUpdate(
                resolve=("logs",),
                supersede=(WorkingItemSpec("fact", "deploy_day", "Thursday"),),
                add=(WorkingItemSpec("constraint", "avoid_restart", "Do not restart during ingestion"),),
            ),
        )
        assert r2.after.turn_index == 2
        assert not r2.after.open_loops
        assert r2.after.facts[0].value == "Thursday"
        assert r2.after.corrections[-1].old_value == "Tuesday"
        assert r2.after.corrections[-1].new_value == "Thursday"
        rels = mem.memory.db.outgoing(r2.slot, "FOLLOWS")
        assert len(rels) == 1 and rels[0][1].slot == r1.slot

    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False) as mem:
        state = mem.working_state(7)
        assert state.turn_index == 2
        assert state.goal == "diagnose latency"
        assert state.facts[0].value == "Thursday"
        assert state.constraints[0].key == "avoid_restart"
        assert state.corrections[-1].old_value == "Tuesday"


def test_immediate_context_does_not_depend_on_semantic_recall(tmp_path: Path):
    root = tmp_path / "mem"
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False, recent_limit=3) as mem:
        for i in range(4):
            mem.record_transition(
                heads(1000 + i * 20), f"turn-{i}", conversation_id=9, episode_id=20,
                working_update=WorkingUpdate(set_goal="same active goal" if i == 0 else None),
            )
        # Query intentionally unrelated to every stored vector.
        frame = mem.prepare_context({"state": hv(99999)}, conversation_id=9, top_k=2)
        assert [x.source for x in frame.immediate_context] == ["turn-1", "turn-2", "turn-3"]
        assert frame.working_state.goal == "same active goal"


def test_stale_index_fresh_transition_is_visible(tmp_path: Path):
    root = tmp_path / "mem"
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False,
                         index_options={"table_count": 12, "bits_per_table": 10, "sketch_bits": 128}) as mem:
        first = heads(100)
        mem.record_transition(first, "old", conversation_id=1, episode_id=1)
        mem.rebuild_index()
        fresh = heads(500)
        slot = mem.record_transition(fresh, "fresh", conversation_id=1, episode_id=2).slot
        frame = mem.prepare_context({"state": fresh["state"]}, conversation_id=1, top_k=1)
        assert frame.provenance[0].slot == slot
        assert frame.provenance[0].score > 0.99


def test_transition_recall_and_action_gate(tmp_path: Path):
    root = tmp_path / "mem"
    base = heads(1000)
    bad = base["action"]
    good = hv(7777, 2048)
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False,
                         index_options={"table_count": 16, "bits_per_table": 10, "sketch_bits": 128}) as mem:
        # Same context + bad action failed twice.
        for e in (1, 2):
            mem.record_transition(
                base, f"incident bad {e}", conversation_id=e, episode_id=e,
                action="restart database", outcome="caused outage", outcome_score=-1.0,
            )
        # Same context + good action succeeded twice.
        for e in (3, 4):
            h = dict(base); h["action"] = good; h["outcome"] = hv(9000 + e, 2048)
            mem.record_transition(
                h, f"incident good {e}", conversation_id=e, episode_id=e,
                action="reduce worker concurrency", outcome="recovered", outcome_score=1.0,
            )
        mem.rebuild_index()
        context = {k: noisy(base[k], 0.02, 50 + i) for i, k in enumerate(("state", "goal", "entity", "sequence"))}
        gate = mem.evaluate_action(
            context, noisy(bad, 0.02, 99), conversation_id=99,
            semantic_floor=0.80, minimum_evidence=0.5, top_k=8,
        )
        assert gate.assessment.decision == "challenge"
        assert gate.assessment.contradiction_weight > gate.assessment.support_weight
        assert gate.frame.decision == "challenge"
        assert gate.frame.contradicting_evidence

        tr = mem.recall_transitions(context, proposed_action=noisy(good, 0.02, 88), conversation_id=99,
                                    semantic_floor=0.80, top_k=4)
        assert any(x.outcome == "recovered" for x in tr.supporting_evidence)


def test_insufficient_evidence_fails_closed(tmp_path: Path):
    root = tmp_path / "mem"
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False,
                         index_options={"table_count": 8, "bits_per_table": 8, "sketch_bits": 64}) as mem:
        mem.record_transition(heads(100), "known", conversation_id=1, episode_id=1,
                              action="known action", outcome="worked", outcome_score=1.0)
        mem.rebuild_index()
        unrelated = {k: hv(9000 + i, 2048) for i, k in enumerate(("state", "goal", "entity", "sequence"))}
        result = mem.evaluate_action(unrelated, hv(9999, 2048), conversation_id=2,
                                     semantic_floor=0.90, minimum_evidence=0.5)
        assert result.assessment.decision == "insufficient_evidence"
        assert result.assessment.evidence_count == 0
        assert result.frame.decision == "insufficient_evidence"


def test_adapter_receives_deterministic_working_state(tmp_path: Path):
    root = tmp_path / "mem"
    seen = {}
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False) as mem:
        mem.record_transition(
            heads(100), "first", conversation_id=3, episode_id=3,
            working_update=WorkingUpdate(set_goal="ship feature", add=(WorkingItemSpec("open_loop", "review", "review code"),)),
        )
        def encode(value, *, context):
            seen["goal"] = context.working_state.goal
            seen["loops"] = tuple(x.key for x in context.working_state.open_loops)
            seen["state_matches_next"] = bool(np.array_equal(context.semantic_heads["state"], heads(100)["next_state"]))
            return {"state": hv(555, 2048)}
        adapter = CallableAssistantAdapter(encode)
        out = mem.encode_query(adapter, "that", conversation_id=3)
        assert set(out) == {"state"}
        assert seen == {"goal": "ship feature", "loops": ("review",), "state_matches_next": True}


def test_shadow_logging_is_non_mutating(tmp_path: Path):
    root = tmp_path / "mem"
    log = tmp_path / "shadow.jsonl"
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False) as mem:
        h = heads(100)
        mem.record_transition(h, "known", conversation_id=1, episode_id=1,
                              action="bad", outcome="failed", outcome_score=-1.0)
        mem.rebuild_index()
        before = mem.memory.db.committed_count
        result = mem.evaluate_action({k: h[k] for k in ("state", "goal", "entity", "sequence")}, h["action"],
                                     conversation_id=2, semantic_floor=0.8, minimum_evidence=0.5)
        ShadowEvaluator(log).log_action(result, proposed_action="bad", baseline={"live_action": "bad"})
        after = mem.memory.db.committed_count
        assert before == after
    row = json.loads(log.read_text().strip())
    assert row["kind"] == "action_gate"
    assert row["baseline"]["live_action"] == "bad"


def test_current_semantic_state_survives_restart(tmp_path: Path):
    root = tmp_path / "mem"
    h = heads(321)
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False) as mem:
        mem.record_transition(h, "turn", conversation_id=44, episode_id=2)
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False) as mem:
        current = mem.current_semantic_heads(44)
        assert np.array_equal(current["state"], h["next_state"])
        assert np.array_equal(current["goal"], h["goal"])
        assert np.array_equal(current["entity"], h["entity"])


def test_failed_vector_write_does_not_advance_working_state(tmp_path: Path, monkeypatch):
    root = tmp_path / "mem"
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False) as mem:
        mem.record_transition(heads(1), "ok", conversation_id=8, episode_id=1,
                              working_update=WorkingUpdate(set_goal="stable"))
        before_count = mem.memory.db.committed_count
        before = mem.working_state(8)
        original = mem.memory.vector_stores["goal"].write_slot
        def boom(*args, **kwargs):
            raise OSError("simulated vector failure")
        monkeypatch.setattr(mem.memory.vector_stores["goal"], "write_slot", boom)
        try:
            try:
                mem.record_transition(heads(2), "fail", conversation_id=8, episode_id=1,
                                      working_update=WorkingUpdate(set_goal="wrong"))
                assert False, "expected failure"
            except OSError:
                pass
        finally:
            monkeypatch.setattr(mem.memory.vector_stores["goal"], "write_slot", original)
        assert mem.memory.db.committed_count == before_count
        after = mem.working_state(8)
        assert after.goal == before.goal == "stable"
        assert after.turn_index == before.turn_index


def test_readiness_evaluator_scores_behavior(tmp_path: Path):
    from hngfrontier import AssistantReadinessEvaluator, ContinuityExpectation, ContextExpectation
    root = tmp_path / "mem"
    h = heads(500)
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False,
                         index_options={"table_count": 12, "bits_per_table": 10, "sketch_bits": 128}) as mem:
        mem.record_transition(h, "history", conversation_id=1, episode_id=55,
                              working_update=WorkingUpdate(set_goal="remember this"))
        mem.rebuild_index()
        report = AssistantReadinessEvaluator(mem).run(
            continuity=(ContinuityExpectation("state", 1, expected_goal="remember this"),),
            contexts=(ContextExpectation("recall", 99, {"state": h["state"]}, 55),),
        )
        assert report.total == 2 and report.passed == 2 and report.pass_rate == 1.0


def test_shadow_summary_supports_labeled_replay(tmp_path: Path):
    log = tmp_path / "shadow.jsonl"
    shadow = ShadowEvaluator(log)
    # Directly exercise the append-only evaluation surface with a real gate result.
    root = tmp_path / "mem"
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False) as mem:
        h = heads(1234)
        mem.record_transition(h, "bad precedent", conversation_id=1, episode_id=1,
                              action="bad", outcome="failed", outcome_score=-1.0)
        mem.rebuild_index()
        result = mem.evaluate_action({k:h[k] for k in ("state","goal","entity","sequence")}, h["action"],
                                     conversation_id=2, minimum_evidence=0.5, semantic_floor=0.8)
        shadow.log_action(result, proposed_action="bad", baseline={"expected_decision":"challenge"})
    summary = shadow.summarize()
    assert summary["records"] == 1 and summary["actions"] == 1
    assert summary["decisions"]["challenge"] == 1
    assert summary["labeled_accuracy"] == 1.0


def _run_crash_child(root: str, mode: str):
    import os
    from hngfrontier import AssistantMemory, WorkingUpdate
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False) as mem:
        if mode == "before_commit":
            def die(*args, **kwargs):
                os._exit(71)
            mem.memory.db.commit_memory = die
        elif mode == "after_commit":
            def die_after(*args, **kwargs):
                os._exit(72)
            mem.working.advance_committed = die_after
        mem.record_transition(heads(700), "crash", conversation_id=71, episode_id=71,
                              working_update=WorkingUpdate(set_goal="survive"))


def test_process_crash_before_commit_leaves_no_memory(tmp_path: Path):
    import multiprocessing as mp
    root = str(tmp_path / "mem")
    p = mp.get_context("spawn").Process(target=_run_crash_child, args=(root, "before_commit"))
    p.start(); p.join(10)
    assert p.exitcode == 71
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False) as mem:
        assert mem.memory.db.committed_count == 0
        assert mem.working_state(71).turn_index == 0
        # The prewritten vector row is outside the committed prefix and can be overwritten safely.
        r = mem.record_transition(heads(701), "retry", conversation_id=71, episode_id=71,
                                  working_update=WorkingUpdate(set_goal="survive"))
        assert r.slot == 0 and r.after.turn_index == 1


def test_process_crash_after_commit_rebuilds_working_state(tmp_path: Path):
    import multiprocessing as mp
    root = str(tmp_path / "mem")
    p = mp.get_context("spawn").Process(target=_run_crash_child, args=(root, "after_commit"))
    p.start(); p.join(10)
    assert p.exitcode == 72
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False) as mem:
        assert mem.memory.db.committed_count == 1
        state = mem.working_state(71)
        assert state.turn_index == 1 and state.goal == "survive"


def test_memory_guided_action_narrowing(tmp_path: Path):
    root = tmp_path / "mem"
    base = heads(8800)
    good = base["action"]
    bad = hv(9900, 2048)
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False,
                         index_options={"table_count": 12, "bits_per_table": 10, "sketch_bits": 128}) as mem:
        for i in range(4):
            h = dict(base); h["action"] = good
            mem.record_transition(h, f"good {i}", conversation_id=100+i, episode_id=200+i,
                                  action="action-good", outcome="worked", outcome_score=1.0)
        for i in range(4):
            h = dict(base); h["action"] = bad
            mem.record_transition(h, f"bad {i}", conversation_id=300+i, episode_id=400+i,
                                  action="action-bad", outcome="failed", outcome_score=-1.0)
        mem.rebuild_index()
        context = {k: noisy(base[k], 0.02, 12000+i) for i, k in enumerate(("state","goal","entity","sequence"))}
        recs = mem.recommend_actions(context, conversation_id=999, max_actions=4, semantic_floor=0.80)
        assert recs
        assert recs[0].label == "action-good"
        assert recs[0].support_weight > 0 and recs[0].contradiction_weight == 0
        bad_row = next(x for x in recs if x.label == "action-bad")
        assert bad_row.evidence_score < 0


def test_episode_reconstruction_is_scoped_to_conversation(tmp_path: Path):
    root = tmp_path / "mem"
    with AssistantMemory(root, hv_dim=2048, space_id="test", auto_index=False,
                         index_options={"table_count": 12, "bits_per_table": 10, "sketch_bits": 128}) as mem:
        h1 = heads(15000); h2 = heads(25000)
        # Both chats intentionally reuse local episode_id=1.
        mem.record_transition(h1, "chat-A-only", conversation_id=101, episode_id=1)
        mem.record_transition(h2, "chat-B-only", conversation_id=202, episode_id=1)
        mem.rebuild_index()
        frame = mem.prepare_context({"state": h1["state"]}, conversation_id=999, top_k=1)
        assert frame.recalled_episodes
        sources = [r.source for r in frame.recalled_episodes[0].records]
        assert sources == ["chat-A-only"]


def test_action_floor_separates_close_action_variants(tmp_path: Path):
    dim = 2048
    rng = np.random.default_rng(4242)
    context = {h: rng.integers(0, 2, size=dim, dtype=np.uint8) for h in ("state","goal","entity","sequence")}
    base_action = rng.integers(0, 2, size=dim, dtype=np.uint8)
    close_action = base_action.copy()
    close_action[rng.choice(dim, size=int(dim*0.05), replace=False)] ^= 1
    root = tmp_path / "mem"
    with AssistantMemory(root, hv_dim=dim, space_id="test", auto_index=False,
                         index_options={"table_count":12,"bits_per_table":10,"sketch_bits":128}) as mem:
        for i in range(3):
            mem.record_transition({**context,"action":base_action}, "good", conversation_id=10+i, episode_id=1,
                                  action="good", outcome="worked", outcome_score=1.0)
            mem.record_transition({**context,"action":close_action}, "bad", conversation_id=20+i, episode_id=1,
                                  action="bad", outcome="failed", outcome_score=-1.0)
        mem.rebuild_index()
        # A loose action floor mixes the two deliberately-close variants; the strict floor
        # makes the proposed action an identity-like evidence constraint.
        bad = mem.evaluate_action(context, close_action, conversation_id=99, semantic_floor=0.80,
                                  action_floor=0.97, minimum_evidence=0.5)
        good = mem.evaluate_action(context, base_action, conversation_id=99, semantic_floor=0.80,
                                   action_floor=0.97, minimum_evidence=0.5)
        assert bad.assessment.decision == "challenge"
        assert good.assessment.decision == "support"


def test_action_gate_reports_conflicted_when_outcomes_balance(tmp_path: Path):
    dim = 2048
    rng = np.random.default_rng(5151)
    context = {h: rng.integers(0, 2, size=dim, dtype=np.uint8) for h in ("state","goal","entity","sequence")}
    action = rng.integers(0, 2, size=dim, dtype=np.uint8)
    root = tmp_path / "mem"
    with AssistantMemory(root, hv_dim=dim, space_id="test", auto_index=False,
                         index_options={"table_count":12,"bits_per_table":10,"sketch_bits":128}) as mem:
        for i in range(3):
            mem.record_transition({**context,"action":action}, "worked", conversation_id=10+i, episode_id=1,
                                  action="same", outcome="success", outcome_score=1.0)
            mem.record_transition({**context,"action":action}, "failed", conversation_id=20+i, episode_id=1,
                                  action="same", outcome="failure", outcome_score=-1.0)
        mem.rebuild_index()
        r = mem.evaluate_action(context, action, conversation_id=99, semantic_floor=0.80,
                                action_floor=0.97, minimum_evidence=0.5,
                                challenge_below=-0.2, support_above=0.2)
        assert r.assessment.decision == "conflicted"
        assert r.assessment.support_weight > 0 and r.assessment.contradiction_weight > 0
