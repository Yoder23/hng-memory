# Frozen v0.7.0rc1 Baseline

Commit: `e57db1b1e92329e9b8f2b173be9a506d2b898da8`. All commands were executed from a detached worktree.

## Reproduced gates

- Full source suite: 94/94.
- Expanded adversarial selection: 64/64.
- Canonical adversaries: 11/11.
- Fault/concurrency: 10/10.
- Inherited readiness, perspective, turn-stream, 20K-turn assistant, restart, noise, and package smoke runs completed successfully.
- Official QMSum-20, 300-query component profile, 100K/1M provider trials, 100K geometry trials, and the shipped 10M retrieval attempt completed successfully.

## Preserved execution failures

The first full-pytest attempt did not pass the package test path, so pytest lacked the package `pythonpath` setting. The first performance/QMSum attempts lacked the intentionally untracked FAISS vendor directory. These are harness/dependency failures, not HNG failures. Their raw logs remain preserved; corrected invocations reran unchanged release code and passed.

## Non-reproducible shipped results

`REAL_HDC_ASSISTANT_ABLATION.json` and `BEHAVIORAL_GOVERNANCE.json` are preserved byte-for-byte from the release, but their producer scripts were not shipped. They remain release evidence, not fresh reproductions.

## Breakthrough gate boundary

No production HDC interpreter or real trace corpus is present, so the real HDC A/B is not run. No fixed LLM endpoint/model credentials are present. LongMemEval-V2, LoCoMo-Plus, and PersonaMem-v2 are not installed. None is replaced with oracle heads or synthetic vectors.
