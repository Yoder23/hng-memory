# Preserved failures and negative results

This log is append-only in substance: later fixes may add resolution notes, but must not erase the
original observation or raw artifact.

## Provenance-ablation first execution failure

The first provenance-ablation invocation failed because direct script execution did not place the
repository root on `sys.path`; its unit test also exposed an incorrect assumption that provenance
was nested in the frozen record payload. The raw candidate representation keeps source/trust fields
flat. The script now adds the repository root explicitly and extracts the five flat provenance
fields. The failed invocation and test were not treated as benchmark evidence.

## Action-probe test-duration mismatch

The first action-probe unit test used a shortened 40-attempt run but incorrectly expected all 20
state/environment combinations to have reached success. Eleven remained unsolved because each
combination had too few visits. The benchmark's full 100-attempt run had already completed and
solved all 20. The regression test now executes the full frozen protocol; the failed shortened test
was not treated as result evidence.

## Baseline reproduction setup failures

1. The first full pytest baseline invocation omitted the nested package Python path. The unchanged
   code passed 94/94 on the corrected invocation. Both attempts are retained.
2. The first performance-profile invocation lacked the untracked FAISS vendor path. The unchanged
   code passed on retry. Both attempts are retained.
3. The first QMSum invocation had the same vendor-path setup defect. The unchanged code passed on
   retry. Both attempts are retained.

These are harness/dependency failures, not product-code failures.

## Missing release producers

The shipped REAL_HDC_ASSISTANT_ABLATION.json and BEHAVIORAL_GOVERNANCE.json have no producer
scripts in the frozen release. They are marked SHIPPED_ONLY_NO_PRODUCER_SCRIPT and are not counted
as freshly reproduced behavioral evidence.

## Real HDC gate blocked

No production HDC assistant, trained interpreter checkpoint or real trace corpus is available.
Prototype code without a trained checkpoint is not substituted. Therefore no real HDC HNG-off/on
claim exists.

## Adversarial duplicate-boundary loss

HNG returns conflicted rather than the frozen expected challenge for all 25 duplicate_attack cases
after correctly reducing six copies to one independent support event against two independent
challenges. Artifact: fixed_candidate/raw/deterministic_events.jsonl.

The same failure occurs in StrongStructuredBaseline and propagates through the fixed 27B model on
all three evaluated holdout variants. The expectation remains unchanged.

## Strong simple baseline tie

StrongStructuredBaseline exactly ties HNG on deterministic and fixed-LLM results while being
simpler, faster in deterministic preparation, and slightly smaller in prompt tokens. This is a
failure of HNG to satisfy Breakthrough Gate 6 on the current workload.

## Prior public losses remain

- BM25 remains better for query-specific QMSum retrieval in the inherited public experiment.
- Ordinary structured dictionary and matched dense heads reproduce the inherited synthetic
  perspective result.
- FAISS remains preferable to custom HNG ANN infrastructure at matched retrieval quality.

These losses motivate composition with strong retrieval and simple policy stores rather than
claims of universal HNG dominance.

## Public-harness setup failures

1. The first LongMemEval-V2 validator call used `--no-check-screenshots`, but the upstream
   validator still required question screenshots. After only the released question-image subset
   was downloaded, the unchanged validator passed for 451 questions, 1,870 trajectories, and 451
   small-tier haystacks. Trajectory screenshots remain absent.
2. The first new public-adapter test collection failed because the dynamic test loader did not
   register the module in `sys.modules` before executing a dataclass. The benchmark code was
   unchanged; the loader was corrected, and the full breakthrough suite passed 11/11.
3. The first reliability-result compiler integration placed the public prompt-token row after the
   wrong block and raised `IndentationError`. That failed compiler invocation is retained in the
   work log. The row was restored to its loop; compiler execution, JSON validation, and 11/11 tests
   then passed.

## LongMemEval-V2 preserved losses

The first judge-dependent premise-awareness item in the noncanonical public pilot was scored 0.
The local reader consumed 6,239 prompt tokens, reached its 192-token output cap, and failed to name
the specific invalid premise. The append-only event remains in
`public/longmemeval_v2/raw/events.jsonl`; it will not be relabeled or dropped.

The completed 21-question pilot is itself a preserved negative result: BM25,
StrongStructuredBaseline, and HNG all score 4/21 (19.0%) with identical fixed prompts. HNG produces
no public-data gain. Dynamic-state accuracy is 0/6 for every retrieval arm. The pilot is
noncanonical and cannot be compared to leaderboard results.

## GitHub ownership correction

The earlier inventory incorrectly conflated the old repository author Tao Yu with the user's
GitHub username. The user confirmed `Yoder23` is their account. A fresh private repository now
exists at `https://github.com/Yoder23/hng-memory`; API ownership/ADMIN permission and matching
local/origin/GitHub commit hashes were verified before any new work was pushed.
