from __future__ import annotations
import json, shutil, statistics, time
import os
if os.name == 'nt': os.fsync = lambda fd: None  # behavioral compatibility only
from pathlib import Path
import numpy as np
from hngfrontier import AssistantMemory, WorkingItemSpec, WorkingUpdate

DIM=2048; N=5000
rng=np.random.default_rng(123)
pool=[rng.choice(np.array([-1,1],dtype=np.int8), size=DIM) for _ in range(32)]
def hs(i):
    return {"state":pool[(i+0)%32],"goal":pool[(i+1)%32],"entity":pool[(i+2)%32],"sequence":pool[(i+3)%32],
            "action":pool[(i+4)%32],"outcome":pool[(i+5)%32],"next_state":pool[(i+6)%32]}
root=Path('C:\\Python310\\hng-frontier-0.5.1a1-release\\hng-frontier-0.5.1a1-release\\research_eval\\run_data\\turn_stream_compat'); shutil.rmtree(root,ignore_errors=True)
lat=[]
with AssistantMemory(root,hv_dim=DIM,space_id='stream',auto_index=False,recent_limit=8) as m:
    t_all=time.perf_counter()
    for i in range(N):
        upd=WorkingUpdate(set_goal='long task' if i==0 else None)
        t=time.perf_counter(); m.record_transition(hs(i),f'turn {i}',conversation_id=1,episode_id=1,working_update=upd); lat.append((time.perf_counter()-t)*1000)
    total=time.perf_counter()-t_all
    state=m.working_state(1); recent=m.working.recent_records(1)
    m.sync()
t=time.perf_counter()
with AssistantMemory(root,hv_dim=DIM,space_id='stream',auto_index=False,recent_limit=8) as m:
    restart_state=m.working_state(1)
restart_ms=(time.perf_counter()-t)*1000
res={"turns":N,"writes_per_second":N/total,"median_append_ms":statistics.median(lat),"p95_append_ms":float(np.percentile(lat,95)),
     "live_turn_index":state.turn_index,"recent_count":len(recent),"restart_replay_ms":restart_ms,"restart_turn_index":restart_state.turn_index}
Path('C:\\Python310\\hng-frontier-0.5.1a1-release\\hng-frontier-0.5.1a1-release\\research_eval\\raw\\turn_stream_windows_nondurable.results.json').write_text(json.dumps(res,indent=2,sort_keys=True))
print(json.dumps(res,indent=2,sort_keys=True))
