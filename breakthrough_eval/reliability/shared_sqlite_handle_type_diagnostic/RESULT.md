# Shared-SQLite handle-type diagnostic preflight failure

No workload ran. The invocation supplied
`7364134c3be2311f4ba73f85a284977d4c13c2aa`, which did not equal the actual
preregistered `HEAD`, `7364134bc8536d3497a9b77113b3e1b310e25c5e`.
The fail-closed preflight wrote `RESULTS.json` with `status=ERROR` and exited 1
before creating an event ledger or run data.

This is an operator transcription failure, not handle-type evidence. The result
is preserved and this output directory is never reused. A corrected execution
requires a separately versioned output directory and preregistration.
