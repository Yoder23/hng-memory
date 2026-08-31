"""Re-score shipped synthetic documents after equalizing priority information."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"baseline_source/hng-frontier-0.5.1a1/src"))
from hngfrontier import HDCDocumentMemory
from hngfrontier.documents import bundle_packed
from hngfrontier.vectors import hamming_similarity,pack_hv

D=2048;DOCS=32;BUDGET=40
def rv(rng):return rng.choice(np.array([-1,1],np.int8),size=D)
def metric(ii,recs):
    ids=set(map(int,ii));themes={int(recs[i].extra["theme_id"]) for i in ids};keys=[i for i,r in enumerate(recs) if r.record_type=="key_claim"];prio=[i for i,r in enumerate(recs) if r.record_type in {"caveat","contradiction","conclusion"}];contra=[i for i,r in enumerate(recs) if r.record_type=="contradiction"]
    return {"theme_coverage":len(themes)/16,"key_claim_recall":sum(i in ids for i in keys)/len(keys),"priority_recall":sum(i in ids for i in prio)/len(prio),"contradiction_recall":sum(i in ids for i in contra)/len(contra)}
def fill(packed,proto,importance,priority,budget,mode):
    chosen=list(dict.fromkeys(map(int,priority)));q=pack_hv(proto,D);rel=hamming_similarity(packed,q,D);red=np.zeros(len(packed),np.float32)
    for i in chosen:red=np.maximum(red,hamming_similarity(packed,packed[i],D))
    while len(chosen)<budget:
        if mode=="mmr":score=.68*rel+.08*importance+.24*(1-red)
        elif mode=="semantic":score=rel
        else:score=importance
        if chosen:score[np.asarray(chosen,np.intp)]=-1e9
        i=int(np.argmax(score));chosen.append(i);red=np.maximum(red,hamming_similarity(packed,packed[i],D))
    return np.asarray(chosen[:budget],np.intp)
def main():
    root=ROOT/"research_eval/run_data/document_breakthrough";rng=np.random.default_rng(404);kind={k:rv(rng) for k in ["body","key_claim","caveat","contradiction","conclusion"]};rows={x:[] for x in ("hng","mmr_equal_info","semantic_equal_info","importance_equal_info")};times={x:[] for x in rows}
    with HDCDocumentMemory(root,hv_dim=D,space_id="doc-breakthrough-v1",auto_index=False,index_options={"table_count":12,"bits_per_table":12,"sketch_bits":256}) as mem:
        for did in range(1,DOCS+1):
            rec=list(mem.records(did));slots=np.asarray([r.slot for r in rec],np.intp);topic=mem.memory.vector_stores["topic"].read_slots(slots);role=mem.memory.vector_stores["role"].read_slots(slots);proto=bundle_packed(topic,D);imp=np.asarray([r.importance for r in rec],np.float32)
            pm=np.zeros(len(rec),bool)
            for k in ("caveat","contradiction","conclusion"):pm|=hamming_similarity(role,pack_hv(kind[k],D),D)>=.88
            priority=np.flatnonzero(pm)
            t=time.perf_counter();frame=mem.summarize_document(did,budget_units=BUDGET,discover_structure=True,priority_role_queries={k:kind[k] for k in ("caveat","contradiction","conclusion")},role_head="role",priority_similarity=.88);times["hng"].append((time.perf_counter()-t)*1000);local={s:i for i,s in enumerate(slots)};rows["hng"].append(metric([local[s] for s in frame.selected_slots],rec))
            for name,mode in (("mmr_equal_info","mmr"),("semantic_equal_info","semantic"),("importance_equal_info","importance")):
                t=time.perf_counter();ii=fill(topic,proto,imp,priority,BUDGET,mode);times[name].append((time.perf_counter()-t)*1000);rows[name].append(metric(ii,rec))
    out={name:{**{k:float(np.mean([r[k] for r in vals])) for k in vals[0]},"median_ms":float(np.median(times[name])),"p95_ms":float(np.percentile(times[name],95))} for name,vals in rows.items()}
    result={"dataset":"shipped synthetic document workload","fairness_change":"Every method receives the same HDC role-head priority detections previously given only to HNG and oracle KMeans.","budget":BUDGET,"summary":out};path=ROOT/"research_eval/raw/document_equal_information.results.json";path.write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result,indent=2))
if __name__=="__main__":main()
