from __future__ import annotations
import json, shutil, time
from pathlib import Path
import numpy as np
from hngfrontier import HDCDocumentMemory
from hngfrontier.documents import bundle_packed
from hngfrontier.vectors import hamming_similarity, pack_hv

D=2048; THEMES=128; UNITS=64; BUDGET=140; ROOT=Path('C:\\Python310\\hng-frontier-0.5.1a1-release\\hng-frontier-0.5.1a1-release\\research_eval\\run_data\\document_scale')

def rv(rng): return rng.choice(np.array([-1,1],np.int8),size=D)
def noisy(v,rng,p):
 o=v.copy(); m=rng.random(D)<p; o[m]*=-1; return o

def main():
 if ROOT.exists(): shutil.rmtree(ROOT)
 rng=np.random.default_rng(405)
 rows=[]; keys=[]; priority=[]
 order=[]
 for t in range(THEMES): order.extend([t]*(4 if t<4 else 1))
 theme=[rv(rng) for _ in range(THEMES)]; entity=[rv(rng) for _ in range(32)]; kind={k:rv(rng) for k in ['body','key_claim','caveat','contradiction','conclusion']}
 caveat=set(rng.choice(THEMES,size=5,replace=False).tolist()); remaining=[x for x in range(THEMES) if x not in caveat]; contra=set(rng.choice(remaining,size=3,replace=False).tolist())
 t0=time.perf_counter()
 with HDCDocumentMemory(ROOT,hv_dim=D,space_id='scale',auto_index=False) as mem:
  first=set(); ordinal=0
  for ps,t in enumerate(order):
   first_t=t not in first; first.add(t)
   for j in range(UNITS):
    k='body'; imp=.42+.1*rng.random()
    if first_t and j==0: k='key_claim'; imp=.58
    if first_t and t in caveat and j==UNITS-2: k='caveat'; imp=.99
    if first_t and t in contra and j==UNITS-1: k='contradiction'; imp=1
    if ps==len(order)-1 and j==UNITS-1: k='conclusion'; imp=1
    base=theme[t]; topic=noisy(base,rng,.06 if k=='body' else (.006 if k=='key_claim' else .035)); claim=noisy(base,rng,.055); ent=noisy(entity[t%32],rng,.035)
    ev=np.where(base.astype(np.int16)*3+kind[k].astype(np.int16)>=0,1,-1).astype(np.int8); ev=noisy(ev,rng,.035)
    slot=mem.add_unit(1,f'THEME {t} {k.upper()} ps={ps} u={j}',{'topic':topic,'claim':claim,'entity':ent,'evidence':ev,'role':noisy(kind[k],rng,.02)},ordinal=ordinal,section_id=ps,kind=k,importance=imp,extra={'theme_id':t})
    idx=len(rows); rows.append({'slot':slot,'theme':t,'kind':k,'importance':imp});
    if k=='key_claim': keys.append(idx)
    if k in {'caveat','contradiction','conclusion'}: priority.append(idx)
    ordinal+=1
  ingest=time.perf_counter()-t0
  rec=mem.records(1); slots=np.asarray([r.slot for r in rec],np.intp); packed=mem.memory.vector_stores['topic'].read_slots(slots); proto=bundle_packed(packed,D); importance=np.asarray([r.importance for r in rec],np.float32)
  t=time.perf_counter(); frame=mem.summarize_document(1,budget_units=BUDGET,discover_structure=True,priority_role_queries={x:kind[x] for x in ('caveat','contradiction','conclusion')},role_head='role',priority_similarity=.88); hng=(time.perf_counter()-t)*1000
  local={r.slot:i for i,r in enumerate(rec)}; hidx=[local[s] for s in frame.selected_slots]
  def met(idx):
   ids=set(map(int,idx)); th={rows[i]['theme'] for i in ids}; return {'theme_coverage':len(th)/THEMES,'key_recall':sum(i in ids for i in keys)/len(keys),'priority_recall':sum(i in ids for i in priority)/len(priority),'selected':len(ids)}
  sims=hamming_similarity(packed,pack_hv(proto,D),D)
  t=time.perf_counter(); ii=np.argpartition(sims,-BUDGET)[-BUDGET:]; topms=(time.perf_counter()-t)*1000
  # MMR
  t=time.perf_counter(); sel=[]; red=np.zeros(len(rec),np.float32)
  for _ in range(BUDGET):
   score=.68*sims+.08*importance+.24*(1-red)
   if sel: score[np.asarray(sel,np.intp)]=-1e9
   i=int(np.argmax(score)); sel.append(i); red=np.maximum(red,hamming_similarity(packed,packed[i],D))
  mmr=(time.perf_counter()-t)*1000
  out={'config':{'units':len(rec),'themes':THEMES,'budget':BUDGET,'hv_dim':D},'ingest_seconds':ingest,'hng':met(hidx)|{'ms':hng,'segments':len(frame.segments)},'rag_topk':met(ii)|{'ms':topms},'rag_mmr':met(sel)|{'ms':mmr}}
 Path('C:\\Python310\\hng-frontier-0.5.1a1-release\\hng-frontier-0.5.1a1-release\\research_eval\\raw\\document_scale.results.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=='__main__': main()
