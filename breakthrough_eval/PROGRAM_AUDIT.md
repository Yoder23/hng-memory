# Breakthrough program completion audit

Audit basis: the original 51-section program, frozen baseline commit
`e57db1b1e92329e9b8f2b173be9a506d2b898da8`, and current worktree evidence. Status is
conservative: `PASS` means the named requirement is evidenced at its requested scope;
`PARTIAL` means useful evidence exists but the requirement is not fully met;
`BLOCKED_EXTERNAL` means the necessary real system/data/model is absent and no synthetic
substitute is permitted; `NOT_RUN` means no qualifying evidence yet exists.

## Core requirements and gates

| Section | Requirement | Status | Authoritative evidence or remaining gap |
|---:|---|---|---|
| 0 | Central evidence-governance hypothesis | PARTIAL | Pinned Qwen/Mistral studies now replicate governed/structured-context gains on a disjoint 30-case window with balanced arm order, but HNG ties StrongStructuredBaseline exactly in both readers. |
| 1 | Downstream breakthrough evidence | PARTIAL | LLM corrupted-evidence behavior improves; no real-assistant or qualifying public win. |
| 2 | Exactly one final S/A/B/C/D verdict | NOT_RUN | Verdict is intentionally withheld until the completion audit closes. |
| 3 | Research-integrity controls | PARTIAL | Frozen candidates/model/prompt, raw append-only logs, preserved losses, explicit evidence classes, and a cross-study input-identifiability audit are present; broader tracks remain. |
| 4 | Immutable 0.7.0rc1 freeze | PASS | `baseline_070/BASELINE_MANIFEST.json`, raw logs, environment, shipped evidence, exact detached commit. |
| 5 | Current prior art | PARTIAL | `PRIOR_ART_2026.md` covers all named areas and newer systems; not every unavailable system is reproduced. |
| 6 | Universal experiment harness | PARTIAL | Standard specs/events and all requested local adapter classes exist; runnable external-system adapters remain unavailable. |
| 7 | Real HDC assistant HNG off/on | BLOCKED_EXTERNAL | A machine-readable fail-closed readiness gate records 21 unmet artifact, digest, design, metric, and sample checks in `real_hdc/READINESS.json`. No trained production interpreter, frozen action library, real trace corpus, or integrated assistant is present; readiness is not behavioral evidence. |
| 8 | Fixed LLM memory comparison | PARTIAL | Pinned Qwen 27B and Mistral 24B readers run ordinary/Strong/HNG on both the original and a disjoint 30-case window; the latter balances all six arm orders. Both readers show HNG=Strong; recent/full/summary/dense arms are not all run. |
| 9 | Official LongMemEval-V2 | PARTIAL | Official pinned small text tier is validated and the 21-question noncanonical pilot completed 84/84 evaluations with zero failures. HNG, StrongStructuredBaseline, and BM25 tie at 4/21; visual/full official stack and contemporary-system comparison are absent. |
| 10 | Official LoCoMo/LoCoMo-Plus | PARTIAL | The official 2,387-sample input is pinned. Four disjoint 30-sample windows now cover fixed, budget, dense/hybrid, and neural-reranker studies. The fourth completes 210/210 events with zero failures: full context 17.5/30, hybrid 15/30, reranked 14.5/30, dense 13.5/30, and BM25 12/30. Primary reranker/hybrid CI includes zero; HNG, Strong, and reranked exactly tie. Protocols remain noncanonical and contemporary-system comparison is absent. |
| 11 | Public personalization | PARTIAL | Official PersonaMem-v2 text data are pinned and validated: 5,000 rows, all 1,998 32K files, 200 referenced histories, zero missing. The seven-stratum local pilot completes 49/49 qualified evaluations; HNG, BM25, Strong, and full history tie at 4/7. Dense and agentic baselines are absent. |
| 12 | Strong RAG plus HNG | PARTIAL | Genuine BM25, Qwen3 dense, RRF hybrid, and pinned Qwen3 cross-encoder reranking now run on disjoint preregistered public-data holdouts. On the reranker window, reranked loses descriptively to hybrid (14.5/30 vs 15/30; CI includes zero), and HNG, Strong, and plain reranked exactly tie. The local strong-RAG matrix exists, but contemporary end-to-end systems remain missing. |
| 13 | Public document knowledge | PARTIAL | QMSum loss is preserved; GovReport/BillSum and post-retrieval governance tasks are missing. |
| 14 | Public-quality action experience | PARTIAL | A packaged 100-attempt synthetic executing simulator reports success, regret, repeated failure, abstention, adaptation, and seven arms using production HNG evaluation. HNG ties structured/graph/Strong and loses to nearest experience (68% vs 75%); no public tool environment is run. |
| 15 | At least 250 adversarial scenarios | PARTIAL | Exactly 250 deterministic scenarios across ten families exist; calibration exists, but combinations and labels are synthetic. |
| 16 | Belief revision timelines | PARTIAL | 100 five-event synthetic timelines exercise the shipped belief store against naive, append-only, temporal, and strong structured arms. HNG reaches 100% but ties the strong authority policy; the harness supplies that policy and no real assistant is tested. |
| 17 | Cross-session experience accumulation | PARTIAL | Fixed-weight 100-attempt curves show HNG rising from 35% in attempts 1-20 to 100% in 81-100 after an environment-change dip. The result is synthetic, and nearest experience has higher total success. |
| 18 | Matched HDC versus dense heads | NOT_RUN | No real matched downstream study; synthetic vectors cannot satisfy the HDC gate. |
| 19 | Retrieval infrastructure | PARTIAL | BinaryFlat/IVF/HNSW/provider evidence at 100K/1M/10M exists; USearch and matched recall are not complete at every scale. |
| 20 | Governed-memory scaling | PARTIAL | 10K-10M retrieval/provider evidence exists; full governance breakdown, updates/rebuilds, and 100M are absent. |
| 21 | Tool-agent advisory evaluation | PARTIAL | A 108-episode executing synthetic environment compares agent alone, ordinary recent memory, StrongStructuredBaseline, and production HNG advisory under mutation, failures, irreversible effects, API changes, conflicting observations, and roles. A failure-driven context fix moves HNG from 29.6% with 18 irreversible mistakes to 63.9% with zero, exactly tying Strong at higher latency. No public or real agent is tested. |
| 22 | Multi-user/multi-tenant scale | PARTIAL | A production-store probe now covers 100,000 tenant/user principals with identical semantic states: 300,000 exhaustive scoped identity queries, 200,000 role/authority attacks, 10,000 concurrent read checks, and 800 writes yield zero scoped or actor-policy leakage; restart and a 100,800-record backup ledger pass. It assumes authenticated server-derived identities, raw get/get_many are unscoped, and no hours-long client load was run. |
| 23 | Persistent operational perspective | PARTIAL | Frozen perspective gauntlet passes; public profile drift/uncertainty study is missing. |
| 24 | Automated memory poisoning | PARTIAL | Poison/duplicate/tenant/role attacks exist in synthetic 250; CI-scale realistic document attacks are missing. |
| 25 | Provenance behavioral ablation | PARTIAL | On 25 frozen poison cases, no-provenance and display-only arms score 0%, while provenance used in governance scores 100%. HNG exactly ties StrongStructuredBaseline, and the result is synthetic deterministic behavior rather than a public downstream task. |
| 26 | Consolidation ablation | PARTIAL | A 240-record production-component probe compares raw with raw+consolidation: behavior is identical, patterns are 8.9% of raw logical JSON size, copies collapse, rare evidence/provenance/reversibility pass. Patterns-only action evaluation is unsupported, so no downstream gain is shown. |
| 27 | Cost/token efficiency | PARTIAL | Fixed 27B arm prompt tokens and latency are recorded. On disjoint public-data holdouts, BM25 k64 uses 116,800 tokens versus 680,824 for full context; dense/hybrid use 106,672/112,665 versus 643,575; reranked uses 104,965 versus 658,631. Embedding/reranking latency and energy, preprocessing/API cost, and broader public workloads remain. |
| 28 | Component latency p50/p95/p99/CI | PARTIAL | A 20-repeat, 8,640-event fresh-store tool-agent probe reports p50/p95/p99 and bootstrap intervals over mean per-run statistics with identical behavior. HNG p95 is 1.976 ms versus Strong at 0.0164 ms. Other components and deployment end-to-end intervals remain incomplete. |
| 29 | Long-run reliability soak | PARTIAL | Restart/fault/concurrency/20K-turn tests pass. A preregistered 1,000,000-write production-store probe passes 9/9 graceful restart checks, exact 100-tenant isolation, lifecycle mutations, and full-ledger backup/restore identity with independently matched database/backup hashes. A separate two-hour, 12-process, repeated-backup/resource-sampling protocol is PREPARED_NOT_EXECUTED and supplies no behavioral evidence yet. Repeated qualifying backup cycles, OS-crash, disk-full, long-run resource-growth, and hours-long concurrent soak evidence remain absent. |
| 30 | StrongStructuredBaseline challenge | PASS | Independent typed/filter/dedup baseline ties HNG 90% and is faster; the HNG loss is explicitly preserved. |
| 31 | Strong structured competitors | NOT_RUN | Unavailable property-graph/learned managers remain undefeated. |
| 32 | Full HNG ablation matrix | PARTIAL | Eight one-at-a-time counterfactual removals run on all 250 frozen scenarios. Outcome, perspective, provenance/trust, exact floors/contracts, temporal validity, supersession, and independence are ranked. Deterministic state carry and profile uncertainty are not isolatable here; consolidation and belief revision are separate component probes. |
| 33 | Evidence-led iteration loop | PARTIAL | The untouched tool-adapter loss led to a general fix and matched rerun. A 960-case unlabeled policy differential then found 236 action-relevant Strong/HNG contrasts, all with HNG more conservative, but no external labels; inference was correctly withheld. Broader labeled holdout iteration remains. |
| 34 | Statistical standard | PARTIAL | Paired bootstrap/exact McNemar and Bonferroni-adjusted reader-family rules cover the pushed disjoint Qwen/Mistral holdout; all six arm orders are balanced. Multiple inference seeds and canonical public/real units remain missing. |
| 35 | Automatic scoreboard | PARTIAL | Compiler produces Markdown/JSON scoreboard and machine rows for release and identifiability checks; required scientific rows remain incomplete until tracks run. |
| 36 | Capability radar | PARTIAL | A complete machine-readable evidence-maturity radar covers every requested axis without converting maturity into subjective capability scores. No axis has canonical public or real paired evidence. |
| 37 | Six minimum breakthrough gates | FAIL_OPEN | Gates 1, 2, 5, and 6 are unmet; Gate 3 passes only synthetically; Gate 4 passes frozen suites. |
| 38 | Stretch gates | NOT_RUN | No stretch gate is currently proven. |
| 39 | Failure-first development | PASS | New work is evaluation/harness/provenance work; no speculative HNG feature was added. |
| 40 | Public reproduction commands | PASS | The small `reproduce.py` surface covers all owned tracks, and a wheel-installed `hng-eval` ran `fresh-clone-core` from exact pushed commit `27e4a8e`: 58/58 dependency-free tests, isolated deterministic 250, and compiler completion. Four external LoCoMo modules are explicitly excluded only from the dependency-free clone proof; all run in the configured 94-test suite. Four observed failures are preserved rather than hidden. |
| 41 | Release artifacts | PASS | The backward-compatible 0.7.0rc3 reproducibility correction ships as an exact-commit, fresh-clone-tested wheel and sdist with SHA-256 manifest, changelog, migration guide, installed console entry, and machine proof. Two earlier artifact pairs are preserved and excluded from qualification. |
| 42 | Required research documents | PARTIAL | 18 of 19 named narrative documents and all four core machine-readable outputs exist. `FINAL_BREAKTHROUGH_VERDICT.md` is intentionally withheld until active public runs and the completion audit finish. |
| 43 | Final paper question | NOT_RUN | Paper claim cannot be supported before real/public gates. |
| 44 | Ten explicit final-report questions | NOT_RUN | Must be answered in final verdict after evidence closure. |
| 45 | Most-important same-retrieval A/B | PARTIAL | A disjoint, counterbalanced Qwen/Mistral holdout passes HNG-versus-ordinary, but HNG ties Strong exactly. All 154 public Strong/HNG pairs reuse exact prompts. An unlabeled grid finds conservative policy contrasts but supplies no defensible outcome labels, so a new reader holdout is not admitted. A real long-running task remains missing. |
| 46 | Second-most-important real HDC A/B | BLOCKED_EXTERNAL | Same resource absence as Section 7. |
| 47 | Combined-system success target | NOT_RUN | No evidence yet proves the full system-level claim. |
| 48 | Architectural freedom from evidence | PASS | No result has been protected ideologically; simple baseline tie and BM25 QMSum win are preserved. |
| 49 | No universal-dominance substitution | PASS | Retrieval, governance, and reasoning claims/results are kept separate. |
| 50 | Hostile-reviewer standard | IN_PROGRESS | Candidate/prompt/model invariants and provenance are explicit. Exact public prompt reuse is not misreported, and 596 unlabeled policy differences are not converted into wins. Public/real generality is still not defensible. |

