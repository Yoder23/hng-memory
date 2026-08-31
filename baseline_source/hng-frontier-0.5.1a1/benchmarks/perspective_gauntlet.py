from __future__ import annotations

import json, shutil, time
from dataclasses import dataclass
from pathlib import Path
import numpy as np

from hngfrontier import AssistantMemory, PerspectiveOverride, PerspectivePolicy, PerspectiveProfile

DIM=4096
CONTEXTS=64
FAMILIES=512
VARIANTS=16
ACTIONS=FAMILIES*VARIANTS
ROOT=Path('/tmp/hng-perspective-gauntlet')
OUT=Path(__file__).with_name('PERSPECTIVE_GAUNTLET.json')


def hv(seed:int):
    return np.random.default_rng(seed).choice(np.array([-1,1],dtype=np.int8), size=DIM)

def flip(v, frac, seed):
    out=v.copy(); rng=np.random.default_rng(seed); idx=rng.choice(DIM,size=max(1,int(DIM*frac)),replace=False); out[idx]*=-1; return out

def sim(a,b): return float(np.mean(a==b))

@dataclass(frozen=True)
class Persona:
    key:str; role:str; auth:int; abstraction:int; expertise:str; priority:str; variant:int

PERSONAS=(
    Persona('ic-delivery','ic',1,1,'novice','delivery',0),
    Persona('ic-reliability','ic',1,1,'expert','reliability',1),
    Persona('staff-delivery','staff',2,2,'expert','delivery',2),
    Persona('staff-reliability','staff',2,2,'expert','reliability',3),
    Persona('manager-delivery','manager',3,2,'novice','delivery',4),
    Persona('manager-reliability','manager',3,2,'expert','reliability',5),
    Persona('exec-growth','executive',5,4,'generalist','growth',6),
    Persona('exec-risk','executive',5,4,'generalist','risk',7),
)

# Role HDC states intentionally share a common base so semantic role similarity alone is not a hard boundary.
role_base=hv(900_000)
role_hv={r:flip(role_base,.08,900_100+i) for i,r in enumerate(sorted({p.role for p in PERSONAS}))}
expertise_hv={x:hv(901_000+i) for i,x in enumerate(sorted({p.expertise for p in PERSONAS}))}
priority_hv={x:hv(902_000+i) for i,x in enumerate(sorted({p.priority for p in PERSONAS}))}

def make_profile(p:Persona):
    level={'novice':.25,'expert':.9,'generalist':.6}[p.expertise]
    return PerspectiveProfile(
        user_id='user-'+p.key, tenant_id='acme', role=p.role, authority_level=p.auth,
        abstraction_level=p.abstraction, expertise={'engineering':level},
        responsibilities=(p.role,), priorities=(p.priority,), extra={'persona':p.key},
    )

def query_heads(context:int,p:Persona):
    base=1_000_000+context*20
    return {
        'state':flip(hv(base+1),.02,base+11), 'goal':flip(hv(base+2),.02,base+12),
        'entity':flip(hv(base+3),.02,base+13), 'sequence':flip(hv(base+4),.02,base+14),
        'perspective':flip(role_hv[p.role],.01,base+15),
        'expertise':flip(expertise_hv[p.expertise],.01,base+16),
        'priority':flip(priority_hv[p.priority],.01,base+17),
    }

def exact_context_heads(context:int,p:Persona,action):
    base=1_000_000+context*20
    return {
        'state':hv(base+1),'goal':hv(base+2),'entity':hv(base+3),'sequence':hv(base+4),
        'perspective':role_hv[p.role], 'expertise':expertise_hv[p.expertise],
        'priority':priority_hv[p.priority], 'action':action,
    }

# 8K action library; variants in a family are intentionally close.
action_family=[hv(2_000_000+i) for i in range(FAMILIES)]
action_vectors=[]; action_labels=[]
for f in range(FAMILIES):
    for v in range(VARIANTS):
        action_vectors.append(flip(action_family[f],.08,2_100_000+f*VARIANTS+v))
        action_labels.append(f'action-{f:04d}-v{v:02d}')
action_matrix=np.stack(action_vectors)
action_packed=np.packbits((action_matrix>0).astype(np.uint8),axis=1,bitorder="little")

def target(context:int,p:Persona):
    fam=context % FAMILIES; idx=fam*VARIANTS+p.variant
    return idx, action_labels[idx], action_vectors[idx]

