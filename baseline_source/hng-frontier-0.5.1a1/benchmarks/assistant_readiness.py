from __future__ import annotations

import json
from pathlib import Path
import shutil
import statistics
import time

import numpy as np

from hngfrontier import AssistantMemory, MemoryFilter, WorkingItemSpec, WorkingUpdate

DIM = 4096
HISTORY = 256
LIVE = 128


def hv(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.choice(np.array([-1, 1], dtype=np.int8), size=DIM)


def noise(v: np.ndarray, frac: float, seed: int) -> np.ndarray:
    out = v.copy(); rng = np.random.default_rng(seed)
    idx = rng.choice(out.size, size=int(out.size * frac), replace=False)
    out[idx] *= -1
    return out


def semantic_bundle(seed: int):
    return {
        "state": hv(seed + 1), "goal": hv(seed + 2), "entity": hv(seed + 3),
        "sequence": hv(seed + 4), "action": hv(seed + 5), "outcome": hv(seed + 6),
        "next_state": hv(seed + 7),
    }


def main():
    root = Path('/mnt/data/hng_frontier_03_bench')
    shutil.rmtree(root, ignore_errors=True)
    index_opts = {"table_count": 24, "bits_per_table": 12, "sketch_bits": 256}
    topics = [semantic_bundle(10000 + i * 20) for i in range(HISTORY)]

    with AssistantMemory(root, hv_dim=DIM, space_id='assistant-readiness-v1', auto_index=False,
                         recent_limit=6, index_options=index_opts) as mem:
        t0 = time.perf_counter()
        for i, h in enumerate(topics):
            mem.record_transition(
                h, f"historical incident {i}", conversation_id=1000+i, episode_id=5000+i,
                action=f"action-{i}", outcome=f"resolved-{i}", outcome_score=1.0,
                namespace='history',
            )
        ingest_history_s = time.perf_counter() - t0
        t0 = time.perf_counter(); mem.rebuild_index(); index_s = time.perf_counter() - t0

        # Create live conversations whose first turn establishes HDC state. The second turn is
        # an ambiguous cue; the old retrieval-only baseline gets only a generic cue vector,
        # while the AssistantMemory bridge exposes the prior committed HDC state directly.
        targets = np.arange(LIVE) * (HISTORY // LIVE)
        for j, idx in enumerate(targets):
            h = topics[int(idx)]
            live_heads = dict(h)
            live_heads["next_state"] = noise(h["state"], 0.02, 70000+j)
            mem.record_transition(
                live_heads, f"live turn establishes topic {idx}", conversation_id=90000+j, episode_id=80000+j,
                namespace='live',
                working_update=WorkingUpdate(
                    set_goal=f"resolve topic {idx}",
                    add=(WorkingItemSpec('open_loop', 'followup', f"investigate topic {idx}"),),
                ),
            )

        generic = hv(999999)
        baseline_ok = 0; frontier_ok = 0
        baseline_ms = []; frontier_ms = []
        history_filter = MemoryFilter(namespace='history')
        for j, idx in enumerate(targets):
            expected_episode = 5000 + int(idx)
            t0 = time.perf_counter()
            raw = mem.memory.recall({"state": generic}, top_k=1, memory_filter=history_filter)
            baseline_ms.append((time.perf_counter()-t0)*1000)
            if raw.hits and raw.hits[0].record.episode_id == expected_episode:
                baseline_ok += 1

            ctx = mem.current_semantic_heads(90000+j)
            query = {k: ctx[k] for k in ("state", "goal", "entity", "sequence") if k in ctx}
            t0 = time.perf_counter()
            frame = mem.prepare_context(
                query, conversation_id=90000+j, top_k=3, memory_filter=history_filter,
                min_similarity={h: 0.90 for h in query}, rerank_candidates=128,
            )
            frontier_ms.append((time.perf_counter()-t0)*1000)
            if any(ep.episode_id == expected_episode for ep in frame.recalled_episodes):
                frontier_ok += 1

        # Corrections/open-loop determinism.
        continuity_ok = 0
        for j in range(64):
            cid = 200000+j; h1 = semantic_bundle(300000+j*20); h2 = semantic_bundle(400000+j*20)
            mem.record_transition(h1, 'initial preference', conversation_id=cid, episode_id=300000+j,
                                  namespace='live', working_update=WorkingUpdate(
                                      set_goal='finish task',
                                      add=(WorkingItemSpec('fact','deadline','Tuesday'),
                                           WorkingItemSpec('open_loop','logs','collect logs'))))
            mem.record_transition(h2, 'correction and logs supplied', conversation_id=cid, episode_id=300000+j,
                                  namespace='live', working_update=WorkingUpdate(
                                      resolve=('logs',),
                                      supersede=(WorkingItemSpec('fact','deadline','Thursday'),),
                                      add=(WorkingItemSpec('constraint','no_restart','do not restart'),)))
            s = mem.working_state(cid)
            if (not s.open_loops and s.facts and s.facts[0].value == 'Thursday'
                    and s.corrections and s.corrections[-1].old_value == 'Tuesday'
                    and s.constraints and s.constraints[0].key == 'no_restart'):
                continuity_ok += 1

        mem.sync()

    # Reopen to prove continuity is reconstructed, not just cached.
    restart_ok = 0
    with AssistantMemory(root, hv_dim=DIM, space_id='assistant-readiness-v1', auto_index=False,
                         recent_limit=6, index_options=index_opts) as mem:
        for j in range(64):
            s = mem.working_state(200000+j)
            if (s.facts and s.facts[0].value == 'Thursday' and not s.open_loops
                    and s.corrections and s.corrections[-1].new_value == 'Thursday'):
                restart_ok += 1

        # Explicit good/bad action evidence under the same semantic context.
        base = semantic_bundle(777000); bad = base['action']; good = hv(888000)
        for e in range(6):
            hb = dict(base)
            mem.record_transition(hb, f'bad precedent {e}', conversation_id=400000+e, episode_id=410000+e,
                                  namespace='guard', action='dangerous action', outcome='failed', outcome_score=-1.0)
        for e in range(6):
            hg = dict(base); hg['action'] = good; hg['outcome'] = hv(889000+e)
            mem.record_transition(hg, f'good precedent {e}', conversation_id=500000+e, episode_id=510000+e,
                                  namespace='guard', action='safe action', outcome='succeeded', outcome_score=1.0)
        mem.rebuild_index()
        context = {k: noise(base[k], .02, 990000+i) for i,k in enumerate(('state','goal','entity','sequence'))}
        bad_result = mem.evaluate_action(context, noise(bad,.02,991000), conversation_id=600000,
                                         memory_filter=MemoryFilter(namespace='guard'), semantic_floor=.80,
                                         minimum_evidence=.5, top_k=12)
        good_result = mem.evaluate_action(context, noise(good,.02,992000), conversation_id=600000,
                                          memory_filter=MemoryFilter(namespace='guard'), semantic_floor=.80,
                                          minimum_evidence=.5, top_k=12)
        unknown_result = mem.evaluate_action(
            {k: hv(995000+i) for i,k in enumerate(('state','goal','entity','sequence'))}, hv(996000),
            conversation_id=600000, memory_filter=MemoryFilter(namespace='guard'), semantic_floor=.90,
            minimum_evidence=.5, top_k=12)

    result = {
        'hv_dim': DIM, 'historical_episodes': HISTORY, 'ambiguous_followups': LIVE,
        'history_ingest_seconds': ingest_history_s, 'index_build_seconds': index_s,
        'retrieval_only_ambiguous_accuracy': baseline_ok/LIVE,
        'hng_continuity_ambiguous_accuracy': frontier_ok/LIVE,
        'retrieval_only_median_ms': statistics.median(baseline_ms),
        'hng_continuity_median_ms': statistics.median(frontier_ms),
        'hng_continuity_p95_ms': float(np.percentile(frontier_ms, 95)),
        'working_state_live_accuracy': continuity_ok/64,
        'working_state_restart_accuracy': restart_ok/64,
        'bad_action_decision': bad_result.assessment.decision,
        'good_action_decision': good_result.assessment.decision,
        'unknown_action_decision': unknown_result.assessment.decision,
        'bad_action_exact_evidence': bad_result.assessment.evidence_count,
        'good_action_exact_evidence': good_result.assessment.evidence_count,
    }
    out = Path('/mnt/data/hng-frontier-0.3.0a1/benchmarks/ASSISTANT_READINESS.json')
    out.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps(result, indent=2, sort_keys=True))

if __name__ == '__main__':
    main()
