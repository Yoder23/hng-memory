# Publication plan for HNG 0.6

## Defensible current claim

HNG 0.6 is an evidence-governed memory/control architecture that fixes the reproduced duplicate, stale-evidence, poisoning, missing-state, loose-threshold, and uncertain-profile failures while preserving deterministic HDC continuity and 0.5 compatibility.

The local evidence supports a systems/software contribution. It does not yet support a state-of-the-art cognitive-substrate claim.

## Required public experiments

1. LongMemEval-V2 with one frozen interpreter/reader across no memory, hybrid RAG, structured memory, and HNG-governed memory.
2. PersonaMem-v2 with structured profile, dense multi-head, RAG history, and governed profile memory.
3. Full QMSum plus GovReport/BillSum using BM25, dense, hybrid, RAPTOR/SVD-RAG where runnable, and hybrid + governance.
4. Same-model tool-agent harness measuring task success, repeated failures, regret, constraint violations, stale advice, unsupported action, and abstention.
5. Multi-process persistence/freshness stress with interrupted FAISS rebuild and concurrent profile/supersession updates.
6. Independent attack set not used to design the trust policy.

## Ablations

- no required-state contract;
- no source-event deduplication;
- no temporal/version filter;
- no supersession;
- no trust policy;
- no profile confidence;
- no structured authority gate;
- no exact per-head floors;
- FAISS versus reference candidate provider;
- raw hybrid RAG versus hybrid + governance.

## Claims prohibited until evidence exists

- state-of-the-art long-horizon assistant memory;
- HDC superiority over dense or structured representations;
- superior document retrieval or summarization;
- universal poisoning resistance;
- production-safe autonomous hard gating;
- ANN novelty.

## Release evidence package

Publish frozen code, wheel, hashes, environment, exact scripts, raw JSON, full failures, and baseline red-team artifacts. Separate locally executed, public reproduced, and literature-only evidence exactly as in `research_eval/`.

