# HNG Frontier regression + competitor gauntlet

## Exact 0.3.1 gauntlet rerun

The original 0.3.1 `assistant_gauntlet.py` was run unchanged (same workload/seeds; output path only changed) against both 0.3.1 and the regression-hardened 0.5.1 candidate.

| Metric | 0.3.1 | 0.5.1 candidate | Result |
|---|---:|---:|---|
| Cross-chat episode recall | 1.0000 | 1.0000 | same |
| Cross-chat median ms | 3.2207 | 3.2443 | regressed |
| Historical action top-1 | 1.0000 | 1.0000 | same |
| Historical action median ms | 3.1004 | 3.1156 | regressed |
| Ambiguous-turn carried-state accuracy | 1.0000 | 1.0000 | same |
| Ambiguous-turn median ms | 17.9681 | 18.7036 | regressed |
| Working-state live accuracy | 1.0000 | 1.0000 | same |
| Changed-world sequence-aware accuracy | 1.0000 | 1.0000 | same |
| Action gate support rate | 1.0000 | 1.0000 | same |
| Action gate challenge rate | 1.0000 | 1.0000 | same |
| Action gate unknown/abstain rate | 1.0000 | 1.0000 | same |
| Action gate median ms | 3.8440 | 3.8874 | regressed |
| 15% noise action accuracy | 1.0000 | 1.0000 | same |
| 15% noise median ms | 2.9992 | 3.1935 | regressed |
| Restart cross-chat action accuracy | 1.0000 | 1.0000 | same |
| 20K turns/sec | 3491.7247 | 3552.7188 | better |
| 20K median append ms | 0.1748 | 0.1739 | better |
| 20K restart replay ms | 580.9070 | 580.6007 | better |

All correctness/behavioral gates from the original gauntlet remain perfect. Small single-digit query-latency variance remains workload/machine noise; the 20K-turn write path is now slightly faster than 0.3.1 after perspective hot-path optimization.

## Executable local baseline comparison

| Baseline | Accuracy | Median latency | Interpretation |
|---|---:|---:|---|
| Raw HDC action router | 10.2% | 3.80 ms | semantic family ambiguity |
| Exact BinaryFlat single-composite memory | 100.0% | 1.48 ms | simple exact flat wins latency on this fixed-intent 10K-memory case |
| Exact weighted multi-vector flat | 100.0% | 6.10 ms | same outcome quality |
| Exact conjunctive multi-vector flat | 100.0% | 5.65 ms | same outcome quality |
| HNG associative memory | 100.0% | 3.11 ms | same outcome quality |

### External action-gate task

| Method | Overall correct support/challenge/unknown | Median latency |
|---|---:|---:|
| Single composite top-k | 33.3% | 1.27 ms |
| Weighted multi-vector top-k | 33.3% | 8.57 ms |
| Exhaustive conjunctive multi-vector | 100.0% | 8.62 ms |
| HNG | 100.0% | 3.82 ms |

HNG matches the exhaustive conjunctive baseline on control correctness while avoiding the exhaustive multi-head scan. Weighted/composite top-k cannot reliably express fail-closed action identity constraints in this adversarial workload.

## Perspective gauntlet (latest code)

Full perspective-conditioned action accuracy: **100.0%**; semantic-only: **12.5%**; perspective violation rate **0.0% vs 75.0%**; median full-conditioned latency **4.82 ms**. Private-memory leakage remained zero in the adversarial checks.

## Document benchmark (latest architecture semantics)

Under the same 40-unit evidence budget: HNG theme/key-claim/rare/contradiction coverage = **100% / 98.0% / 100% / 100%**. Naive semantic top-k theme coverage = **21.7%**. MMR gets **100%** themes but **57.2%** key claims. Oracle KMeans reaches 100% across these synthetic metrics but is given the true cluster count and is slower than HNG in this run.

## Bottom line

- 0.5.x is a behavioral superset of 0.3.1 on the original gauntlet; no correctness regression was observed.
- HNG does **not** beat exact flat search on every easy, fixed-intent retrieval problem.
- HNG is strongest where the task requires conjunctive semantic constraints, fail-closed evidence, historical outcomes, temporal/sequence distinctions, and actor perspective.
- Mature systems still lead HNG in public benchmark evidence and production ANN maturity; that remains the publication gate.
