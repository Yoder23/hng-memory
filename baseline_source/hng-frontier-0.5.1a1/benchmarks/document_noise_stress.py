from __future__ import annotations
import json,time
from pathlib import Path
import numpy as np
from hngfrontier import HDCDocumentMemory
from hngfrontier.vectors import unpack_hv
ROOT=Path('/mnt/data/hng_doc_breakthrough_full_v3'); D=2048

def noise(v,rng,p):
 o=v.copy(); m=rng.random(v.size)<p; o[m]*=-1; return o

def main():
 rng=np.random.default_rng(441); out={}
 with HDCDocumentMemory(ROOT,hv_dim=D,space_id='doc-breakthrough-v1',auto_index=False,index_options={'table_count':12,'bits_per_table':12,'sketch_bits':256}) as mem:
  # use stored indices from the previous benchmark; build if absent
  for h in ('topic','entity'):
   if h not in mem.memory.indices: mem.rebuild_index(h)
  targets=[]
  for doc in range(1,33):
   recs=mem.records(doc)
   for r in recs:
    if r.record_type=='key_claim': targets.append((doc,r.slot))
  pick=rng.choice(len(targets),size=min(192,len(targets)),replace=False)
  for p in (.02,.05,.10,.15):
   ok=0; times=[]; exact=[]
   for qi in pick:
    doc,slot=targets[int(qi)]
    topic=unpack_hv(mem.memory.vector_stores['topic'].read_slots(np.asarray([slot],np.intp))[0],D)
    entity=unpack_hv(mem.memory.vector_stores['entity'].read_slots(np.asarray([slot],np.intp))[0],D)
    q={'topic':noise(topic,rng,p),'entity':noise(entity,rng,p)}
    t=time.perf_counter(); rr=mem.query_document_adaptive(doc,q,top_k=5,min_similarity={'topic':.75,'entity':.75},required_route_heads=('topic','entity'),start_radius=1,max_radius=2,min_hits=1); times.append((time.perf_counter()-t)*1000)
    ok += int(any(h.slot==slot for h in rr.hits)); exact.append(rr.stats.exact_candidates)
   out[f'{int(p*100)}pct']={'recall_at5':ok/len(pick),'median_ms':float(np.median(times)),'p95_ms':float(np.percentile(times,95)),'median_exact_candidates':float(np.median(exact))}
 Path('/mnt/data/hng-frontier-0.4.0a1/benchmarks/DOCUMENT_NOISE.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=='__main__': main()
