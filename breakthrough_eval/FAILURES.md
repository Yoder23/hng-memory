# Preserved failures and negative results

This log is append-only in substance: later fixes may add resolution notes, but must not erase the
original observation or raw artifact.

## Expanded LoCoMo compiler integration failure

The first compiler run after adding dynamic LoCoMo result selection failed before writing new
aggregates because a Windows separator replacement became an unterminated Python string literal.
No benchmark event was affected. The repair uses the platform-safe Path method for POSIX rendering,
and the compiler then completed with 139 result rows and 15 scoreboard rows.

## Expanded LoCoMo planned resume interruption

The first 30-sample invocation was deliberately interrupted after 20 complete append-only events
to add exact-prompt inference reuse. An in-flight judge request received KeyboardInterrupt and did
not produce an event; the 20 completed events remain intact. The prepared manifest hash remained
unchanged across the corrected resumable invocation. This is a setup/protocol-efficiency event,
not a scored benchmark failure.

## Expanded LoCoMo final serialization failure

All 120 events completed with zero evaluation errors, but the first final compilation attempt then
failed because a relative raw-log path was compared with the absolute repository root. The raw
JSONL remained complete: 70 actual inference events and 50 exact-input reuse events. The serializer
now resolves the raw path before making it repository-relative; the corrected invocation performs
no new model calls because every sample/arm key is already complete.

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

## LoCoMo-Plus preserved loss

The completed six-category public-data pilot is a negative result. Full context scores 3/6 (50.0%),
while BM25, StrongStructuredBaseline, and HNG each score 2/6 (33.3%) with identical fixed retrieval
prompts. HNG produces no governance gain on clean dialogue turns and trails the full-context arm.
The result is noncanonical and too small for a leaderboard or significance claim.

## PersonaMem-v2 setup failures

1. The first full upstream Git clone ran for more than three minutes without completing. The partial
   target was verified before removal; a shallow clone then succeeded at commit
   `dd52429f83ced4394be46c3849186a423942b2a5`.
2. Two Hugging Face CLI attempts under the long workspace path failed with Windows cache
   `FileNotFoundError` path-length errors. Downloading to the short external path `C:\tmp\pmv2`
   succeeded without modifying the dataset.
3. The first eight-worker 32K-history download reached 92% before repeated HTTP 429 responses
   exhausted retries. A one-worker resume initially encountered the same rate limit, then completed
   all 1,998 files from cache. No completed file was deleted.
4. The first pilot test collection exposed a generated path-normalization syntax error before any
   benchmark call ran. The path now uses `Path.as_posix()`; all four pilot tests and preparation pass.
5. The first three PersonaMem-v2 reader attempts used a 192-token output budget and reached the cap
   before consistently emitting the required final MCQ letter. They remain in the append-only log
   but are excluded from scoring. The fail-closed rerun requires an explicit final letter and a
   non-length stop reason.
6. The official full-history harness places MCQ options in a trailing system message. On the local
   Ollama/Qwen path, five of seven responses ignored or outgrew that instruction and were rejected;
   two happened to emit parseable letters. Prompt protocol revision 2 moves the same MCQ task into
   the final user turn and reruns all seven full-history arms for a consistent local protocol. Every
   revision-1 full-history event remains preserved and excluded.

## Public-adapter provenance-label correction

The shared clean-document HNG adapter initially hard-coded `LongMemEval-V2` as the provenance
identity. LoCoMo-Plus and the first PersonaMem-v2 HNG event therefore carried the wrong dataset name
inside their governance traces, although candidates, policy decisions, prompts, and scores were
unchanged. Those raw events are preserved and excluded by identity validation. The adapter now
requires the actual source identity/prefix, regression tests assert them, and only the affected HNG
arms are rerun.

These are setup/transport failures, not result evidence. The official benchmark validates at 5,000
rows, 200 uniquely referenced 32K histories, and zero missing history references.

## Tool-agent adapter loss and harness setup failures

The untouched ToolAgentAdapter failed the executing synthetic tool-agent study: HNG scored 29.6%,
below agent alone at 33.3%, ordinary memory at 46.3%, and StrongStructuredBaseline at 63.9%. It made
18 irreversible mistakes because recorded outcomes lacked temporal validity and access/perspective
context; a v1 success remained globally SUPPORT in v2. The loss is preserved in BEFORE_RESULTS.

