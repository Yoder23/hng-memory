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

## Neural-reranker holdout setup failures

1. The first pinned Hugging Face snapshot download populated blobs but failed when the Windows
   cache attempted to create a symlink without the required OS privilege (`WinError 1314`). No
   benchmark artifact or model inference changed. The identical repository revision was restored
   into an explicit temporary directory using real files; its 1,191,588,280-byte safetensors file
   hashes to the preregistered SHA-256.
2. The first inline smoke command was rejected by the local shell helper while parsing nested
   quotes; Python never launched. The official yes/no-logit scoring path was moved into a tested
   repository module instead of weakening the command parser.
3. The first direct smoke-script invocation failed before model load because its module search path
   omitted the repository root. The entry point now uses the same root bootstrap as the other
   evaluation scripts. The corrected smoke ranks the relevant passage 0.9897 versus 0.0250.

## Cross-family reader replication setup failures

1. The first Ollama inventory command used a nested inline Python f-string that the local shell
   helper rejected while parsing quotes. Python never launched and no model or artifact changed.
   A JSON-only inventory command then succeeded.
2. A standalone `pytest` executable resolved to a different Python environment and failed during
   collection because it could not import `breakthrough_eval`. The project interpreter passed the
   same focused suite. No holdout inference had started.
3. One combined patch submission had an invalid multi-file hunk boundary and was rejected before
   applying any line. The changes were split into valid patches and their regression tests passed.
4. The first append-only resume-guard patch lost a backslash while traversing the JavaScript,
   PowerShell, and Python quoting layers, producing a Python syntax error during test collection.
   No inference ran. The path normalization now uses an unambiguous character code and the focused
   suite passes before preregistration.

## Cross-family reader replication surviving failure

The pushed Mistral-family replication completes 90/90 events with zero runtime failures and passes
the preregistered HNG-versus-ordinary rule (27/30 versus 8/30; +63.3 points; CI excludes zero).
It nevertheless reproduces the central attribution failure: HNG and StrongStructuredBaseline are
an exact 27/30 tie with CI [0, 0] and p=1, and both miss all three duplicate-attack cases. HNG also
uses 18,261 prompt tokens versus Strong's 17,358. This is evidence for structured/governed context,
not an HNG-specific breakthrough, and the fixed-case synthetic design supplies no public or real
assistant claim.

## Disjoint cross-reader holdout setup failures

1. The first preregistration-manifest freeze failed closed before writing a manifest because the
   harness expected Ollama family `qwen3`, while the exact installed Qwen 3.5 model digest reports
   authoritative family `qwen35`. No inference or result event occurred. The model name and full
   digest were already correct; the family pin now uses the observed exact metadata rather than a
   weakened or substring-based check.
2. After correcting the code pin, the next freeze refused to proceed because the already-preserved
   preparation artifact still contained the old family label. No case, candidate, context, order,
   or model event changed. The single metadata field and its protocol file hash were updated
   explicitly before preregistration rather than bypassing the immutability check.

## Disjoint cross-reader holdout surviving failure

The pushed 180-event holdout passes its Bonferroni-adjusted joint HNG-versus-ordinary rule in both
Qwen and Mistral, on cases untouched by the earlier reader study and with exact six-order balance.
It again fails the architectural attribution control: HNG and StrongStructuredBaseline are exact
27/30 ties in both readers (CI [0,0], p=1), and both miss every duplicate-attack case. HNG also
uses more prompt tokens than Strong in both readers (17,103 vs 16,215 for Qwen; 18,261 vs 17,358
for Mistral). The surviving result is structured/governed-context evidence, not HNG-specific,
public, canonical, or real-assistant evidence.

## Fresh-clone reproduction failures

1. A new clone at result commit `a2475fab953192c4539595738ae8b3006e5dd14c` installed rc2 and
   NumPy successfully in a new virtual environment, but `hng-eval.exe` did not exist. This directly
   reproduced the Section 40 packaging gap; no authoritative evidence file changed in the clone.
