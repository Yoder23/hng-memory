from __future__ import annotations

import argparse, json, shutil, statistics, time
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

from hngfrontier import HDCDocumentMemory
from hngfrontier.documents import bundle_packed
from hngfrontier.vectors import hamming_similarity, pack_hv


def rand_hv(rng, d):
    return rng.choice(np.array([-1, 1], dtype=np.int8), size=d)


def noisy(v, rng, p):
    out = np.asarray(v, dtype=np.int8).copy()
    mask = rng.random(out.size) < p
    out[mask] *= -1
    return out


def rag_topk(packed, doc_proto, importance, k, hv_dim, *, importance_weight=0.0):
    sims = hamming_similarity(packed, pack_hv(doc_proto, hv_dim), hv_dim)
    score = (1.0 - importance_weight) * sims + importance_weight * importance
    ii = np.argpartition(score, -min(k, score.size))[-min(k, score.size):]
    return ii[np.argsort(score[ii])[::-1]]


def rag_mmr(packed, doc_proto, importance, k, hv_dim, *, lam=0.68, importance_weight=0.08):
    q = pack_hv(doc_proto, hv_dim)
    relevance = hamming_similarity(packed, q, hv_dim)
    selected=[]; remaining=np.arange(packed.shape[0], dtype=np.intp)
    redundancy=np.zeros(packed.shape[0], np.float32)
    for _ in range(min(k, packed.shape[0])):
        score = lam * relevance + importance_weight * importance + (1.0-lam-importance_weight) * (1.0-redundancy)
        if selected:
            score[np.asarray(selected, np.intp)] = -1e9
        i=int(np.argmax(score)); selected.append(i)
        sim_to_i=hamming_similarity(packed, packed[i], hv_dim)
        redundancy=np.maximum(redundancy, sim_to_i)
    return np.asarray(selected, dtype=np.intp)


def metrics(indices, rows, key_indices, priority_indices, theme_count):
    ids=set(int(i) for i in indices)
    themes={int(rows[i]['theme']) for i in ids}
    keys=sum(1 for i in key_indices if i in ids)
    pr=sum(1 for i in priority_indices if i in ids)
    contradictions=sum(1 for i in priority_indices if i in ids and rows[i]['kind']=='contradiction')
    total_contra=sum(1 for i in priority_indices if rows[i]['kind']=='contradiction')
    return {
        'theme_coverage': len(themes)/theme_count,
        'key_claim_recall': keys/len(key_indices),
        'priority_recall': pr/len(priority_indices) if priority_indices else 1.0,
        'contradiction_recall': contradictions/total_contra if total_contra else 1.0,
        'selected': len(ids),
        'unique_themes': len(themes),
        'redundancy_fraction': 1.0 - len(themes)/max(1,len(ids)),
    }


