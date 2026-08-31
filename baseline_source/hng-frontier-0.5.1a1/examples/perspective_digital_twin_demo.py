from __future__ import annotations

from pathlib import Path
import shutil
import numpy as np

from hngfrontier import AssistantMemory, PerspectiveOverride, PerspectiveProfile

DIM=2048

def hv(seed):
    return np.random.default_rng(seed).choice(np.array([-1,1],dtype=np.int8),size=DIM)

root=Path('/tmp/hng-perspective-demo'); shutil.rmtree(root,ignore_errors=True)
state,goal,entity,sequence=[hv(x) for x in (1,2,3,4)]
# Deliberately identical semantic problem. Only actor perspective changes what is appropriate.
perspective_base=hv(10); expertise=hv(11); delivery=hv(12); strategy=hv(13)
ic_action=hv(20); manager_action=hv(21)

with AssistantMemory(root,hv_dim=DIM,space_id='perspective-demo',auto_index=False,
                     index_options={'table_count':12,'bits_per_table':10,'sketch_bits':128}) as memory:
    memory.set_user_profile(PerspectiveProfile(
        user_id='alex',tenant_id='acme',role='individual-contributor',authority_level=1,
        abstraction_level=1,expertise={'backend':.9},responsibilities=('own service implementation',),
        priorities=('delivery',),
    ))
    memory.set_user_profile(PerspectiveProfile(
        user_id='morgan',tenant_id='acme',role='engineering-manager',authority_level=3,
        abstraction_level=2,expertise={'backend':.7},responsibilities=('team delivery',),
        priorities=('delivery',),
    ))

    # Shared organizational experience, but recorded with who could appropriately take the action.
    memory.activate_perspective(101,'alex')
    memory.record_transition(
        {'state':state,'goal':goal,'entity':entity,'sequence':sequence,'perspective':perspective_base,
         'expertise':expertise,'priority':delivery,'action':ic_action},
        'Database latency rose during ingestion.',conversation_id=101,episode_id=1,
        action='profile-query-and-fix-index',outcome='latency recovered',outcome_score=1.0,memory_scope='tenant')

    memory.activate_perspective(202,'morgan')
    memory.record_transition(
        {'state':state,'goal':goal,'entity':entity,'sequence':sequence,'perspective':perspective_base,
         'expertise':expertise,'priority':delivery,'action':manager_action},
        'Same database latency pattern, viewed from team ownership.',conversation_id=202,episode_id=1,
        action='reprioritize-team-reliability-work',outcome='recurrence dropped',outcome_score=1.0,memory_scope='tenant')
    memory.rebuild_index()

    semantic_query={'state':state,'goal':goal,'entity':entity,'sequence':sequence}
    full_query={**semantic_query,'perspective':perspective_base,'expertise':expertise,'priority':delivery}

    # Same literal problem, different people.
    memory.activate_perspective(301,'alex')
    alex=memory.recommend_actions(full_query,conversation_id=301,max_actions=3,semantic_floor=.8)
    memory.activate_perspective(302,'morgan')
    morgan=memory.recommend_actions(full_query,conversation_id=302,max_actions=3,semantic_floor=.8)

    # Same durable person can explicitly act in a different role for one conversation.
    memory.activate_perspective(303,'alex',PerspectiveOverride(
        role='engineering-manager',authority_level=3,abstraction_level=2,
        responsibilities=('acting team lead',),priorities=('delivery',),
    ))
    acting_manager=memory.recommend_actions(full_query,conversation_id=303,max_actions=3,semantic_floor=.8)

    print('SAME QUERY:', 'How should we address the database latency problem?')
    print('ALEX / IC:', alex[0].label)
    print('MORGAN / MANAGER:', morgan[0].label)
    print('ALEX / ACTING MANAGER:', acting_manager[0].label)
    print('ALEX PROFILE:', memory.perspective(303).as_dict())