2. The first rc3 wheel created `hng-eval.exe`, reported `hng-eval 0.7.0rc3`, and forwarded the core
   dry-run correctly. Actual core collection then failed in four LoCoMo tests because the fresh
   clone intentionally lacks the uncommitted external `task_eval` checkout. The failure is
   preserved in `fresh_clone_reproduction/BEFORE.json`. A separate dependency-free command now
   declares those four exclusions while the configured-environment suite continues to run them.
3. The first exact-commit run of `fresh-clone-core` passed 54 tests but failed two configuration
   tests because `Qwen3Reranker` imported optional `torch` before rejecting invalid dimensions.
   The new virtual environment correctly did not contain the heavyweight reranker runtime. The
   failure is preserved in `fresh_clone_reproduction/BEFORE.json`; validation now occurs before
   optional imports, without changing any valid reranker inference path.
4. The next new-clone run passed all 56 dependency-free tests, then the 250-case stage failed
   closed because its default output was the committed frozen raw log. This preserved immutable
   evidence but exposed an incorrect reproduction target. `fresh-clone-core` now writes the same
   deterministic study to a new ignored `.hng-eval-proof/fixed_candidate` directory; normal
   evidence paths and compiler inputs are unchanged.

## Identifiability audit setup failure

The first two unit fixtures failed because the audit attempted to render every input path relative
to the repository evidence directory, while pytest correctly created fixtures in the operating
system temporary directory. No preserved evidence was read incorrectly and the main audit still
completed. Path display now falls back to an absolute fixture path; comparison logic is unchanged.

## Policy-differential development setup failure

The first direct policy-search invocation failed before generating a result because Python placed
the script directory, rather than the repository root, on its module path. The import-based unit
tests passed, which exposed the entry-point-specific gap. The script now inserts its resolved
repository root explicitly before importing the shared benchmark policy code.

## Million-write preregistration setup failure

The first focused preregistration test used an incorrect hard-coded SHA-256 fixture value; the
streaming hash implementation returned the correct digest and no reliability execution had begun.
Review also caught that free-space preflight targeted the intentionally absent runtime directory.
The expected digest is corrected and disk capacity is now checked on the existing protocol
directory before the probe creates runtime files.

## Million-write execution monitoring setup failures

Read-only progress probes encountered one inline-Python quoting `SyntaxError`, two orchestration
JavaScript quoting `SyntaxError` failures, and transient shell-helper setup-refresh errors. None
opened SQLite, changed a runtime file, restarted the benchmark, or altered its arguments. The
original preregistered process handle completed once with exit code zero; its exclusive machine
result and independently recomputed database/backup hashes are the admitted evidence.

## Million-write result metadata limitation

The successful million-write wrapper delegates execution to the bounded-probe engine and inherited
that engine's generic `bounded_sqlite_evidence_store_reliability_probe` value in the `benchmark`
field. The authoritative JSON was not rewritten. Its frozen protocol/preparation paths, exact
preregistered commit, one-million-record configuration, command, source hashes, and exclusive
artifact path identify the qualifying run. This label defect does not change a pass criterion, but
it remains preserved rather than silently normalized.

## Sustained-reliability harness setup failures

1. The first large file-add patch exceeded the Windows command-line length
   limit and was rejected before applying. The harness was then added through
   bounded patch chunks; no reliability process had started.
2. One direct patch call hit a transient sandbox setup-refresh error before
   modifying the file. The identical bounded patch succeeded through the
   approved patch wrapper.
3. The first protocol patch embedded Markdown backticks in an orchestration
   template literal and failed at JavaScript parse time. The parser-safe patch
   preserved the same protocol content.
4. The first focused-test tool call was rejected by the orchestration parser
   before Python launched. The same command then ran through a parser-safe
   variable and passed all 13 focused tests.
5. Two attempts to add the SQLite journal-sidecar ignore rule were rejected
   before applying (one parser failure and one sandbox refresh failure). The
   same one-line patch then succeeded; no runtime artifact was changed.

None of these setup failures generated a preparation artifact or qualifying
behavioral event.

## Sustained-reliability qualifying failure

