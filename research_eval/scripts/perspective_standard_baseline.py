"""Conventional structured/exhaustive baselines on the shipped perspective data."""
from __future__ import annotations
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"baseline_source/hng-frontier-0.5.1a1/src"))

# Execute definitions only, stopping before the shipped benchmark mutates storage.
source=(ROOT/"baseline_source/hng-frontier-0.5.1a1/benchmarks/perspective_gauntlet.py").read_text(encoding="utf-8")
prefix=source.split("shutil.rmtree(ROOT,ignore_errors=True)",1)[0]
ns={"__file__":str(ROOT/"baseline_source/hng-frontier-0.5.1a1/benchmarks/perspective_gauntlet.py")};exec(prefix,ns)
PERSONAS=ns["PERSONAS"];CONTEXTS=ns["CONTEXTS"];DIM=ns["DIM"];query_heads=ns["query_heads"];exact_context_heads=ns["exact_context_heads"];target=ns["target"];action_vectors=ns["action_vectors"];action_labels=ns["action_labels"]
HEADS=("state","goal","entity","sequence","perspective","expertise","priority")
records=[];lookup={}
for c in range(CONTEXTS):
    for p in PERSONAS:
        idx,label,action=target(c,p);lookup[(c,p.role,p.expertise,p.priority)]=label
        for outcome,vec in ((1,action),(1,action)):
            records.append((p,c,label,outcome,exact_context_heads(c,p,vec)))
        bad=(p.variant+1)%16;bi=(c%512)*16+bad
        records.append((p,c,action_labels[bi],-1,exact_context_heads(c,p,action_vectors[bi])))
packed={h:np.packbits(np.stack([r[4][h]>0 for r in records]),axis=1,bitorder="little") for h in HEADS}
dense={h:np.stack([r[4][h] for r in records]).astype(np.float32) for h in HEADS}
roles=np.asarray([r[0].role for r in records]);auth=np.asarray([r[0].auth for r in records]);abstraction=np.asarray([r[0].abstraction for r in records]);labels=np.asarray([r[2] for r in records]);outcomes=np.asarray([r[3] for r in records])
def sims(head,q):
    qp=np.packbits(q>0,bitorder="little");return 1-np.bitwise_count(np.bitwise_xor(packed[head],qp)).sum(axis=1)/DIM
def choose(q,p,mode):
    mask=(roles==p.role)&(auth<=p.auth)&(np.abs(abstraction-p.abstraction)<=1)
    heads=HEADS if mode=="full" else HEADS[:4]
    score=np.zeros(len(records),np.float64)
    for h in heads:
        s=sims(h,q[h]);score+=s;mask&=s>=.8
    score/=len(heads);agg=defaultdict(float)
    for i in np.flatnonzero(mask):agg[str(labels[i])]+=(max(0,score[i]-.5)*2)*outcomes[i]
    return max(agg,key=agg.get) if agg else ""
def choose_dense(q,p):
    mask=(roles==p.role)&(auth<=p.auth)&(np.abs(abstraction-p.abstraction)<=1);score=np.zeros(len(records),np.float32)
    for h in HEADS:
        cosine=(dense[h]@q[h].astype(np.float32))/DIM;s=(cosine+1)/2;score+=s;mask&=s>=.8
    score/=len(HEADS);agg=defaultdict(float)
    for i in np.flatnonzero(mask):agg[str(labels[i])]+=(max(0,float(score[i])-.5)*2)*outcomes[i]
    return max(agg,key=agg.get) if agg else ""
def pct(xs,p):return float(np.percentile(xs,p))
def main():
    counts={"structured_full":0,"hard_metadata_only":0,"ordinary_dictionary":0};lat={k:[] for k in counts};total=0
    for c in range(CONTEXTS):
        for p in PERSONAS:
            q=query_heads(c,p);want=target(c,p)[1];total+=1
            for name,mode in (("structured_full","full"),("hard_metadata_only","hard")):
                t=time.perf_counter();got=choose(q,p,mode);lat[name].append((time.perf_counter()-t)*1000);counts[name]+=got==want
            t=time.perf_counter();got=lookup[(c,p.role,p.expertise,p.priority)];lat["ordinary_dictionary"].append((time.perf_counter()-t)*1000);counts["ordinary_dictionary"]+=got==want
    out={name:{"accuracy":counts[name]/total,"queries":total,"median_ms":statistics.median(lat[name]),"p95_ms":pct(lat[name],95),"p99_ms":pct(lat[name],99)} for name in counts}
    dense_ok=0;dense_lat=[];dense_n=0
    for c in range(16):
        for p in PERSONAS:
            q=query_heads(c,p);t=time.perf_counter();got=choose_dense(q,p);dense_lat.append((time.perf_counter()-t)*1000);dense_ok+=got==target(c,p)[1];dense_n+=1
    out["dense_float_multihead"]={"accuracy":dense_ok/dense_n,"queries":dense_n,"median_ms":statistics.median(dense_lat),"p95_ms":pct(dense_lat,95),"p99_ms":pct(dense_lat,99),"note":"Exact cosine over float32 +/-1 versions of the same seven semantic heads."}
    result={"dataset":"shipped perspective gauntlet geometry","same_information":True,"note":"The structured baseline uses exact role/authority/abstraction filters plus exhaustive per-head Hamming floors; the dictionary uses the explicit context/profile fields that define ground truth.","results":out}
    path=ROOT/"research_eval/raw/perspective_standard_baseline.results.json";path.write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result,indent=2))
if __name__=="__main__":main()
