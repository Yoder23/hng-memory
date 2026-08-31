# HNG reproduction

## Frozen artifact

- Package: `hng-frontier` 0.5.1a1 (`pyproject.toml`), while several documents still say 0.5.0a1.
- Source ZIP SHA-256: `BD01373215D08FE71D038A10110240C9EFB0BE6A1E127614FCBA0F5DAFC5E881`.
- Wheel SHA-256: `5D86C06F25BAD6F4BD756D94F0B588BD59544A1A322D7C966B0F9D2EC145B61D`.
- The wheel nested in the source ZIP is byte-identical.
- This directory is not a Git repository; no commit/hash can be reported.
- No runnable 0.3.1 source/wheel is bundled. Only historical JSON/Markdown artifacts exist, so the requested unchanged two-version rerun was impossible.

## Architecture found

SQLite is authoritative for records/metadata; each semantic head is stored as packed segmented NumPy slabs. Each head has a disposable multi-table bit-sampling index with a 256-bit sketch. Retrieval unions per-head routed candidates, optionally requires route agreement, applies exact metadata eligibility, shortlists by sketch fusion, then recomputes full-HV Hamming similarity and applies per-head floors. Working memory replays committed SQLite updates. Perspective access and actor eligibility are non-semantic filters. Document structure is inferred from the largest gap in adjacent topic-HV similarities.

## Regression table

| Check | Shipped claim/artifact | Fresh result | Verdict |
|---|---:|---:|---|
| Source tests | 30/30 | 30/30 in 3.63 s | Reproduced |
| Examples unchanged | Runnable | 3/3 fail on Windows `/tmp` path | Portability failure |
| Examples path-adapted | n/a | 3/3 pass | Behavior reproduced |
| Cross-chat episode recall | 100% | 100% | Reproduced |
| Historical action top-1 | 100% | 100% | Reproduced |
| Carried-state ambiguous continuity | 100% | 100%; retrieval-only 0% | Reproduced; state carry causes gain |
| Changed-sequence routing | 100% when supplied | 100%; obsolete-action rate without sequence 100% | Reproduced with crucial caveat |
| Action support/challenge/unknown | 100% | 100% | Reproduced |
| Action accuracy at 15% noise | 100% | **98.958%** | Not reproduced |
| Restart recovery | 100% | 100% in no-op-fsync behavioral run | Behavioral only |
| Perspective conditioned top-1 | 100% | 100% | Reproduced |
| Raw perspective action router | 6.25% | **7.2266%** | Artifact mismatch |
| Perspective violations | 0% vs 75% | 0% vs 75% | Reproduced |
| Synthetic document coverage | 100/98/100/100% | 100/98.05/100/100% | Reproduced |
| Synthetic document boundary F1 | 1.00 | 1.00 | Reproduced |
| Synthetic HNG synopsis median | ~23.6 ms claimed | 117.4 ms fresh shipped run | Not reproduced on this machine |

The unchanged `assistant_readiness.py`, `turn_stream.py`, and full `assistant_gauntlet.py` fail on Windows at `vectors.py:209` with `OSError: [Errno 9] Bad file descriptor` from `os.fsync(fd)`. Secondary runs with an explicit Windows `os.fsync = no-op` shim completed; these validate behavioral logic only, not crash durability.

The normal wheel install correctly refuses Python 3.10 because the package declares Python >=3.11. With `--ignore-requires-python`, the wheel imports as 0.5.1a1. A compliant interpreter was unavailable, so strict wheel validation is incomplete rather than failed.

Core HNG algorithms remained untouched throughout the baseline verdict. All path adapters, compatibility shims, competitors, and reporting code live under `research_eval/`; the preserved raw outputs distinguish untouched failures from adapted behavioral runs.