The exact clean pushed command at commit
`d3cef83d1f4d86ab4efe1bcbaa8cf77f4b8b2ccf` started all four writers and
eight readers. At 600 seconds the coordinator entered the first online SQLite
backup. Under uninterrupted writes the backup did not complete and emitted no
event; because the coordinator was blocked, the 900-second worker rotation
also did not occur. At the missed rotation boundary all 12 workers were still
live, the backup remained zero bytes, WAL was 10,237,227,712 bytes, maximum
worker handles were 815, and 85,879,586,816 bytes remained free.

Continuing unchanged would have bypassed the coordinator's resource sampling
and rotation while WAL/handles kept growing. One safety Ctrl-C stopped the
process with exit code 1 and all workers terminated. The protocol is not
retried. Thirteen fsynced events and byte hashes for the event ledger, live
database, 10.318 GB WAL, and partial backup are preserved in
`reliability/sustained_2h/INTERRUPTED.json`. Zero backup cycles completed and
no qualifying soak result exists.

## Sustained-reliability interrupt serialization failure

The top-level wrapper was intended to catch BaseException and write an
exclusive ERROR result. The unified Ctrl-C path instead exited with no stdout
and no RESULTS.json. The external machine postmortem is therefore labeled
`INTERRUPTED_FAIL`, not presented as wrapper output. The first PowerShell
hash-reporting expression also contained an empty pipeline element and failed
before reading a file; an explicit result-array command then hashed all four
preserved artifacts successfully.

## Sustained-reliability v2 qualifying failure

The failure-driven v2 protocol was frozen and pushed at commit
`d446a455f9695cf05ffeba955720f5556c916d36`. Its one exact execution fixed the
v1 backup-starvation mechanism: 6/6 completed write-quiesced/read-live
backup/restore cycles passed, and 4/4 completed 15-minute worker epochs returned
all reports with zero exit failures. Complete-epoch reports contain 908,830
durable writes, 802,305 scoped reads, and zero missing or malformed reads.

At 4,020.086 seconds the fsynced resource sample measured 1,059 handles in each
writer process and 1,049 in each reader process, exceeding the frozen
1,024-per-process cap. The coordinator raised `RuntimeError`, stopped all active
workers, wrote `RESULTS.json` with `status=ERROR`, and exited code 1. Only 4/8
required epochs, 6/12 required recovery cycles, and 68/100 required samples had
completed. The protocol is not retried or called a partial pass.

Post-stop read-only inspection found no live worker PID, SQLite
`quick_check=ok`, exact row/generation equality at 1,008,409, and a stable
logical ledger hash. Those checks are recovery evidence, not a substitute for
the final qualifying check the protocol never reached. Original stdout,
`RESULTS.json`, and `events.jsonl` are unchanged; the derived machine
postmortem is `reliability/sustained_2h_v2/FAILURE_ANALYSIS.json`.

## Sustained-reliability v2 observer-effect hypothesis

The coordinator stayed at 268 handles while readers and writers rose almost in
lockstep and rotations initially reset child counts. Epoch 4 then showed a
large synchronized increase during an interval with unusually heavy external
orchestration and repository inspection. This correlation motivates a separate
controlled diagnostic but does not establish causation, relax the frozen cap,
or change v2's failure. The hypothesis is recorded as `UNPROVEN` and cannot be
used as qualification evidence.

## Child-handle diagnostic timing-control failure

The first separately preregistered observer diagnostic ran from commit
`d9ff16b7257446af53d19eed873f34670e03e0aa`. All four children completed with
zero errors, every phase met its sample minimum, and pulse ordinals 1 through 20
were unique and complete. The external pulse launcher began later than expected
and its per-command overhead accumulated: pulse 19 landed at 271.357 seconds
and pulse 20 at 276.805 seconds, outside the frozen `[150,270)` external phase.
The fail-closed analyzer returned `status=ERROR`, `valid=false`, and
`outcome=INVALID`; the run is not retried or used to resolve the hypothesis.

The children recorded zero net external-phase handle growth across idle, event,
SQLite-read, and SQLite-write variants, but that descriptive observation cannot
satisfy the preregistered decision because two pulse-timing controls failed. A
follow-up requires a new protocol/output directory and a cadence that leaves a
larger timing margin.

## Child-handle diagnostic v2 timing-control failure

