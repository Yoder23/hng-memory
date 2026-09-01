# Shared-SQLite handle-type diagnostic v2 result

The exact preregistered run from commit
`e43112503899cb11f3808ec6e731f2ab48c9a945` is `ERROR/INVALID`. Every
condition met its independent sampling minimum and the available child reports
contained no workload, reader-integrity, or handle-query errors. However, only
9 of 12 reports reached the parent in each condition. Three children per
condition remained blocked while their multiprocessing queue feeder attempted
to flush the enlarged type-histogram report; the frozen parent joined children
before draining that queue and terminated those three after timeout. The frozen
all-reports and zero-exit controls therefore failed in all four conditions.

The invalid result contains a strong but inadmissible descriptive pattern. The
idle and isolated medians were about 1.017 total handles/minute. The two shared
replications measured 38.634 and 47.795. Among the nine available reports in
each shared replication, the Windows `Section` object was the dominant type:
median deltas of 38 and 47 handles, accounting for 92.7% and 94.0% of positive
median type growth. The controls had zero median `Section` growth.

Those values do not satisfy the frozen decision because the reports are
incomplete. They justify a separately versioned follow-up that drains child
reports concurrently with process exit while leaving the workload, handle
enumeration, thresholds, and decision rule unchanged. This run is never retried
or represented as identifying the dominant handle type.
