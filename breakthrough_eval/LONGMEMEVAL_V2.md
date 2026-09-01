# LongMemEval-V2

## Claim boundary

The installed resource is the official LongMemEval-V2 repository at commit
`2cc8c540bdb87fe6761629b585e727e1c4704520` and the official small-tier text data pinned in
`PUBLIC_RESOURCES.json`. The upstream validator passes for 451 questions, 1,870 trajectories,
and 451 small-tier haystacks after the released question screenshots were installed.

This repository does **not** currently contain the multi-gigabyte trajectory screenshots or the
official reader/embedding/judge stack. Consequently, the local result is a noncanonical public-data
pilot, not an official leaderboard score and not evidence that HNG defeats a reported system.

## Frozen pilot protocol

- Selection: SHA-256 of `(seed, question id)`, stratified by domain, ability, and deterministic
  versus judge-dependent scoring. Neither reference answers nor evidence annotations participate.
- Slice: 21 questions spanning static state, dynamic state, workflow knowledge, environment
  gotchas, and premise awareness.
- Haystack: official small tier; 100 trajectory identifiers per question and 200 distinct
  trajectories across the selected slice.
- Retrieval: local BM25 over text state slices containing trajectory goal/outcome plus URL,
  action, thought, and a capped accessibility tree.
- Reader: fixed local `qwen3.8:27b-q4_K_M`, digest
  `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`, temperature 0,
  seed 20260831.
- Scoring: official deterministic evaluation functions. Items requiring semantic grading use
  the official prompt/rubric with the same local model as judge and are reported separately.
- Arms: no retrieval, BM25, BM25+StrongStructuredBaseline, BM25+HNG.
- Fixed-candidate invariant: BM25, StrongStructuredBaseline, and HNG receive the same ordered
  candidates. Governance may only remove candidates. When it retains the same set, rendering
  preserves BM25 order, producing an identical prompt hash.
- Raw output: append-only `public/longmemeval_v2/raw/events.jsonl`.

## Leakage controls

Reference answers and evaluation functions are loaded only after the reader response is produced.
They are never passed to selection, BM25, candidate governance, or the reader prompt. The official
dataset does not expose an oracle evidence field in this adapter.

## Results

The run completed all 84 arm evaluations with zero runtime failures. Every fixed-candidate
invariant passed for all 21 questions: BM25, StrongStructuredBaseline, and HNG used identical
candidate pools, selected IDs, prompt hashes, and model digests.

| Arm | Correct | Accuracy | Prompt tokens | Reader p50 / p95 |
|---|---:|---:|---:|---:|
| No retrieval | 0/21 | 0.0% | 3,832 | 16.097 / 30.316 s |
| BM25 | 4/21 | 19.0% | 122,054 | 46.302 / 49.170 s |
| StrongStructuredBaseline | 4/21 | 19.0% | 122,054 | 30.570 / 32.547 s |
| HNG | 4/21 | 19.0% | 122,054 | 30.588 / 32.127 s |

All three retrieval arms score 0/6 dynamic-state, 2/3 environment-gotcha, 1/6 static-state, and
1/6 workflow questions. The latency order is confounded by serialized execution and model cache
effects; it is descriptive, not an arm-speed claim. HNG neither changes the clean candidate set nor
improves an answer. The first preserved premise-awareness loss remains: the reader hit its output
cap and failed to identify the specific invalid premise, so the local judge scored it 0.

Machine results are `public/longmemeval_v2/RESULTS.json`; raw events are append-only under
`public/longmemeval_v2/raw/`.

## What this experiment can establish

It can test whether production HNG changes downstream answers after the same clean BM25 candidate
selection. It cannot establish official LongMemEval-V2 competitiveness, visual-memory ability,
or a state-of-the-art claim. If HNG and the simple baseline leave all clean candidates untouched,
the observed exact aggregate tie is the expected and important result: governance has no value to
add without governance-relevant metadata or corruption. The low noncanonical score and lack of a
contemporary-system comparison mean this result does not satisfy the public-validation gate.