The distinct timing-corrected run from commit
`8585905e7c78107228a2e93ce3987974845f0397` shortened its intended pulse cadence
to two seconds, but external process-start and approval overhead delayed the
first pulse to 180.702 seconds and made the effective cadence about 5.3 seconds.
Pulses 18, 19, and 20 landed at 273.536, 279.255, and 284.688 seconds, outside
the frozen `[150,270)` external phase. All other validity checks passed; the
analyzer again returned `ERROR/INVALID`, and the run is not retried.

The four child variants again had zero measured external-phase handle growth.
That repeated descriptive observation remains inadmissible for the frozen
decision because timing validity failed. A follow-up must use a wider external
window plus no intentional inter-pulse delay, under a new protocol and commit.

## Child-handle diagnostic v3 valid refutation

The timing-robust follow-up from commit
`7bed722e642ca9c89663cf53d3fa6457c3082956` widened the external window to 180
seconds and removed intentional pulse delay. All 20 ordinals landed in the
frozen window; all child reports, exits, errors, and sample minimum controls
passed. Idle, event-poll, isolated SQLite-read, and isolated SQLite-write
children each showed zero net handle growth during both the external phase and
recovery. The exact frozen outcome is
`REFUTES_OBSERVER_EFFECT_AT_THRESHOLD`.

This rules out the narrow external-pulse hypothesis at the preregistered
thresholds for those isolated variants. It does not reproduce the failed v2
12-process shared-database workload or make v2 pass. Reliability root-cause
work must now isolate process count, shared SQLite/WAL activity, and workload
operations rather than attributing the breach to progress-report tool calls.

## Shared-SQLite handle-matrix sampling failure

The first four-condition root-cause matrix ran from commit
`71706b2a06daa56745f878eb7918d9cd3baa81ee`. All 48 children returned reports
with zero errors and exits, and all reader checks were well formed. Idle and
isolated-SQLite controls passed. In the two shared-database conditions, several
writers completed only 72 to 79 of 80 required self-samples because sampling
ran in the workload loop and long SQLite operations delayed it. The exact run
is consequently `ERROR/INVALID` and is not retried.

The invalid run descriptively separated the conditions: idle and isolated
medians were both about 0.667 handles/minute, versus 32.360 and 17.334 for the
two shared conditions, with positive synchronized growth in every shared child.
Those values cannot satisfy the invalid run's decision. They justify a new
protocol with an independent sampler thread and an explicit replicated
lower-bound rule.

## Shared-SQLite handle-matrix v2 valid localization

The independently sampled follow-up ran from commit
`245090724cfbb1552388b44a4d17a939321b6fe8`. All 48 fresh children exited zero,
reported without errors, and produced 90 or 91 samples against the frozen
minimum of 80. Readers observed zero missing or malformed records. Median
handle slopes were 0.667 handles/minute in both the 12-process idle and
12-process isolated-SQLite controls, versus 41.792 and 49.206 in two independent
shared-SQLite/WAL replications. Every shared child exceeded the frozen
10-handles/minute lower bound, while every control remained below the frozen
5-handles/minute ceiling. The exact outcome is
`SUPPORTS_SHARED_SQLITE_CAUSE`.

This validly localizes the reproduced growth to concurrent shared-database
activity under the tested workload and rules out process count, isolated SQLite
use, and the independent sampler at the frozen thresholds. It does not yet
identify the leaking Windows handle type or allocating call path, and it does
not reverse sustained v2's failed qualification. A new sustained protocol is
not justified until a bounded mechanism diagnostic identifies what is being
allocated and an intervention can be tested directly.

## Handle-type diagnostic preflight transcription failure

The first handle-type invocation supplied commit
`7364134c3be2311f4ba73f85a284977d4c13c2aa`, not the actual preregistered `HEAD`
`7364134bc8536d3497a9b77113b3e1b310e25c5e`. The exact-commit preflight failed
closed, wrote `status=ERROR`, and exited 1 before creating an event ledger,
worker processes, or run data. It provides no mechanism evidence. The artifact
and output namespace are preserved; a separately versioned v2 protocol is
required for the corrected full-hash invocation.

