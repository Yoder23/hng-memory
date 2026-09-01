# Breakthrough resource inventory

Audit date: 2026-09-01. Machine-readable source: RESOURCE_INVENTORY.json.

GitHub is connected to the user-confirmed account Yoder23. The only remote is the private
repository at https://github.com/Yoder23/hng-memory.git; local main, origin/main, and GitHub were
verified through fresh-clone source commit 27e4a8ee0012f7eef1a9b3655fb8d454aa14c3ab on
2026-09-01.

## Available

- Frozen release worktree at C:\\tmp\\hng-breakthrough-baseline-e57, exact commit
  e57db1b1e92329e9b8f2b173be9a506d2b898da8.
- Production HNG 0.7 package source and tests in baseline_source/hng-frontier-0.5.1a1/.
- Qualified HNG 0.7.0rc3 wheel and sdist under
  breakthrough_eval/releases/0.7.0rc3/qualified_dist, with SHA-256 manifest, changelog, rc3
  migration guide, and installed `hng-eval` proof from a brand-new exact-commit clone. The proof
  passes 58 dependency-free tests, deterministic 250, and compiler regeneration; its four external
  LoCoMo exclusions are explicit. The configured suite passed 94 tests at rc3 qualification and
  passes 103 after the sustained-reliability harness was added.
- Ollama with fixed strong local reader qwen3.8:27b-q4_K_M, digest
  25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e,
  27.3B parameters, Q4_K_M, 262,144-token declared context.
- qwen3-coder:latest is available, but is another Qwen-family model and cannot satisfy a
  cross-family claim.
- Ollama Mistral Small 3.1 `mistral-small3.1:24b-instruct-2503-q4_K_M`, digest
  b9aaf0c2586a8ed8105feab808c0f034bd4d346203822f048e2366165a13f4ea, is qualified as a
  genuinely different `mistral3` reader family: 24.0B parameters, Q4_K_M, 131,072-token declared
  context. Its development-only JSON-schema smoke is preserved with no holdout inference.
- Official Qwen3-Reranker-0.6B at repository revision
  e61197ed45024b0ed8a2d74b80b4d909f1255473 is installed for local Transformers/CUDA inference;
  model.safetensors SHA-256 is
  27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b.
- Official QMSum test JSONL in the existing pinned checkout.
- Official LoCoMo-Plus repository at commit
  059f4e3d38f7f1f96765e8e2cb7de3097551bffb; both released inputs are pinned by SHA-256 and
  the upstream unified-input generator produced 2,387 samples.
- Official LongMemEval-V2 repository at commit
  2cc8c540bdb87fe6761629b585e727e1c4704520; the 451-question small text tier, 1,870
  trajectories, 451 haystack mappings, and question screenshots pass the upstream validator
  with trajectory screenshot checking disabled.
- Official PersonaMem-v2 repository at commit
  dd52429f83ced4394be46c3849186a423942b2a5 and dataset revision
  0622e56d1cc6f1bc990a5100a6ec4022a60e66a6; the 5,000-row text benchmark and all 1,998
  released 32K histories are present, and all 200 uniquely referenced histories resolve.
- FAISS CPU 1.15.0 and USearch 2.26.1 vendor environments.
- Intel Core i9-12900H (14 physical / 20 logical cores), 68,473,409,536 bytes RAM,
  NVIDIA RTX 3080 Laptop GPU 16 GB (driver 591.44), Windows build 26200,
  Python 3.10, NumPy 2.2.6/OpenBLAS 0.3.29.
- Preregistered bounded million-write production-store result at commit
  bc18cf4f21869c92b98b26ad79219498e532358b: 1,000,000 durable appends, 9/9 graceful
  restart checks, exact 100-tenant isolation, lifecycle checks, and full-ledger backup/restore
  identity pass. Runtime files are Git-ignored; their independently verified SHA-256 values and
  byte sizes are retained in `reliability/million_write/RESULTS.json`.
- Exact sustained 12-process attempt at commit
  d3cef83d1f4d86ab4efe1bcbaa8cf77f4b8b2ccf is preserved as
  `INTERRUPTED_FAIL`: the first online backup starved, zero backup cycles
  completed, the 15-minute rotation was missed, and safety interruption
  stopped all workers. Machine postmortem:
  `reliability/sustained_2h/INTERRUPTED.json`.

## Unavailable or not yet installed

- **Real HDC assistant gate:** no production HNG-integrated HDC assistant, trained production
  interpreter checkpoint, frozen action library, or real interaction trace corpus is present.
  C:\\Python310\\trainslm contains prototype integration code but no usable trained model.
  This gate is BLOCKED_EXTERNAL; synthetic semantics are forbidden as a substitute.
- LongMemEval-V2 trajectory screenshots are not installed (the text path and question images are
  present). PersonaMem, LaMP, GovReport, and BillSum are not installed locally. PersonaMem-v2's
  official dense and agentic systems are also not installed.
- No paid hosted-judge credential or spend authorization is assumed.
- Hindsight, MAGMA, Mem0, Zep, Letta, APEX-MEM, and Memory-R1 are not locally installed
  end-to-end. They remain undefeated.

## Completed public pilots

LongMemEval-V2, LoCoMo-Plus, and PersonaMem-v2 noncanonical pilots are complete, with all losses
preserved. PersonaMem-v2 freezes the reader digest and fixed retrieval candidates; `pref_type`
defines strata only, while row selection and retrieval exclude answer options, preference/profile
text, and oracle snippets. Official answers are loaded only after sample selection and retrieval.
HNG ties the strongest local controls in all three public-data pilots.