def run(root: Path, *, docs=32, hv_dim=2048, themes=16, units_per_section=10, budget=40, seed=404):
    if root.exists(): shutil.rmtree(root)
    rng=np.random.default_rng(seed)
    index_opts={'table_count':12,'bits_per_table':12,'sketch_bits':256}
    doc_rows={}; key_by_doc={}; priority_by_doc={}; true_boundaries={}
    ingest_t0=time.perf_counter()
    with HDCDocumentMemory(root, hv_dim=hv_dim, space_id='doc-breakthrough-v1', auto_index=False, index_options=index_opts) as mem:
        global_kind={k:rand_hv(rng,hv_dim) for k in ['body','key_claim','caveat','contradiction','conclusion']}
        ordinal_global=0
        for doc_id in range(1,docs+1):
            # 4 dominant themes repeat in 4 physical sections, remaining themes once.
            theme_order=[]
            for t in range(themes):
                theme_order.extend([t] * (4 if t < 4 else 1))
            # Keep repetitions contiguous but rotate theme order per document.
            shift=doc_id % themes
            chunks=[]
            for t in range(themes):
                tt=(t+shift)%themes
                chunks.extend([tt]*(4 if tt < 4 else 1))
            theme_order=chunks
            theme_vec=[rand_hv(rng,hv_dim) for _ in range(themes)]
            entity_vec=[rand_hv(rng,hv_dim) for _ in range(max(4,themes//2))]
            caveat_themes=set(rng.choice(themes,size=5,replace=False).tolist())
            remaining=[t for t in range(themes) if t not in caveat_themes]
            contra_themes=set(rng.choice(remaining,size=3,replace=False).tolist())
            first_seen=set(); rows=[]; key_idx=[]; priority_idx=[]; boundaries=[]
            prev_theme=None
            for physical_sec, theme in enumerate(theme_order):
                if prev_theme is not None and theme != prev_theme:
                    boundaries.append(len(rows))
                prev_theme=theme
                first_for_theme=theme not in first_seen
                first_seen.add(theme)
                for j in range(units_per_section):
                    kind='body'; imp=0.42 + 0.10*rng.random()
                    if first_for_theme and j==0:
                        kind='key_claim'; imp=0.58
                    if first_for_theme and theme in caveat_themes and j==units_per_section-2:
                        kind='caveat'; imp=0.99
                    if first_for_theme and theme in contra_themes and j==units_per_section-1:
                        kind='contradiction'; imp=1.0
                    # One global conclusion at the very end.
                    if physical_sec==len(theme_order)-1 and j==units_per_section-1:
                        kind='conclusion'; imp=1.0
                    # Each head remains HDC-native. Topic carries the semantic region; claim/evidence
                    # add a role-specific perturbation while entity provides a separate address space.
                    base=theme_vec[theme]
                    topic=noisy(base,rng,0.060 if kind=='body' else (0.006 if kind=='key_claim' else 0.035))
                    claim=noisy(base,rng,0.055)
                    # Make priority roles semantically recognizable without changing their topic.
                    role=global_kind[kind]
                    evidence=np.where((base.astype(np.int16)*3 + role.astype(np.int16))>=0,1,-1).astype(np.int8)
                    evidence=noisy(evidence,rng,0.035)
                    entity=noisy(entity_vec[theme % len(entity_vec)],rng,0.035)
                    text=f'DOC {doc_id} THEME {theme} {kind.upper()} physical_section={physical_sec} unit={j}'
                    local_idx=len(rows)
                    slot=mem.add_unit(doc_id,text,{'topic':topic,'claim':claim,'entity':entity,'evidence':evidence,'role':noisy(role,rng,0.02)},
                                      ordinal=ordinal_global,section_id=physical_sec,kind=kind,importance=float(imp),
                                      claim_key=f'd{doc_id}-t{theme}',polarity=-1 if kind=='contradiction' else 1,
                                      extra={'theme_id':theme,'physical_section':physical_sec})
                    row={'slot':slot,'theme':theme,'kind':kind,'importance':float(imp),'text':text}
                    rows.append(row)
                    if kind=='key_claim': key_idx.append(local_idx)
                    if kind in {'caveat','contradiction','conclusion'}: priority_idx.append(local_idx)
                    ordinal_global += 1
            doc_rows[doc_id]=rows; key_by_doc[doc_id]=key_idx; priority_by_doc[doc_id]=priority_idx; true_boundaries[doc_id]=set(boundaries)
        ingest_s=time.perf_counter()-ingest_t0

        results={'hng':[],'lead':[],'uniform':[],'rag_topk':[],'rag_importance':[],'rag_mmr':[],'oracle_kmeans':[]}
        times={k:[] for k in results}; segment_f1=[]; examples=[]
        for doc_id in range(1,docs+1):
            records=mem.records(doc_id); rows=doc_rows[doc_id]
            slots=np.asarray([r.slot for r in records],np.intp)
            packed=mem.memory.vector_stores['topic'].read_slots(slots)
            proto=bundle_packed(packed,hv_dim)
            importance=np.asarray([r.importance for r in records],np.float32)

            t=time.perf_counter(); frame=mem.summarize_document(doc_id,budget_units=budget,discover_structure=True,priority_role_queries={x:global_kind[x] for x in ('caveat','contradiction','conclusion')},role_head='role',priority_similarity=.88); times['hng'].append(time.perf_counter()-t)
            local_by_slot={r.slot:i for i,r in enumerate(records)}
            hidx=np.asarray([local_by_slot[s] for s in frame.selected_slots],np.intp)
            results['hng'].append(metrics(hidx,rows,key_by_doc[doc_id],priority_by_doc[doc_id],themes))
            predicted={seg.start_ordinal - int(records[0].extra['ordinal']) for seg in frame.segments[1:]}
            truth=true_boundaries[doc_id]
            tp=len(predicted & truth); prec=tp/max(1,len(predicted)); rec=tp/max(1,len(truth)); segment_f1.append(2*prec*rec/max(1e-9,prec+rec))

            for name,fn in [
                ('lead',lambda:np.arange(min(budget, len(records)), dtype=np.intp)),
                ('uniform',lambda:np.unique(np.rint(np.linspace(0, len(records)-1, min(budget, len(records)))).astype(np.intp))),
                ('rag_topk',lambda:rag_topk(packed,proto,importance,budget,hv_dim,importance_weight=0.0)),
                ('rag_importance',lambda:rag_topk(packed,proto,importance,budget,hv_dim,importance_weight=0.20)),
                ('rag_mmr',lambda:rag_mmr(packed,proto,importance,budget,hv_dim)),
            ]:
                t=time.perf_counter(); idx=fn(); times[name].append(time.perf_counter()-t)
                results[name].append(metrics(idx,rows,key_by_doc[doc_id],priority_by_doc[doc_id],themes))

            # Strong non-LLM hierarchy baseline: KMeans gets the *oracle* number of semantic
            # regions. It uses the same packed HDC topic states after unpacking, then chooses
            # a medoid-like central unit per cluster plus the same HDC role-detected priority
            # evidence. This tests whether HNG is doing more than trivial diversity sampling.
            t=time.perf_counter()
            x=(np.unpackbits(packed,axis=1,bitorder='little',count=hv_dim).astype(np.float32)*2.0)-1.0
            km=KMeans(n_clusters=themes,n_init=1,max_iter=30,random_state=doc_id,algorithm='lloyd').fit(x)
            chosen=set()
            for c in range(themes):
                members=np.flatnonzero(km.labels_==c)
                if members.size:
                    dist=((x[members]-km.cluster_centers_[c])**2).sum(axis=1)
                    chosen.add(int(members[int(np.argmin(dist))]))
            role_packed=mem.memory.vector_stores['role'].read_slots(slots)
            pmask=np.zeros(len(records),dtype=bool)
            for kind_name in ('caveat','contradiction','conclusion'):
                pmask |= hamming_similarity(role_packed,pack_hv(global_kind[kind_name],hv_dim),hv_dim)>=.88
            chosen.update(int(i) for i in np.flatnonzero(pmask))
            if len(chosen)<budget:
                remaining=[i for i in np.argsort(importance)[::-1] if int(i) not in chosen]
                chosen.update(int(i) for i in remaining[:budget-len(chosen)])
            kidx=np.asarray(list(chosen)[:budget],dtype=np.intp)
            times['oracle_kmeans'].append(time.perf_counter()-t)
            results['oracle_kmeans'].append(metrics(kidx,rows,key_by_doc[doc_id],priority_by_doc[doc_id],themes))
            if doc_id==1:
                examples.append({'hng_context':frame.to_context_text(max_chars=6000),'segments':len(frame.segments),'threshold':frame.boundary_threshold})

        # Targeted document Q&A: topic + entity conjunctive query vs a single bundled/composite top-k.
        mem.rebuild_index()
        qa_total=0; hng_ok=0; composite_ok=0; hng_q_ms=[]; composite_q_ms=[]
        for doc_id in range(1,min(docs,16)+1):
            records=mem.records(doc_id); rows=doc_rows[doc_id]; slots=np.asarray([r.slot for r in records],np.intp)
            for theme in range(themes):
                target=[i for i,r in enumerate(rows) if r['theme']==theme and r['kind']=='key_claim']
                if not target: continue
                target_slot=rows[target[0]]['slot']; rec=records[target[0]]
                # Query from the target's native states with independent noise.
                topic=mem.memory.vector_stores['topic'].read_slots(np.asarray([target_slot],np.intp))[0]
                entity=mem.memory.vector_stores['entity'].read_slots(np.asarray([target_slot],np.intp))[0]
                topic_hv=noisy(np.where(np.unpackbits(topic,bitorder='little',count=hv_dim)>0,1,-1).astype(np.int8),rng,.04)
                entity_hv=noisy(np.where(np.unpackbits(entity,bitorder='little',count=hv_dim)>0,1,-1).astype(np.int8),rng,.04)
                t=time.perf_counter(); rr=mem.query_document(doc_id,{'topic':topic_hv,'entity':entity_hv},top_k=5,min_similarity={'topic':.78,'entity':.78},required_route_heads=('topic','entity'),probe_radius=1); hng_q_ms.append((time.perf_counter()-t)*1000)
                if any(h.slot==target_slot for h in rr.hits): hng_ok += 1
                # Composite baseline: bundle query heads and each record's two heads, exact scan.
                t=time.perf_counter()
                tpack=mem.memory.vector_stores['topic'].read_slots(slots); epack=mem.memory.vector_stores['entity'].read_slots(slots)
                tbits=np.unpackbits(tpack,axis=1,bitorder='little',count=hv_dim).astype(np.int8)*2-1
                ebits=np.unpackbits(epack,axis=1,bitorder='little',count=hv_dim).astype(np.int8)*2-1
                composites=np.where(tbits.astype(np.int16)+ebits.astype(np.int16)>=0,1,-1).astype(np.int8)
                qp=np.where(topic_hv.astype(np.int16)+entity_hv.astype(np.int16)>=0,1,-1).astype(np.int8)
                cp=np.packbits(composites>0,axis=1,bitorder='little'); sims=hamming_similarity(cp,pack_hv(qp,hv_dim),hv_dim)
                ii=np.argpartition(sims,-5)[-5:]; composite_q_ms.append((time.perf_counter()-t)*1000)
                if target[0] in ii: composite_ok += 1
                qa_total += 1

    def agg(method):
        rows=results[method]
        return {k:float(np.mean([x[k] for x in rows])) for k in ['theme_coverage','key_claim_recall','priority_recall','contradiction_recall','redundancy_fraction']} | {
            'median_ms':float(np.median(np.asarray(times[method])*1000)),
            'p95_ms':float(np.percentile(np.asarray(times[method])*1000,95)),
        }
    summary={
        'config':{'documents':docs,'hv_dim':hv_dim,'themes_per_document':themes,'units_per_section':units_per_section,'summary_budget_units':budget,'total_records':sum(len(v) for v in doc_rows.values())},
        'ingest_seconds':ingest_s,
        'summary':{m:agg(m) for m in results},
        'hng_structure_boundary_f1':float(np.mean(segment_f1)),
        'targeted_qa':{
            'queries':qa_total,'hng_multihead_recall_at5':hng_ok/qa_total,'composite_exact_recall_at5':composite_ok/qa_total,
            'hng_median_ms':float(np.median(hng_q_ms)),'composite_median_ms':float(np.median(composite_q_ms)),
        },
        'example':examples[0],
    }
    return summary


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='/mnt/data/hng_doc_breakthrough'); ap.add_argument('--out',default=''); ap.add_argument('--docs',type=int,default=32); args=ap.parse_args()
    res=run(Path(args.root),docs=args.docs)
    text=json.dumps(res,indent=2); print(text)
    if args.out: Path(args.out).write_text(text)

if __name__=='__main__': main()
