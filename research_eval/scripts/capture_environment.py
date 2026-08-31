from __future__ import annotations
import importlib.metadata as md,json,os,platform,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
packages={name:(md.version(name) if name in {d.metadata.get('Name') for d in md.distributions()} else None) for name in ('numpy','pytest','scikit-learn','scipy','pandas','psutil')}
vendor={}
sys.path.insert(0,str(ROOT/'research_eval/vendor'))
for name in ('faiss-cpu','usearch'):
 try:vendor[name]=md.version(name)
 except md.PackageNotFoundError:vendor[name]=None
out={'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'compiler':platform.python_compiler(),'packages':packages,'isolated_vendor_packages':vendor,'thread_environment':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},'artifact_sha256':{'source_zip':'BD01373215D08FE71D038A10110240C9EFB0BE6A1E127614FCBA0F5DAFC5E881','wheel':'5D86C06F25BAD6F4BD756D94F0B588BD59544A1A322D7C966B0F9D2EC145B61D'}}
path=ROOT/'research_eval/raw/environment_python.json';path.write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
