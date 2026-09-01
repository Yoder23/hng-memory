# Fixed-candidate cross-family reader replication protocol

## Purpose and evidence boundary

This failure-driven replication tests whether the synthetic fixed-candidate governance result is
specific to the Qwen reader family. It uses a Mistral-family reader while holding the cases,
ordered candidate pools, three memory-system contexts, action-advisor prompt, scoring rule, and
generation settings fixed. It addresses model-family robustness only. It is not a new dataset,
public benchmark, canonical leaderboard protocol, multiple-seed study, contemporary-system
comparison, or real-assistant/HDC evaluation.

The Mistral acquisition and a single development-split compatibility smoke occur before
preregistration. No holdout inference is permitted until the exact installed digest, qualification
artifact, protocol, prepared manifest, harness, and tests are committed and pushed.

## Frozen inputs and systems

- Protocol: `fixed_candidate_cross_family_llm_holdout`.
- Evidence class: synthetic.
- Seed: 20260831.
- Cases: exactly the same first 30 generated holdout cases used by the frozen Qwen-family study.
- Balance: three cases from each of ten adversarial families.
- Prepared file SHA-256: `eddfc96fc553dad7c5ac675222658bd8b374d9b85465383e48c3d864ad6b28c3`.
- Systems: `ordinary_rag`, `strong_structured`, and `hng`.
- Reader: `mistral-small3.1:24b-instruct-2503-q4_K_M`.
- Installed Ollama digest: `b9aaf0c2586a8ed8105feab808c0f034bd4d346203822f048e2366165a13f4ea`.
- Generation: temperature 0, seed 20260831, `num_predict=32`, `num_ctx=32768`, streaming off.
- Output contract: one JSON-schema-constrained enum value from `support`, `challenge`,
  `conflicted`, or `insufficient_evidence`.

For every case, all systems receive the identical ordered candidate pool. Only the serialized
memory context differs according to the already-frozen ordinary, Strong, or HNG policy. The
expected decision is never included in the model prompt. Tests require every case ID, candidate
ID sequence, candidate-pool hash, and system-specific memory-context hash to match the prior
Qwen event log exactly.

## Preregistered comparisons and decision rules

The primary comparison is paired exact-match decision accuracy for `hng - ordinary_rag` over all
30 cases. The complexity control is `hng - strong_structured` over the same cases. For each,
report the paired accuracy delta, deterministic paired-bootstrap 95% interval from the frozen
harness, and two-sided exact McNemar p-value.

A reader-family-independent HNG superiority claim requires, on the Mistral run:

1. a positive HNG-minus-ordinary accuracy delta;
2. a paired-bootstrap 95% lower bound above zero; and
3. two-sided exact McNemar `p < 0.05`.

Attribution of that superiority specifically beyond the Strong baseline additionally requires the
same three conditions for HNG versus Strong. If the primary rule passes but the complexity control
does not, the result supports a benefit from governed/structured memory context but not an
HNG-specific advantage. A tie, negative delta, interval including zero, or `p >= 0.05` is preserved
as a failed superiority test. No per-family or latency result can substitute for either
preregistered accuracy comparison.

Because these 30 cases were previously evaluated with Qwen, the Mistral result is a fixed-case
model-family replication rather than an independent confirmatory sample. Cross-family comparisons
to the prior Qwen scores are descriptive only.

## Execution, failures, and audit

The execution command must supply the exact preregistration commit. The harness refuses to run
unless HEAD equals that commit and there are no changes outside this protocol's append-only raw
log/result runtime files. An existing raw log is accepted only when every row has the identical
protocol, model name, full digest, and preregistration commit.

Run all 90 case/system calls without interim scoring or stopping. Every attempt is append-only.
Failed calls remain in the log; successful retry does not erase them. A result is complete only
when all 90 expected case/system keys have exactly one completed event and every completed input
matches `PREPARED.json`. Otherwise the result remains partial. Report all losses, ties, incomplete
events, and recovered failures.

Outputs are isolated under `breakthrough_eval/fixed_candidate_cross_family/`: the qualification,
prepared input manifest, preregistration manifest, raw JSONL events, result summary, and final
execution manifest.
