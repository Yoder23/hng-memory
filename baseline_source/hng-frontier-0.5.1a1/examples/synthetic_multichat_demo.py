from __future__ import annotations

from pathlib import Path
import shutil
import numpy as np

from hngfrontier import AssistantMemory, CallableAssistantAdapter, MemoryFilter, WorkingItemSpec, WorkingUpdate

DIM = 2048

def hv(seed: int):
    return np.random.default_rng(seed).integers(0, 2, size=DIM, dtype=np.uint8)

def noisy(v, frac: float, seed: int):
    out = np.array(v, copy=True)
    rng = np.random.default_rng(seed)
    idx = rng.choice(out.size, size=max(1, int(out.size * frac)), replace=False)
    if np.all((out == -1) | (out == 1)):
        out[idx] *= -1
    else:
        out[idx] ^= 1
    return out

root = Path("/tmp/hng-frontier-multichat-demo")
shutil.rmtree(root, ignore_errors=True)

state = hv(1); goal = hv(2); entity = hv(3); sequence = hv(4)
safe_action = hv(5); bad_action = noisy(safe_action, 0.12, 6)

with AssistantMemory(root, hv_dim=DIM, space_id="demo", auto_index=False,
                     index_options={"table_count": 12, "bits_per_table": 10, "sketch_bits": 128}) as memory:
    # Chat A: successful historical experience.
    memory.record_transition(
        {"state": state, "goal": goal, "entity": entity, "sequence": sequence,
         "action": safe_action, "next_state": noisy(state, 0.02, 7)},
        "Chat A: GPU OOM during concurrent inference.", conversation_id=101, episode_id=1,
        action="reduce-micro-batch", outcome="GPU pressure cleared", outcome_score=1.0,
        namespace="history",
    )
    # Chat B: a bad alternative under the same context.
    memory.record_transition(
        {"state": noisy(state, .01, 8), "goal": noisy(goal, .01, 9), "entity": noisy(entity, .01, 10),
         "sequence": noisy(sequence, .01, 11), "action": bad_action, "next_state": noisy(state, .05, 12)},
        "Chat B: restart-only attempt under the same failure mode.", conversation_id=202, episode_id=1,
        action="restart-worker", outcome="failure returned", outcome_score=-1.0,
        namespace="history",
    )
    memory.rebuild_index()

    # Chat C / turn 1 establishes current HDC state and an explicit working-memory loop.
    memory.record_transition(
        {"state": noisy(state,.02,20), "goal": noisy(goal,.02,21), "entity": noisy(entity,.02,22),
         "sequence": noisy(sequence,.02,23), "action": safe_action, "next_state": noisy(state,.02,24)},
        "Chat C turn 1: same GPU pressure has appeared again.", conversation_id=303, episode_id=1,
        namespace="live",
        working_update=WorkingUpdate(
            set_goal="restore stable inference",
            add=(WorkingItemSpec("open_loop", "latency", "determine whether GPU pressure explains latency"),),
        ),
    )

    # Turn 2 is intentionally elliptical. The HDC interpreter receives prior HDC state directly.
    adapter = CallableAssistantAdapter(lambda _msg, *, context: {
        head: noisy(np.asarray(context.semantic_heads[head]), .01, 100+i)
        for i, head in enumerate(("state", "goal", "entity", "sequence"))
    })
    query = memory.encode_query(adapter, "Could that explain the latency too?", conversation_id=303)
    frame = memory.prepare_context(query, conversation_id=303,
                                   memory_filter=MemoryFilter(namespace="history"),
                                   min_similarity={h:.80 for h in query}, required_route_heads=tuple(query))
    recommendations = memory.recommend_actions(query, conversation_id=303,
                                                memory_filter=MemoryFilter(namespace="history"),
                                                semantic_floor=.80)
    safe = memory.evaluate_action(query, safe_action, conversation_id=303,
                                  memory_filter=MemoryFilter(namespace="history"),
                                  semantic_floor=.80, action_floor=.95, minimum_evidence=.25)
    bad = memory.evaluate_action(query, bad_action, conversation_id=303,
                                 memory_filter=MemoryFilter(namespace="history"),
                                 semantic_floor=.80, action_floor=.95, minimum_evidence=.25)

    print("CURRENT GOAL:", frame.working_state.goal)
    print("OPEN LOOP:", frame.open_loops[0].value)
    print("RECALLED CHAT:", frame.recalled_episodes[0].records[0].source)
    print("RECOMMENDED ACTION:", recommendations[0].label)
    print("SAFE ACTION GATE:", safe.assessment.decision)
    print("BAD ACTION GATE:", bad.assessment.decision)
