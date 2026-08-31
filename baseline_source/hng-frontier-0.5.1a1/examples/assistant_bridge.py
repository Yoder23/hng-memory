"""Minimal integration skeleton. Replace `my_encoder` with your HDC interpreter."""
import numpy as np
from hngfrontier import AssistantMemory, CallableAssistantAdapter, WorkingUpdate

DIM = 10_000
rng = np.random.default_rng(7)
def demo_hv():
    return rng.choice(np.array([-1, 1], dtype=np.int8), size=DIM)

# Example only: a real HDC assistant should bind/bundle the new observation with the
# provided prior semantic state using its actual interpreter semantics.
def my_encoder(value, *, context):
    prior_state = context.semantic_heads.get("state")
    return {
        "state": prior_state if prior_state is not None else demo_hv(),
        "goal": context.semantic_heads.get("goal", demo_hv()),
        "entity": context.semantic_heads.get("entity", demo_hv()),
        "sequence": demo_hv(),
    }

adapter = CallableAssistantAdapter(my_encoder)

with AssistantMemory("./demo-memory", hv_dim=DIM, space_id="my-hdc-v1", auto_index=False) as memory:
    first = {h: demo_hv() for h in AssistantMemory.DEFAULT_HEADS}
    memory.record_transition(
        first, "User reports a recurring production issue.",
        conversation_id=1, episode_id=1,
        working_update=WorkingUpdate(set_goal="diagnose issue"),
    )

    # Elliptical next turn: the adapter receives prior committed HDC state directly.
    query_heads = memory.encode_query(adapter, "Could that explain the latency too?", conversation_id=1)
    frame = memory.prepare_context(query_heads, conversation_id=1)
    print(frame.as_dict())
