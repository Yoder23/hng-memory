"""Executed QMSum comparison under equal evidence budgets and one encoder.

The same deterministic HDC encoder feeds HNG and exact Hamming baselines.
BM25 receives the same transcript units.  No generator or gold span metadata is
used for retrieval; annotations are consulted only after ranking.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
SHIP=ROOT/"baseline_source/hng-frontier-0.5.1a1"
sys.path.insert(0,str(SHIP/"src"));sys.path.insert(0,str(SHIP/"benchmarks"))
import numpy as np
from hngfrontier import CallableDocumentAdapter,DocumentUnitEncoding,HDCDocumentMemory
from hngfrontier.vectors import hamming_similarity,pack_hv
from qmsum_public_hdc import TextHDC,rouge_n_f1,rouge_l_f1,ranges_to_set,tokens


def topk(scores,k):
    k=min(k,len(scores));ii=np.argpartition(scores,-k)[-k:];return ii[np.argsort(scores[ii])[::-1]]


def mmr(packed,query,k,dim,lam=.70):
    rel=hamming_similarity(packed,pack_hv(query,dim),dim);red=np.zeros(len(packed),np.float32);sel=[]
    for _ in range(min(k,len(packed))):
        score=lam*rel+(1-lam)*(1-red)
        if sel: score[np.asarray(sel,np.intp)]=-1e9
        i=int(np.argmax(score));sel.append(i);red=np.maximum(red,hamming_similarity(packed,packed[i],dim))
    return np.asarray(sel,np.intp)


def bm25_matrix(texts):
    docs=[tokens(x) for x in texts];n=len(docs);avg=sum(map(len,docs))/max(1,n);dfs=Counter()
    for d in docs: dfs.update(set(d))
    return docs,avg,dfs


def bm25_scores(index,query):
    docs,avg,dfs=index;n=len(docs);q=tokens(query);out=np.zeros(n,np.float32);k1=1.5;b=.75
    for i,d in enumerate(docs):
        tf=Counter(d);dl=len(d)
        for term in q:
            if not tf[term]:continue
            idf=math.log(1+(n-dfs.get(term,0)+.5)/(dfs.get(term,0)+.5))
            out[i]+=idf*tf[term]*(k1+1)/(tf[term]+k1*(1-b+b*dl/max(1,avg)))
    return out


def norm(x):
    x=np.asarray(x,np.float32);lo=float(x.min(initial=0));hi=float(x.max(initial=0))
    return (x-lo)/(hi-lo) if hi>lo else np.zeros_like(x)


def lat(xs): return {"median_ms":statistics.median(xs),"p95_ms":float(np.percentile(xs,95)),"p99_ms":float(np.percentile(xs,99))}


def main():
    ap=argparse.ArgumentParser();ap.add_argument("jsonl",type=Path);ap.add_argument("--limit",type=int,default=20)
    ap.add_argument("--dim",type=int,default=4096);ap.add_argument("--budget",type=int,default=32);ap.add_argument("--top-k",type=int,default=5)
    ap.add_argument("--output",type=Path,default=ROOT/"research_eval/raw/qmsum_fair_20.results.json");args=ap.parse_args()
    rows=[]
    with args.jsonl.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():rows.append(json.loads(line))
            if len(rows)>=args.limit:break
    hdc=TextHDC(args.dim);tmp=Path(tempfile.mkdtemp(prefix="hng-qmsum-fair-"));per=[];query_hits={x:[] for x in ("hng","exact_topic","exact_multihead","bm25","hybrid")};query_ms={x:[] for x in query_hits}
    try:
        with HDCDocumentMemory(tmp,hv_dim=args.dim,space_id="qmsum-fair-v1",auto_index=False,index_options={"table_count":16,"bits_per_table":12,"sketch_bits":256}) as docs:
            ingest=[]
            for did,row in enumerate(rows,1):
                units=[(f'{u.get("speaker","")}: {u.get("content","")}',0) for u in row["meeting_transcripts"]]
                def enc(text,*,context):return DocumentUnitEncoding(heads={"topic":hdc.encode(text,space="topic"),"claim":hdc.encode(text,space="claim"),"entity":hdc.encode(text,space="entity",bigrams=False),"evidence":hdc.encode(text,space="evidence"),"role":hdc.encode(text,space="role",bigrams=False)})
                t=time.perf_counter();docs.ingest(did,units,CallableDocumentAdapter(enc));ingest.append((time.perf_counter()-t)*1000)
            t=time.perf_counter();docs.rebuild_index();index_ms=(time.perf_counter()-t)*1000
            for did,row in enumerate(rows,1):
                rec=list(docs.records(did));texts=[r.source for r in rec];slots=np.asarray([r.slot for r in rec],np.intp)
                topic=docs.memory.vector_stores["topic"].read_slots(slots);entity=docs.memory.vector_stores["entity"].read_slots(slots);bm=bm25_matrix(texts)
                general=row.get("general_query_list",[{}])[0];gq=general.get("query","summarize the meeting");ref=general.get("answer","")
                qt=hdc.encode(gq,space="topic");qts=hamming_similarity(topic,pack_hv(qt,args.dim),args.dim)
                methods={"lead":np.arange(min(args.budget,len(rec))),"uniform":np.unique(np.rint(np.linspace(0,len(rec)-1,min(args.budget,len(rec)))).astype(np.intp)),"semantic_topk":topk(qts,args.budget),"mmr":mmr(topic,qt,args.budget,args.dim),"bm25":topk(bm25_scores(bm,gq),args.budget)}
                t=time.perf_counter();frame=docs.summarize_document(did,budget_units=args.budget,discover_structure=True);hng_ms=(time.perf_counter()-t)*1000
                byslot={r.slot:i for i,r in enumerate(rec)};methods["hng"]=np.asarray([byslot[s] for s in frame.selected_slots],np.intp)
                scores={}
                for name,ii in methods.items():
                    pred=" ".join(texts[int(i)] for i in ii)
                    scores[name]={"rouge1_f1":rouge_n_f1(pred,ref,1),"rouge2_f1":rouge_n_f1(pred,ref,2),"rougeL_f1":rouge_l_f1(pred,ref),"selected":len(ii)}
                for q in row.get("specific_query_list",[]):
                    gold=ranges_to_set(q.get("relevant_text_span",[]));qtext=q.get("query","")
                    if not gold:continue
                    qtopic=hdc.encode(qtext,space="topic");qentity=hdc.encode(qtext,space="entity",bigrams=False)
                    ts=hamming_similarity(topic,pack_hv(qtopic,args.dim),args.dim);es=hamming_similarity(entity,pack_hv(qentity,args.dim),args.dim);bs=bm25_scores(bm,qtext)
                    rankings={}
                    t=time.perf_counter();rr=docs.query_document_adaptive(did,{"topic":qtopic,"entity":qentity},top_k=args.top_k);query_ms["hng"].append((time.perf_counter()-t)*1000);rankings["hng"]=[int(h.record.extra.get("ordinal",-1)) for h in rr.hits]
                    for name,score in (("exact_topic",ts),("exact_multihead",(ts+es)/2),("bm25",bs),("hybrid",.5*norm(bs)+.25*norm(ts)+.25*norm(es))):
                        t=time.perf_counter();rankings[name]=topk(score,args.top_k).tolist();query_ms[name].append((time.perf_counter()-t)*1000)
                    for name,pred in rankings.items():query_hits[name].append(bool(set(pred)&gold))
                per.append({"document_id":did,"units":len(rec),"segments":len(frame.segments),"ingest_ms":ingest[did-1],"hng_synopsis_ms":hng_ms,"methods":scores})
    finally:shutil.rmtree(tmp,ignore_errors=True)
    method_names=list(per[0]["methods"]);summary={}
    for name in method_names:summary[name]={m:float(np.mean([d["methods"][name][m] for d in per])) for m in ("rouge1_f1","rouge2_f1","rougeL_f1")}
    query={name:{"queries":len(vals),"span_hit_at_5":float(np.mean(vals)),**lat(query_ms[name])} for name,vals in query_hits.items()}
    out={"dataset":"official QMSum test subset","documents":len(per),"dim":args.dim,"evidence_budget":args.budget,"top_k":args.top_k,"index_build_ms":index_ms,"mean_segments":float(np.mean([x["segments"] for x in per])),"all_documents_single_segment":all(x["segments"]==1 for x in per),"summary":summary,"specific_query":query,"per_document":per}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(out,indent=2),encoding="utf-8");print(json.dumps(out,indent=2))


if __name__=="__main__":main()
