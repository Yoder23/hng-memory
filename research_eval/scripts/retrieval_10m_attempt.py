"""Bounded 10M-vector attempt: HNG vs FAISS Flat/IVF on 4096-bit vectors."""
from __future__ import annotations
import json,time,sys,statistics
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"research_eval/vendor"));sys.path.insert(0,str(ROOT/"baseline_source/hng-frontier-0.5.1a1/src"))
import faiss,psutil
from hngfrontier.index import HDCIndex
from hngfrontier.vectors import hamming_similarity,pack_hv
N=10_000_000;DIM=4096;Q=10
class P:
 def __init__(self,x):self.x=x;self.hv_dim=DIM
 @property
 def count(self):return len(self.x)
 def read_slots(self,s):return self.x[np.asarray(s,np.intp)]
 def read_range(self,a,b):return self.x[a:b]
 def exact_topk(self,q,s,k):
  s=np.asarray(s,np.intp)
  if not len(s):return []
  z=hamming_similarity(self.x[s],pack_hv(q,DIM),DIM);k=min(k,len(s));ii=np.argpartition(z,-k)[-k:];ii=ii[np.argsort(z[ii])[::-1]];return [(int(s[i]),float(z[i])) for i in ii]
def timing(xs):return {"median_ms":statistics.median(xs),"p95_ms":float(np.percentile(xs,95)),"p99_ms":float(np.percentile(xs,99))}
def main():
 rng=np.random.default_rng(20260831);proc=psutil.Process();steps=[];t=time.perf_counter();x=rng.integers(0,256,(N,DIM//8),dtype=np.uint8);steps.append({"step":"generate","seconds":time.perf_counter()-t,"rss":proc.memory_info().rss})
 ids=rng.choice(N,Q,replace=False);queries=x[ids].copy();bits=np.unpackbits(queries,axis=1,bitorder="little");
 for i in range(Q):flip=rng.choice(DIM,int(.02*DIM),replace=False);bits[i,flip]^=1
 queries=np.packbits(bits,axis=1,bitorder="little")
 faiss.omp_set_num_threads(1);flat=faiss.IndexBinaryFlat(DIM);t=time.perf_counter();flat.add(x);steps.append({"step":"faiss_flat_add","seconds":time.perf_counter()-t,"rss":proc.memory_info().rss});truth=[];flatlat=[]
 for q in queries:t=time.perf_counter();_,ii=flat.search(q.reshape(1,-1),10);flatlat.append((time.perf_counter()-t)*1000);truth.append(ii[0])
 provider=P(x);t=time.perf_counter();h=HDCIndex.build(provider,table_count=12,bits_per_table=12,sketch_bits=256);steps.append({"step":"hng_build","seconds":time.perf_counter()-t,"rss":proc.memory_info().rss});hp=[];hl=[];frac=[]
 for q in queries:
  qb=np.unpackbits(q,bitorder="little",count=DIM);t=time.perf_counter();r=h.search(provider,qb,top_k=10,probe_radius=1,rerank_candidates=256);hl.append((time.perf_counter()-t)*1000);hp.append([i for i,_ in r.hits]);frac.append(r.stats.exact_fraction)
 quant=faiss.IndexBinaryFlat(DIM);ivf=faiss.IndexBinaryIVF(quant,DIM,256);train=x[rng.choice(N,100_000,replace=False)];t=time.perf_counter();ivf.train(train);ivf.add(x);steps.append({"step":"faiss_ivf_train_add","seconds":time.perf_counter()-t,"rss":proc.memory_info().rss});runs={}
 for npb in (16,64,256):
  ivf.nprobe=npb;pred=[];lat=[]
  for q in queries:t=time.perf_counter();_,ii=ivf.search(q.reshape(1,-1),10);lat.append((time.perf_counter()-t)*1000);pred.append(ii[0])
  runs[str(npb)]={"top1_agreement":float(np.mean([p[0]==g[0] for p,g in zip(pred,truth)])),**timing(lat)}
 hbytes=sum(a.nbytes for a in (h.positions,h.sketch_positions,h.key_offsets,h.keys,h.starts,h.postings,h.sketches))
 out={"config":{"n":N,"dim":DIM,"queries":Q,"geometry":"independent","threads":1},"steps":steps,"raw_vector_bytes":x.nbytes,"faiss_flat":{**timing(flatlat),"total_bytes":int(faiss.serialize_index_binary(flat).size)},"hng":{"top1_agreement":float(np.mean([p[0]==g[0] for p,g in zip(hp,truth)])),**timing(hl),"index_bytes":hbytes,"total_bytes_including_raw":hbytes+x.nbytes,"median_exact_fraction":float(np.median(frac))},"faiss_ivf":{"total_bytes":int(faiss.serialize_index_binary(ivf).size),"runs":runs},"usearch":{"status":"not_run","reason":"1M build took 374 s and failed to reach matched recall by expansion_search=128; linear projection exceeds one hour at 10M."}}
 path=ROOT/"research_eval/raw/retrieval_kernel_10m.results.json";path.write_text(json.dumps(out,indent=2),encoding="utf-8");print(json.dumps(out,indent=2))
if __name__=="__main__":main()
