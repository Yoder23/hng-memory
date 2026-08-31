"""Run durability-calling gauntlets with an explicit Windows fsync no-op shim.

Untouched runs are the authoritative portability result and fail with EBADF.
These secondary runs are behavioral-only: they do not validate durability.
"""
from pathlib import Path
import sys
from run_shipped_portable import adapt, py_path, RAW, RUNS

SHIM="import time\nimport os\nif os.name == 'nt': os.fsync = lambda fd: None  # behavioral compatibility only\n"

def main():
    specs=[
      ("assistant_readiness_windows_nondurable","benchmarks/assistant_readiness.py",{
        "import time\n":SHIM,
        "Path('/mnt/data/hng_frontier_03_bench')":py_path(RUNS/"assistant_readiness_compat"),
        "Path('/mnt/data/hng-frontier-0.3.0a1/benchmarks/ASSISTANT_READINESS.json')":py_path(RAW/"assistant_readiness_windows_nondurable.results.json")},[]),
      ("turn_stream_windows_nondurable","benchmarks/turn_stream.py",{
        "import json, shutil, statistics, time\n":"import json, shutil, statistics, time\nimport os\nif os.name == 'nt': os.fsync = lambda fd: None  # behavioral compatibility only\n",
        "Path('/mnt/data/hng_frontier_03_stream')":py_path(RUNS/"turn_stream_compat"),
        "Path('/mnt/data/hng-frontier-0.3.0a1/benchmarks/TURN_STREAM.json')":py_path(RAW/"turn_stream_windows_nondurable.results.json")},[]),
      ("assistant_gauntlet_windows_nondurable","benchmarks/assistant_gauntlet.py",{
        "import time\n":SHIM,
        "Path('/mnt/data/hng-frontier-0.4.0a1/benchmarks')":py_path(RAW/"assistant_gauntlet_windows_nondurable")},["--root",str(RUNS/"assistant_gauntlet_compat")]),
    ]
    results=[adapt(*x) for x in specs]
    return 0 if all(x["exit_code"]==0 for x in results) else 1
if __name__=="__main__":raise SystemExit(main())
