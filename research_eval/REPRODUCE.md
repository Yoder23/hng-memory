# Reproduce

Run commands from the release root with `C:\Python310\python.exe`. The package declares Python >=3.11; Python 3.10 was used only because it was the sole installed interpreter and the source is syntactically compatible.

```powershell
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'

& 'C:\Python310\python.exe' -m pytest -q -p no:cacheprovider `
  --rootdir '.\baseline_source\hng-frontier-0.5.1a1'

& 'C:\Python310\python.exe' '.\research_eval\scripts\run_shipped_portable.py' --quick
& 'C:\Python310\python.exe' '.\research_eval\scripts\run_windows_nondurable_gauntlets.py'
& 'C:\Python310\python.exe' '.\research_eval\scripts\adversarial_memory.py'
& 'C:\Python310\python.exe' '.\research_eval\scripts\perspective_standard_baseline.py'
& 'C:\Python310\python.exe' '.\research_eval\scripts\document_equal_information.py'

& 'C:\Python310\python.exe' '.\research_eval\scripts\qmsum_fair_baselines.py' `
  '.\research_eval\external\QMSum\data\ALL\jsonl\test.jsonl' --limit 20

& 'C:\Python310\python.exe' '.\research_eval\scripts\retrieval_kernel_benchmark.py' `
  --scales 100000 --dim 4096 --queries 80
& 'C:\Python310\python.exe' '.\research_eval\scripts\retrieval_kernel_benchmark.py' `
  --scales 1000000 --dim 4096 --queries 30
& 'C:\Python310\python.exe' '.\research_eval\scripts\retrieval_10m_attempt.py'

& 'C:\Python310\python.exe' '.\research_eval\scripts\compile_results.py'
```

`run_shipped_portable.py` writes the exact path-adapted source under `scripts/adapted_shipped/` and a replacement manifest under `raw/`. `run_windows_nondurable_gauntlets.py` is not a durability test; it explicitly disables `fsync` only to reach later behavioral checks after preserving the untouched failure.

The 10M command requires roughly 16.4 GB peak process RSS in this configuration. The official QMSum checkout is commit `83d7768c1f2b4dfeb091385d3dc7e239b8e5bb7e` under `research_eval/external/QMSum`; dataset content is not copied into result files.
