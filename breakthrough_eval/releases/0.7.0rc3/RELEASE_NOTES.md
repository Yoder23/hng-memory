# HNG Frontier 0.7.0rc3 release notes

Version 0.7.0rc3 is a reproducibility and packaging correction over rc2. A new clone and virtual
environment installed rc2 successfully but proved that the documented repository evaluation
surface had no installed `hng-eval` command.

Rc3 adds a fail-closed console dispatcher that locates or accepts a repository root and invokes
`breakthrough_eval/scripts/reproduce.py` with the installed interpreter and no shell. It also adds
an explicit `fresh-clone-core` command after the first actual core run exposed four tests that
depend on the intentionally uncommitted official LoCoMo `task_eval` checkout. Those exclusions are
declared in the command; the configured-environment suite continues to run every test.

The fresh-clone audit also exposed and preserved two additional failures: invalid reranker
dimensions imported optional `torch` before validation, and the deterministic reproduction command
targeted an existing frozen raw log. Rc3 validates dimensions before optional imports and writes
fresh-clone deterministic output to an ignored, isolated proof directory. The qualifying run from
exact pushed commit `27e4a8ee0012f7eef1a9b3655fb8d454aa14c3ab` passes 58 dependency-free
tests, executes all 250 scenarios with candidate identity verified, and recompiles 230 result rows
and 22 scoreboard rows through the installed `hng-eval` entry point.

This release changes no memory behavior, retrieval policy, model, database schema, or research
result. The rc1 baseline remains frozen at commit
`e57db1b1e92329e9b8f2b173be9a506d2b898da8`.
