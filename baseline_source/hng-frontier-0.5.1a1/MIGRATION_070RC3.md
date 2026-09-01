# Migrating from 0.7.0rc2 to 0.7.0rc3

No database, API, memory, or configuration migration is required. Version 0.7.0rc3 adds only the
installed `hng-eval` console dispatcher and its packaging/reproduction tests.

From a repository checkout, install the package and invoke the existing evaluation surface:

```powershell
python -m pip install baseline_source/hng-frontier-0.5.1a1
hng-eval --repo-root . --dry-run core
```

The command fails closed when the supplied/current directory is not inside a checkout containing
`breakthrough_eval/scripts/reproduce.py`. Expensive or external evaluations retain their existing
explicit flags, pinned artifacts, and preregistration requirements; the dispatcher does not bypass
them.
