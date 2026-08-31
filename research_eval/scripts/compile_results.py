from __future__ import annotations
import csv,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];RAW=ROOT/'research_eval/raw'
def load(name):return json.loads((RAW/name).read_text(encoding='utf-8'))
rows=[]
def add(tier,track,benchmark,method,metric,value,unit='',status='executed',note=''):rows.append(dict(tier=tier,track=track,benchmark=benchmark,method=method,metric=metric,value=value,unit=unit,status=status,note=note))
g=load('assistant_gauntlet_windows_nondurable/ASSISTANT_GAUNTLET.json')
for metric,value in [('cross_chat_episode_recall',g['cross_chat_and_action_routing']['cross_chat_episode_recall']),('historical_action_top1',g['cross_chat_and_action_routing']['hng_action_top1']),('carried_state_accuracy',g['multi_turn']['hng_carried_state_accuracy']),('changed_sequence_accuracy',g['stale_index_temporal_conflict']['sequence_aware_new_action_accuracy']),('noise_15pct_accuracy',g['noise_stress']['15pct']['accuracy']),('restart_action_accuracy',g['restart']['cross_chat_action_accuracy'])]:add('A','phase0','assistant_gauntlet_windows_nondurable','HNG',metric,value,'fraction',note='Behavioral run with Windows fsync no-op; durability not validated.')
p=load('perspective_gauntlet.results.json');add('A','B','shipped_perspective','HNG full','action_top1',p['main']['perspective_conditioned_top1'],'fraction');add('A','B','shipped_perspective','HNG full','role_violation_rate',p['main']['perspective_role_violation_rate'],'fraction')
pb=load('perspective_standard_baseline.results.json')
for method,v in pb['results'].items():add('A','B','shipped_perspective',method,'action_top1',v['accuracy'],'fraction')
for filename in ('retrieval_kernel_100k.results.json','retrieval_kernel_1m.results.json'):
 d=load(filename)
 for z in d['results']:
  b=f"{z['config']['n']}_{z['config']['geometry']}";add('A','C',b,'HNG','top1_agreement',z['hng']['exact_top1_agreement'],'fraction');add('A','C',b,'HNG','median_latency',z['hng']['median_ms'],'ms')
  matched=[(int(k),v) for k,v in z['faiss_binary_ivf']['runs'].items() if v['exact_top1_agreement']>=z['hng']['exact_top1_agreement']]
  if matched:
   npb,v=min(matched,key=lambda x:x[1]['median_ms']);add('A','C',b,f'FAISS BinaryIVF nprobe={npb}','top1_agreement',v['exact_top1_agreement'],'fraction');add('A','C',b,f'FAISS BinaryIVF nprobe={npb}','median_latency',v['median_ms'],'ms')
q=load('qmsum_fair_20.results.json')
for method,v in q['summary'].items():
 for metric,value in v.items():add('B','D','QMSum_test_first20',method,metric,value,'fraction')
for method,v in q['specific_query'].items():add('B','D','QMSum_test_first20',method,'specific_span_hit_at_5',v['span_hit_at_5'],'fraction')
a=load('adversarial.results.json')
for c in a['cases']:add('A','adversarial','synthetic_adversaries','HNG',c['case'],1 if c['passed'] else 0,'pass_bool',note=f"actual={c['actual']}; expected={c['safe_expected']}")
if (RAW/'retrieval_kernel_10m.results.json').exists():
 d=load('retrieval_kernel_10m.results.json')
 for method,v in [('HNG',d['hng']),('FAISS BinaryIVF nprobe=16',d['faiss_ivf']['runs']['16'])]:
  add('A','C','10000000_independent',method,'top1_agreement',v['top1_agreement'],'fraction')
  for metric in ('median_ms','p95_ms','p99_ms'):add('A','C','10000000_independent',method,metric,v[metric],'ms')
out={'artifact_version':'0.5.1a1','source_git_commit':None,'research_cutoff':'2026-08-31','overall_conclusion':'C - Valuable specialized system','tier_definitions':{'A':'executed locally','B':'official public benchmark reproduced','C':'literature only; excluded from comparable rows'},'rows':rows}
(ROOT/'research_eval/RESULTS.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
with (ROOT/'research_eval/RESULTS.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print(f'wrote {len(rows)} result rows')
