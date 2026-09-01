# Evidence governance: public status

The mature synthetic governance suite contains exactly 250 frozen scenarios across duplicate,
stale-environment, wrong-tenant, wrong-role, poison, supersession, conflict, irrelevant-state,
sparse-verified, and authority-mismatch families. It includes calibration buckets, paired bootstrap,
McNemar tests, append-only raw events, and fixed candidate hashes.

This is not a public benchmark. Its strongest result is architectural rather than brand-specific:
both production HNG and an independently implemented simple typed policy reach 90%, while raw
candidate majority reaches 10%. The simple policy fully reproduces HNG's decisions and failures.

A provenance-specific ablation isolates the 25 frozen poison cases. Removing provenance from the
decision or merely displaying it yields 0/25 correct; using it in governance yields 25/25 for both
HNG and StrongStructuredBaseline (paired exact McNemar versus no-provenance p < 1e-7). HNG versus
StrongStructuredBaseline is an exact tie. This demonstrates that provenance must affect decisions,
but not that HNG is better than a simple typed trust policy.

The completed LongMemEval-V2 pilot is the first pinned public-data fixed-candidate test. Its corpus
is clean and lacks rich trust/tenant/version metadata. HNG, StrongStructuredBaseline, and BM25 all
retain identical candidates/prompts and score 4/21. The exact aggregate tie shows that evidence
governance cannot create value when the benchmark supplies no governance-relevant distinction. A
qualifying public governance claim still requires a released corruption/versioning extension with
non-oracle labels.
