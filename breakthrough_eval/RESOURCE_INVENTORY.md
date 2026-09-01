# Breakthrough resource inventory

Audit date: 2026-08-31. Machine-readable source: RESOURCE_INVENTORY.json.

GitHub is connected to the user-confirmed account Yoder23. The only remote is the private
repository at https://github.com/Yoder23/hng-memory.git; local main, origin/main, and GitHub were
verified at commit c089b1b93bfaffc9d87bca0861dafe44942e9553 on 2026-08-31.

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
- Official LoCoMo-Plus repository at commit
  059f4e3d38f7f1f96765e8e2cb7de3097551bffb; both released inputs are pinned by SHA-256 and
  the upstream unified-input generator produced 2,387 samples.
- Official LongMemEval-V2 repository at commit
  2cc8c540bdb87fe6761629b585e727e1c4704520; the 451-question small text tier, 1,870
  trajectories, 451 haystack mappings, and question screenshots pass the upstream validator
  with trajectory screenshot checking disabled.
- FAISS CPU 1.15.0 and USearch 2.26.1 vendor environments.
- Intel Core i9-12900H (14 physical / 20 logical cores), 68,473,409,536 bytes RAM,
  NVIDIA RTX 3080 Laptop GPU 16 GB (driver 591.44), Windows build 26200,
  Python 3.10, NumPy 2.2.6/OpenBLAS 0.3.29.

## Unavailable or not yet installed

- **Real HDC assistant gate:** no production HNG-integrated HDC assistant, trained production
  interpreter checkpoint, frozen action library, or real interaction trace corpus is present.
  C:\\Python310\\trainslm contains prototype integration code but no usable trained model.
  This gate is BLOCKED_EXTERNAL; synthetic semantics are forbidden as a substitute.
- LongMemEval-V2 trajectory screenshots are not installed (the text path and question images are
  present). PersonaMem-v2, PersonaMem, LaMP, GovReport, and BillSum are not installed locally.
- No paid hosted-judge credential or spend authorization is assumed.
- Hindsight, MAGMA, Mem0, Zep, Letta, APEX-MEM, and Memory-R1 are not locally installed
  end-to-end. They remain undefeated.

## Active public experiment

The pinned LongMemEval-V2 small-tier text pilot is running locally. It is explicitly noncanonical:
the reader is the frozen local 27B model, trajectory screenshots are omitted, BM25 selects text
state slices, and judge-dependent items use the same local model as judge. Its fixed-candidate arms
freeze candidate order, prompt hash, model digest, generation options, and seed. Official answers
are used only after generation by the official evaluator functions.
