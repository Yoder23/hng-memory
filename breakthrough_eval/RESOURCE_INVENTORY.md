# Breakthrough resource inventory

Audit date: 2026-08-31. Machine-readable source: RESOURCE_INVENTORY.json.

GitHub is intentionally disconnected. The previously configured Yoder23 credential and remote
were rejected by the user as belonging to Tao Yu, then removed. No push destination is configured
until the user authenticates the correct account.

## Available

- Frozen release worktree at C:\\tmp\\hng-breakthrough-baseline-e57, exact commit
  e57db1b1e92329e9b8f2b173be9a506d2b898da8.
- Production HNG 0.7 package source and tests in baseline_source/hng-frontier-0.5.1a1/.
- Ollama with fixed strong local reader qwen3.8:27b-q4_K_M, digest
  25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e,
  27.3B parameters, Q4_K_M, 262,144-token declared context.
- qwen3-coder:latest is available, but is another Qwen-family model and cannot satisfy a
  cross-family claim.
- Official QMSum test JSONL in the existing pinned checkout.
- FAISS CPU 1.15.0 and USearch 2.26.1 vendor environments.
- Intel Core i9-12900H (14 physical / 20 logical cores), 68,473,409,536 bytes RAM,
  NVIDIA RTX 3080 Laptop GPU 16 GB (driver 591.44), Windows build 26200,
  Python 3.10, NumPy 2.2.6/OpenBLAS 0.3.29.

## Unavailable or not yet installed

- **Real HDC assistant gate:** no production HNG-integrated HDC assistant, trained production
  interpreter checkpoint, frozen action library, or real interaction trace corpus is present.
  C:\\Python310\\trainslm contains prototype integration code but no usable trained model.
  This gate is BLOCKED_EXTERNAL; synthetic semantics are forbidden as a substitute.
- LongMemEval-V2, LoCoMo-Plus, PersonaMem-v2, PersonaMem, LaMP, GovReport, and BillSum are
  not installed locally.
- No paid hosted-judge credential or spend authorization is assumed.
- Hindsight, MAGMA, Mem0, Zep, Letta, APEX-MEM, and Memory-R1 are not locally installed
  end-to-end. They remain undefeated.

## Feasible next experiment

The fixed-candidate LLM test can run locally without changing model weights. It will freeze the
Ollama model digest, prompt template, task, candidate IDs/order, generation options, token budget,
and random seed. The only variable is the rendered memory system. Ordinary candidate context,
StrongStructuredBaseline, and HNG must receive the same candidate metadata.
