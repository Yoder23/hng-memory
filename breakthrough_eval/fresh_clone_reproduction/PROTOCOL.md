# Fresh-clone reproduction protocol

The proof starts from a new private-repository clone at an exact pushed commit and a new virtual
environment. It installs the built wheel, verifies package/runtime/entry-point versions, runs the
installed dispatcher in dry-run mode, then executes an explicitly dependency-free repository core.

The dependency-free suite excludes exactly four LoCoMo modules that import the externally installed
and intentionally uncommitted official `task_eval` package. The normal configured-environment suite
continues to run them. The proof must report these exclusions rather than silently treating external
resources as package dependencies.

Passing requires the installed `hng-eval` executable, a matching rc3 version, a successful dry-run,
dependency-free owned tests, the 250-case deterministic benchmark, compiler completion, exact clone
commit, raw logs, and artifact hashes. The disposable clone may mutate its own generated evidence;
the authoritative source worktree and frozen rc1 baseline must remain unchanged. The deterministic
proof output is therefore written once to `.hng-eval-proof/fixed_candidate`, which is ignored and
separate from committed evidence; an existing proof log remains a fail-closed condition.