## Handle-type diagnostic v2 queue-drain validity failure

The corrected exact-commit run from
`e43112503899cb11f3808ec6e731f2ab48c9a945` completed all workload windows, but
the frozen parent joined children before draining their enlarged type-histogram
queue reports. In every condition, 9/12 reports arrived and three children were
terminated after their queue feeders blocked. All available reports had no
workload, reader-integrity, or handle-query errors and all sample minimums
passed, but the all-reports and zero-exit controls failed. The exact outcome is
`ERROR/INVALID` and is not retried.

Descriptively only, idle and isolated medians were about 1.017 total
handles/minute, versus 38.634 and 47.795 in the two shared replications. The
nine available reports per shared condition agreed that Windows `Section`
objects dominated, with median deltas of 38 and 47 and 92.7% and 94.0% shares
of positive median type growth; controls had zero median `Section` growth.
These values are inadmissible for the invalid decision. A distinct follow-up
must drain reports concurrently with child exit while retaining the frozen
mechanism thresholds.

## Handle-type diagnostic v3 valid identification

The queue-safe follow-up from commit
`53e3602689e59255c2152fbd4a02ce500b87fa67` drained reports before joining
children. All 48 children reported, exited zero, met their sample minimums, had
zero handle-query errors, and produced zero missing or malformed reader checks.
Idle and isolated-SQLite median slopes were both about 1.017 handles/minute;
the two shared replications measured 48.810 and 49.814. Every shared child
exceeded the frozen lower bound.

Windows `Section` objects had median deltas of 48 in both shared replications,
accounted for 94.1% of positive median type growth, and had zero median growth
in both controls. The exact frozen outcome is
`IDENTIFIES_DOMINANT_HANDLE_TYPE`. This validly identifies the kernel object
type but not yet the mapped file or SQLite allocation path. Sustained v2 remains
failed; the mechanism result is not reliability qualification evidence.

## WAL-index Section-mapping mechanism identified

The exact follow-up from commit
`0221dd8fd076103a15c8dd58dd8aa5ef57b64ad0` passed all 48 child and integrity
controls. In the first shared replication, the `-shm` WAL-index grew by 34
32-KiB units and every client gained exactly 34 Section handles. In the second,
the WAL-index grew by 48 units and every client gained exactly 48 Section
handles. The maximum mismatch across all 24 shared children was zero. Isolated
clients stayed at one SHM unit and gained zero Sections; idle controls also
gained zero Sections. The frozen outcome is
`IDENTIFIES_WAL_INDEX_SECTION_MAPPING`.

The shared WALs reached 589,584,392 and 818,891,232 bytes in 60 seconds. The
root mechanism is therefore uncontrolled shared WAL/WAL-index growth, with each
client mapping every new 32-KiB WAL-index unit into a Windows Section handle.
This explains the synchronized per-process growth and the sustained safety-cap
failure. It does not itself prove an intervention; sustained v2 remains failed
until a separately preregistered WAL-bounding treatment and full reliability
run pass.

## Rotation/TRUNCATE treatment passes bounded intervention gate

The exact treatment run from commit
`55c25f1a2416a3848b0f47527099a6d59361363f` first reproduced the failure
mechanism over 120 untreated seconds: maximum process handles reached 329, all
children gained 99 Sections, the WAL-index reached 100 units, and the WAL
reached 1,681,635,712 bytes.

Two independent treatments then ran four 30-second fresh-connection epochs
each. Every one of eight fully quiescent TRUNCATE checkpoints returned
`busy=0`, left a zero-byte WAL, and completed in 0.029-0.041 seconds. Treatment
maxima were 252 and 256 handles and 21 and 25 Section handles per epoch, while
aggregate throughput was 128.3% and 113.4% of the untreated baseline. All
workers, reader checks, `quick_check`, row counts, and evidence generations
passed exactly. The frozen outcome is
`SUPPORTS_ROTATE_CHECKPOINT_WAL_BOUNDING`.

This supports the intervention but does not reclassify sustained v2. A distinct
two-hour protocol must now combine short connection epochs, quiescent TRUNCATE
checkpoints, v2's monitored recovery, and the original fail-closed resource
limits.