## Minimum-gate ledger

| Gate | Current evidence | Result |
|---|---|---|
| 1: real behavioral improvement | No real HDC or other real assistant A/B is available. | UNMET |
| 2: public external validation | LongMemEval-V2, PersonaMem-v2, and all LoCoMo-Plus runs are noncanonical and lack contemporary-system comparisons. Retrieval-arm results remain informative, but all 154 public Strong/HNG pairs use exact prompts and cannot identify an HNG effect. | UNMET |
| 3: fixed-candidate governance | On a disjoint balanced-order window, Qwen is +33.3 points and Mistral +60.0 over ordinary; both CIs exclude zero and adjusted p<0.025. HNG exactly ties Strong in both. | PARTIAL |
| 4: robustness | 94/94, 64/64, 11/11, and 10/10 frozen suites pass; losses elsewhere are preserved. | MET |
| 5: HDC and LLM model independence | Pinned Qwen/Mistral readers now replicate on both original and disjoint generated cases; real HDC evidence remains absent. | UNMET overall (LLM-family subrequirement met) |
| 6: strong simple baseline | Strong ties HNG and is faster/cheaper. Synthetic reader inputs differ and still tie; public inputs are identical. A 960-case unlabeled grid finds HNG-only conservatism, but no external labels establish that abstention is correct. | UNMET (HNG does not beat/extend it) |

The ledger forbids an S or A claim on current evidence. It does not pre-commit the final verdict;
remaining public and operational experiments must still be completed where feasible.