def raw_route(context:int,p:Persona):
    # Assistant knows the action family, not which historically appropriate close variant.
    q=action_family[context%FAMILIES]
    qp=np.packbits((q>0).astype(np.uint8),bitorder="little")
    d=np.bitwise_count(np.bitwise_xor(action_packed,qp)).sum(axis=1)
    ii=np.argpartition(d, VARIANTS-1)[:VARIANTS]
    ii=ii[np.argsort(d[ii])]
    return int(ii[0]), ii

shutil.rmtree(ROOT,ignore_errors=True)
results={}
with AssistantMemory(ROOT,hv_dim=DIM,space_id='perspective-v1',auto_index=False,
    index_options={'table_count':16,'bits_per_table':11,'sketch_bits':256,'seed':0xC0FFEE}) as mem:
    for p in PERSONAS:
        mem.set_user_profile(make_profile(p))

    t0=time.perf_counter(); records=0
    # Shared tenant precedents: identical semantic contexts, different actors and priorities.
    for c in range(CONTEXTS):
        for pi,p in enumerate(PERSONAS):
            cid=10_000+c*100+pi
            mem.activate_perspective(cid,'user-'+p.key)
            idx,label,action=target(c,p)
            # Two successful precedents for the right actor-conditioned variant.
            for k in range(2):
                mem.record_transition(exact_context_heads(c,p,action),f'{p.key} context {c} success {k}',
                    conversation_id=cid,episode_id=k+1,action=label,outcome='worked',outcome_score=1.0,
                    memory_scope='tenant')
                records+=1
            # One close sibling failed for this same perspective.
            badv=(p.variant+1)%VARIANTS; badidx=(c%FAMILIES)*VARIANTS+badv
            mem.record_transition(exact_context_heads(c,p,action_vectors[badidx]),f'{p.key} context {c} bad',
                conversation_id=cid,episode_id=3,action=action_labels[badidx],outcome='failed',outcome_score=-1.0,
                memory_scope='tenant')
            records+=1
    ingest_s=time.perf_counter()-t0
    t0=time.perf_counter(); mem.rebuild_index(); index_s=time.perf_counter()-t0

    raw_correct=0; raw_top16=0; semantic_correct=0; soft_correct=0; conditioned_correct=0
    semantic_role_viol=0; conditioned_role_viol=0
    lat_sem=[]; lat_soft=[]; lat_cond=[]
    samples=[]
    for c in range(CONTEXTS):
        for pi,p in enumerate(PERSONAS):
            q=query_heads(c,p); target_idx,target_label,_=target(c,p)
            ri,top16=raw_route(c,p); raw_correct+=int(ri==target_idx); raw_top16+=int(target_idx in top16)
            live_cid=1_000_000+c*100+pi
            mem.activate_perspective(live_cid,'user-'+p.key)
            # Semantics-only ignores actor/perspective heads and access policy.
            basic={k:q[k] for k in ('state','goal','entity','sequence')}
            st=time.perf_counter(); sem=mem.recommend_actions(basic,conversation_id=live_cid,max_actions=1,semantic_floor=.80,
                perspective_policy=PerspectivePolicy.disabled()); lat_sem.append(time.perf_counter()-st)
            # Soft perspective uses all HDC heads but intentionally disables the non-semantic actor gate.
            if c < 16:
                st=time.perf_counter(); soft=mem.recommend_actions(q,conversation_id=live_cid,max_actions=1,semantic_floor=.80,
                    perspective_policy=PerspectivePolicy.disabled()); lat_soft.append(time.perf_counter()-st)
                so=soft[0].label if soft else ''
                soft_correct+=int(so==target_label)
            else:
                so=''
            # Full HNG perspective: same semantic heads + hard identity/role/authority/abstraction eligibility.
            st=time.perf_counter(); cond=mem.recommend_actions(q,conversation_id=live_cid,max_actions=1,semantic_floor=.80); lat_cond.append(time.perf_counter()-st)
            sl=sem[0].label if sem else ''; cl=cond[0].label if cond else ''
            semantic_correct+=int(sl==target_label); conditioned_correct+=int(cl==target_label)
            if sem:
                rec=mem.memory.db.get(sem[0].slots[0]); semantic_role_viol+=int(rec is not None and rec.actor_role not in ('',p.role))
            if cond:
                rec=mem.memory.db.get(cond[0].slots[0]); conditioned_role_viol+=int(rec is not None and rec.actor_role not in ('',p.role))
            if len(samples)<8 and pi in (0,4,6): samples.append({'context':c,'persona':p.key,'target':target_label,'semantic_only':sl,'soft':so,'conditioned':cl})

    total=CONTEXTS*len(PERSONAS)
    results['main']={
        'contexts':CONTEXTS,'personas':len(PERSONAS),'queries':total,'historical_records':records,'action_library':ACTIONS,
        'raw_action_top1':raw_correct/total,'raw_action_top16':raw_top16/total,
        'semantic_only_top1':semantic_correct/total,'soft_perspective_top1_sample':soft_correct/(16*len(PERSONAS)),
        'perspective_conditioned_top1':conditioned_correct/total,
        'semantic_only_role_violation_rate':semantic_role_viol/total,
        'perspective_role_violation_rate':conditioned_role_viol/total,
        'semantic_median_ms':float(np.median(lat_sem)*1000),'soft_median_ms':float(np.median(lat_soft)*1000),
        'conditioned_median_ms':float(np.median(lat_cond)*1000),'conditioned_p95_ms':float(np.percentile(lat_cond,95)*1000),
        'ingest_seconds':ingest_s,'index_seconds':index_s,'samples':samples,
    }

    # Same durable user, explicitly switching acting perspective inside a conversation.
    base_persona=PERSONAS[0]; manager=PERSONAS[4]
    switch_ok=0; switch_n=64
    for c in range(switch_n):
        cid=2_000_000+c
        mem.activate_perspective(cid,'user-'+base_persona.key,PerspectiveOverride(
            role=manager.role,authority_level=manager.auth,abstraction_level=manager.abstraction,
            expertise={'engineering':.25},responsibilities=('manage team',),priorities=(manager.priority,),
        ))
        q=query_heads(c,manager)
        out=mem.recommend_actions(q,conversation_id=cid,max_actions=1,semantic_floor=.80)
        switch_ok+=int(bool(out) and out[0].label==target(c,manager)[1])
    results['role_switch']={'queries':switch_n,'accuracy':switch_ok/switch_n}

    # Private-memory isolation: same HDC state, same role, opposite evidence cannot cross user boundary.
    alice=PerspectiveProfile('alice','acme','ic',1,1,{'engineering':.9},('code',),('reliability',))
    bob=PerspectiveProfile('bob','acme','ic',1,1,{'engineering':.9},('code',),('reliability',))
    mem.set_user_profile(alice); mem.set_user_profile(bob)
    c=0; p=PERSONAS[1]; q=query_heads(c,p)
    mem.activate_perspective(3_000_001,'alice')
    mem.record_transition(exact_context_heads(c,p,action_vectors[0]),'alice secret',conversation_id=3_000_001,episode_id=1,
        action='alice-private-action',outcome='worked',outcome_score=1,memory_scope='private')
    mem.activate_perspective(3_000_002,'bob')
    mem.record_transition(exact_context_heads(c,p,action_vectors[1]),'bob secret',conversation_id=3_000_002,episode_id=1,
        action='bob-private-action',outcome='worked',outcome_score=1,memory_scope='private')
    # Stale tail is intentional: privacy must be correct even before rebuilding.
    privacy_ok=0
    for cid,uid,want,notwant in [(3_000_001,'alice','alice-private-action','bob-private-action'),(3_000_002,'bob','bob-private-action','alice-private-action')]:
        mem.activate_perspective(cid,uid)
        # Filter private only to make the isolation assertion exact.
        from hngfrontier import MemoryFilter
        out=mem.recommend_actions(q,conversation_id=cid,max_actions=8,semantic_floor=.8,
            memory_filter=MemoryFilter(scopes=('private',)))
        labels={x.label for x in out}; privacy_ok+=int(want in labels and notwant not in labels)
    results['privacy']={'checks':2,'passed':privacy_ok,'leakage':2-privacy_ok}

    # Profile priority update should change future routing without rewriting old history.
    user='user-ic-delivery'; cid=4_000_001
    mem.activate_perspective(cid,user)
    q_delivery=query_heads(5,PERSONAS[0])
    before=mem.recommend_actions(q_delivery,conversation_id=cid,max_actions=1,semantic_floor=.8)[0].label
    updated=PerspectiveProfile(user,'acme','ic',1,1,{'engineering':.9},('software delivery',),('reliability',))
    mem.set_user_profile(updated)
    # Re-activate not required; effective perspective resolves latest durable profile. Query head changes because interpreter sees new priority.
    q_reliability=query_heads(5,PERSONAS[1])
    after=mem.recommend_actions(q_reliability,conversation_id=cid,max_actions=1,semantic_floor=.8)[0].label
    results['profile_update']={'before':before,'after':after,'expected_before':target(5,PERSONAS[0])[1],
        'expected_after':target(5,PERSONAS[1])[1], 'passed':before==target(5,PERSONAS[0])[1] and after==target(5,PERSONAS[1])[1]}

OUT.write_text(json.dumps(results,indent=2,sort_keys=True))
print(json.dumps(results,indent=2,sort_keys=True))
