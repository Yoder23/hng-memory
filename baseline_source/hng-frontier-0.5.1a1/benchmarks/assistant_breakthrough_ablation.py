from __future__ import annotations
import json, shutil, time
from pathlib import Path
import numpy as np
from hngfrontier import AssistantMemory, MemoryFilter, WorkingUpdate
from hngfrontier.vectors import hamming_similarity, pack_hv

D=2048; CONTEXTS=128; VARIANTS=16; ACTION_FAMILIES=256; ROOT=Path('/mnt/data/hng_assistant_ablation_04')

def mutate(bits,rng,p):
 out=bits.copy(); m=rng.random(bits.size)<p; out[m]^=1; return out

def bipolar(bits): return bits.astype(np.int8)*2-1

def main():
 if ROOT.exists(): shutil.rmtree(ROOT)
 rng=np.random.default_rng(440)
 # Hard-neighbor semantic families.
 state_base=rng.integers(0,2,size=(16,D),dtype=np.uint8); goal_base=rng.integers(0,2,size=(8,D),dtype=np.uint8); entity_base=rng.integers(0,2,size=(32,D),dtype=np.uint8); seq_base=rng.integers(0,2,size=(16,D),dtype=np.uint8)
 contexts=[]
 for c in range(CONTEXTS):
  contexts.append({
   'state':mutate(state_base[c//8],np.random.default_rng(1000+c),.07),
   'goal':mutate(goal_base[c//16],np.random.default_rng(2000+c),.06),
   'entity':mutate(entity_base[c%32],np.random.default_rng(3000+c),.05),
   'sequence':mutate(seq_base[(c*7)%16],np.random.default_rng(4000+c),.08),
  })
 action_base=rng.integers(0,2,size=(ACTION_FAMILIES,D),dtype=np.uint8); action_bits=np.empty((ACTION_FAMILIES*VARIANTS,D),np.uint8)
 for f in range(ACTION_FAMILIES):
  for v in range(VARIANTS): action_bits[f*VARIANTS+v]=mutate(action_base[f],np.random.default_rng(500000+f*100+v),.05)
 action_packed=np.packbits(action_bits,axis=1,bitorder='little')
 correct=np.asarray([(c*7+3)%VARIANTS + c*VARIANTS for c in range(CONTEXTS)],dtype=np.intp)
 heads=('state','goal','entity','sequence','action','next_state')
 opts={'table_count':10,'bits_per_table':11,'sketch_bits':192}
 ingest=0
 with AssistantMemory(ROOT,hv_dim=D,space_id='assistant-ablation-v1',heads=heads,auto_index=False,index_options=opts) as mem:
  t=time.perf_counter()
  for c in range(CONTEXTS):
   h={k:bipolar(v) for k,v in contexts[c].items()}
   # Four successes for the exact action and one negative for a close sibling.
   for rep in range(4):
    aid=int(correct[c]); mem.record_transition(h|{'action':bipolar(action_bits[aid]),'next_state':bipolar(mutate(contexts[c]['state'],np.random.default_rng(600000+c*10+rep),.02))},f'context {c} success {rep}',conversation_id=10_000+c*10+rep,episode_id=1,action=f'action-{aid}',outcome='success',outcome_score=1.0,namespace='history')
   bad=int(c*VARIANTS+((correct[c]-c*VARIANTS+1)%VARIANTS)); mem.record_transition(h|{'action':bipolar(action_bits[bad]),'next_state':bipolar(contexts[c]['state'])},f'context {c} failed sibling',conversation_id=20_000+c,episode_id=1,action=f'action-{bad}',outcome='failed',outcome_score=-1.0,namespace='history')
  ingest=time.perf_counter()-t; mem.rebuild_index()
  raw=0; hng=0; cross=0; raw_ms=[]; hng_ms=[]
  for c in range(CONTEXTS):
   family=c; qfam=bipolar(action_base[family]);
   t=time.perf_counter(); sims=hamming_similarity(action_packed,pack_hv(qfam,D),D); top=int(np.argmax(sims)); raw_ms.append((time.perf_counter()-t)*1000); raw += int(top==int(correct[c]))
   q={k:bipolar(mutate(v,np.random.default_rng(700000+c*10+i),.03)) for i,(k,v) in enumerate(contexts[c].items())}
   t=time.perf_counter(); recs=mem.recommend_actions(q,conversation_id=90_000+c,max_actions=5,top_k_memories=48,memory_filter=MemoryFilter(namespace='history'),semantic_floor=.80); hng_ms.append((time.perf_counter()-t)*1000)
   if recs:
    aid=int(recs[0].label.split('-')[1]); hng += int(aid==int(correct[c])); cross += int(mem.memory.db.get(recs[0].slots[0]).conversation_id != 90_000+c)

  # Ambiguous second-turn continuity. Current utterance carries no useful topic signal.
  ambiguous_raw=0; carried=0
  junk=rng.integers(0,2,size=(CONTEXTS,D),dtype=np.uint8)
  for c in range(CONTEXTS):
   cid=100_000+c
   h={k:bipolar(v) for k,v in contexts[c].items()}
   mem.record_transition(h|{'next_state':bipolar(contexts[c]['state'])},f'live chat {c} establishes state',conversation_id=cid,episode_id=1,working_update=WorkingUpdate(set_goal=f'goal-{c}'))
   # No-memory retrieval from an unrelated ambiguous cue.
   rr=mem.memory.recall({'state':bipolar(junk[c])},top_k=1,memory_filter=MemoryFilter(namespace='history'))
   if rr.hits: ambiguous_raw += int(rr.hits[0].record.source.startswith(f'context {c} '))
   current=mem.current_semantic_heads(cid)
   rr=mem.memory.recall({'state':current['state'],'goal':current['goal'],'entity':current['entity'],'sequence':current['sequence']},top_k=5,memory_filter=MemoryFilter(namespace='history'),min_similarity={'state':.80,'goal':.80,'entity':.80,'sequence':.80},required_route_heads=('state','goal','entity','sequence'))
   carried += int(any(x.record.source.startswith(f'context {c} ') for x in rr.hits))
  out={'config':{'contexts':CONTEXTS,'hv_dim':D,'action_library':ACTION_FAMILIES*VARIANTS,'variants_per_family':VARIANTS},'history_ingest_seconds':ingest,'action_routing':{'raw_hdc_top1':raw/CONTEXTS,'hng_history_top1':hng/CONTEXTS,'hng_cross_chat_evidence_rate':cross/CONTEXTS,'raw_action_scan_median_ms':float(np.median(raw_ms)),'hng_recommend_median_ms':float(np.median(hng_ms))},'turn_continuity':{'ambiguous_current_turn_only':ambiguous_raw/CONTEXTS,'hng_carried_state':carried/CONTEXTS}}
 Path('/mnt/data/hng-frontier-0.4.0a1/benchmarks/ASSISTANT_ABLATION.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=='__main__': main()