The first full invocation failed before execution because its default 120 episodes violated the
phase-alignment requirement of a multiple of 36. No event was emitted. The corrected default is
108. The next invocation executed and wrote all 432 raw events but failed while normalizing a
relative raw-log path against the absolute repository root. That raw stream remains preserved and
excluded. Path normalization was corrected, and the qualified untouched run used a new raw file.

After the general context-forwarding fix, HNG reaches 63.9%, eliminates the 18 irreversible
mistakes, and exactly ties StrongStructuredBaseline while remaining slower. This is a recovered
defect and preserved tie, not a breakthrough win.

## 0.7.0rc2 packaging correction

The first rc2 wheel and sdist built successfully, but inspection showed that the sdist omitted the
new changelog and rc1-to-rc2 migration guide. Both initial artifacts and hashes remain preserved
under releases/0.7.0rc2/dist and are excluded from release qualification. MANIFEST.in was added and
a separate final_dist build includes both documents. Its wheel installs in an isolated target,
reports runtime version 0.7.0rc2, exposes the contextual adapter parameters, and persists a
versioned outcome in the smoke test.

## Scaled isolation setup failure and security boundary

The first attempt to add the 100,000-principal probe failed inside the patch-command wrapper because
literal documentation delimiters terminated its JavaScript template before apply_patch ran. No
repository file or benchmark artifact changed. The patch was resubmitted without that wrapper
ambiguity; the small regression passed before the full run.

The full probe also records a deployment limitation rather than hiding it: scoped eligible-ID
queries and ActorPolicy produce zero observed cross-user, cross-tenant, role, or authority leakage,
but raw get/get_many are privileged unscoped primitives. Possession of a private record identifier
is sufficient for direct raw lookup. The result therefore does not claim authentication-system or
request-boundary security; deployments must keep raw access behind server-side authorization.

## HNG-ablation harness corrections

1. The first matrix invocation imported `EvidenceAggregator` from the governance convenience module,
   but the frozen release exposes it from `hngfrontier.aggregation`. No event was emitted.
2. The next invocation treated `Scenario.candidate_pool_sha256` as a method instead of a property.
   No event was emitted.
3. Protocol revision 1 completed but its provenance/trust ablation used the unrecognized source type
   `telemetry`; the production trust map therefore assigned a low default and excluded nearly all
   evidence. All 2,250 revision-1 events remain in the append-only log but are excluded. Revision 2
   uses `system_telemetry`, reruns all decisions, and is the sole reported matrix result.

## Retrieval-budget preregistration validation boundary

A repository-root `pytest -q` attempt failed during collection with 36 import errors because it
traversed the preserved 0.5.1 baseline source snapshot and vendored external benchmark trees as if
they were part of the active package. The failures include the snapshot's isolated `hngfrontier`
path plus intentionally uninstalled PersonaMem-v2 GPU/distributed dependencies such as `verl`,
`flash_attn`, `vllm`, and `tensordict`. No retrieval-budget inference had started. The owned
breakthrough suite passed 46/46, including the holdout's 13 focused tests; the production package
suite is validated separately rather than silently excluding or modifying preserved external code.

The first post-execution uniqueness-audit command escaped a PowerShell interpolation expression as
a command and emitted diagnostic errors; it did not read scores incorrectly or change artifacts.
The audit was rerun in Python and verified 180 events, 180 unique sample/arm keys, zero duplicates,
zero event errors, and one preregistration commit across the complete log.

## Dense/hybrid holdout setup failures

1. The first structured sample inspection printed an entire public conversation and then hit a
   Windows cp1252 `UnicodeEncodeError` on an emoji. It changed no file or model state. Subsequent
   inspection used ASCII-safe metadata summaries only.
2. The first cross-manifest overlap audit expected a `development_indices` field in the older
   development manifest and raised `KeyError`. The byte-stable prepared manifest was unchanged.
   The corrected audit derived indices from its sample rows and verified zero overlap with all 60
   earlier samples and exact equality between the excluded set and those prior windows.
3. After execution, an unscoped repository-root `pytest -q` repeated the known collection failure:
   it traversed the immutable baseline snapshot and vendored external projects, producing 36
   missing-package import errors for isolated or optional dependencies such as `hngfrontier`,
   `verl`, `flash_attn`, and `tensordict`. No experiment or result artifact changed. The owned
   breakthrough suite passed 51/51 and the production package suite passed 100/100 from its
   package root.
