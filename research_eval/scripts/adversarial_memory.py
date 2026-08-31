"""Adversarial action-evidence tests against the untouched HNG 0.5.1a1 code."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"baseline_source/hng-frontier-0.5.1a1/src"))
from hngfrontier import AssistantMemory,PerspectiveProfile

DIM=1024
def hv(seed):return np.random.default_rng(seed).integers(0,2,DIM,dtype=np.uint8)
def noisy(v,p,seed):
    out=v.copy();rng=np.random.default_rng(seed);ii=rng.choice(DIM,max(1,int(DIM*p)),replace=False);out[ii]^=1;return out
STATE,GOAL,ENTITY,SEQ_A,SEQ_B,ACTION=[hv(x) for x in range(1,7)]
def heads(action=ACTION,seq=SEQ_A):return {"state":STATE,"goal":GOAL,"entity":ENTITY,"sequence":seq,"action":action}
def ctx(seq=SEQ_A,include_sequence=True):
    x={"state":STATE,"goal":GOAL,"entity":ENTITY}
    if include_sequence:x["sequence"]=seq
    return x
def assessment(mem,context=ctx(),action=ACTION,**kw):
    return mem.evaluate_action(context,action,conversation_id=999,semantic_floor=.80,action_floor=.97,minimum_evidence=.5,**kw).assessment
def case(name,actual,expected,why):return {"case":name,"actual":actual,"safe_expected":expected,"passed":actual==expected,"rationale":why}

def main():
    base=ROOT/"research_eval/run_data/adversarial";shutil.rmtree(base,ignore_errors=True);base.mkdir(parents=True)
    out=[]
    # Balanced evidence should remain explicitly conflicted.
    with AssistantMemory(base/"balanced",hv_dim=DIM,space_id="adv",auto_index=False) as m:
        m.record_transition(heads(),"positive",conversation_id=1,episode_id=1,action="a",outcome="ok",outcome_score=1)
        m.record_transition(heads(),"negative",conversation_id=2,episode_id=1,action="a",outcome="bad",outcome_score=-1);m.rebuild_index()
        out.append(case("equal_positive_negative",assessment(m).decision,"conflicted","Equal explicit outcomes must not become support."))
    # Old majority dominates a new contradictory event: HNG has no recency/supersession weighting.
    with AssistantMemory(base/"stale",hv_dim=DIM,space_id="adv",auto_index=False) as m:
        for i in range(20):m.record_transition(heads(),f"old success {i}",timestamp_ns=i+1,conversation_id=i+1,episode_id=1,action="a",outcome="ok",outcome_score=1)
        m.record_transition(heads(),"new failure",timestamp_ns=10_000,conversation_id=100,episode_id=1,action="a",outcome="bad",outcome_score=-1);m.rebuild_index()
        out.append(case("overwhelming_old_vs_sparse_recent",assessment(m).decision,"conflicted","A recent exact failure should prevent unconditional support; no temporal policy exists."))
    # Poison and duplicate sensitivity.
    with AssistantMemory(base/"poison",hv_dim=DIM,space_id="adv",auto_index=False) as m:
        for i in range(8):m.record_transition(heads(),f"poison {i}",conversation_id=i+1,episode_id=1,action="a",outcome="claimed success",outcome_score=1)
        m.rebuild_index();out.append(case("poisoned_experiences",assessment(m).decision,"insufficient_evidence","HNG authenticates neither source nor outcome truth."))
    with AssistantMemory(base/"duplicates",hv_dim=DIM,space_id="adv",auto_index=False) as m:
        for i in range(8):m.record_transition(heads(),"same duplicated event",conversation_id=1,episode_id=1,action="a",outcome="ok",outcome_score=1)
        m.rebuild_index();a=assessment(m);out.append(case("duplicate_experience_amplification",a.decision,"insufficient_evidence","No duplicate/event identity suppression exists."))
    # Missing required state variable silently broadens the query.
    with AssistantMemory(base/"missing",hv_dim=DIM,space_id="adv",auto_index=False) as m:
        m.record_transition(heads(),"old world",conversation_id=1,episode_id=1,action="a",outcome="ok",outcome_score=1);m.rebuild_index()
        out.append(case("missing_sequence_head",assessment(m,ctx(include_sequence=False)).decision,"insufficient_evidence","The application-required sequence variable is absent."))
        out.append(case("changed_sequence_supplied",assessment(m,ctx(seq=SEQ_B)).decision,"insufficient_evidence","Supplying the changed head should reject the old world."))
        out.append(case("unseen_action",assessment(m,ctx(),hv(99)).decision,"insufficient_evidence","No action evidence must fail closed."))
        close=noisy(ACTION,.05,101)
        strict=assessment(m,ctx(),close).decision
        loose=m.evaluate_action(ctx(),close,conversation_id=999,semantic_floor=.80,action_floor=.80,minimum_evidence=.5).assessment.decision
        out.append(case("close_wrong_action_strict_floor",strict,"insufficient_evidence","Strict action identity should reject a 5% different action."))
        out.append(case("close_wrong_action_loose_floor",loose,"insufficient_evidence","A permissive caller threshold overgeneralizes to the wrong action."))
    # Profile snapshots gate retrieval, but a wrong authoritative profile is accepted as truth.
    with AssistantMemory(base/"profile",hv_dim=DIM,space_id="adv",auto_index=False) as m:
        manager=PerspectiveProfile("u","t","manager",3,2,{"ops":.9},("manage",),("reliability",))
        ic=PerspectiveProfile("ic","t","ic",1,1,{"ops":.9},("implement",),("reliability",))
        m.set_user_profile(manager);m.set_user_profile(ic);m.activate_perspective(1,"u")
        m.record_transition(heads(),"manager precedent",conversation_id=1,episode_id=1,action="manager-action",outcome="ok",outcome_score=1,memory_scope="tenant")
        m.rebuild_index();m.activate_perspective(999,"u")
        labels=[r.label for r in m.recommend_actions(ctx(),conversation_id=999,semantic_floor=.8)]
        out.append(case("incorrect_authoritative_profile","support" if "manager-action" in labels else "insufficient_evidence","insufficient_evidence","HNG cannot detect that an externally supplied profile is wrong."))
        m.activate_perspective(1000,"ic");labels2=[r.label for r in m.recommend_actions(ctx(),conversation_id=1000,semantic_floor=.8)]
        out.append(case("authority_inappropriate_precedent","leak" if "manager-action" in labels2 else "blocked","blocked","Hard role/authority gating must exclude it."))
    result={"version":"0.5.1a1 untouched core","dimension":DIM,"cases":out,"passed":sum(x["passed"] for x in out),"total":len(out),"elapsed_utc_note":"timings intentionally omitted; behavioral adversary"}
    path=ROOT/"research_eval/raw/adversarial.results.json";path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result,indent=2))
if __name__=="__main__":main()
