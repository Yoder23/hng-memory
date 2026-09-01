# Invalid shared-SQLite root-cause matrix

The one exact run from preregistered commit
`71706b2a06daa56745f878eb7918d9cd3baa81ee` is **INVALID** and is not retried.
All 48 children returned reports with zero errors and zero nonzero exits, and
all reader checks were well formed. Idle and isolated-SQLite controls met every
validity criterion. Several shared-database writers produced only 72 to 79
self-samples because long workload operations delayed the sampler embedded in
the same loop, below the frozen minimum of 80.

The fail-closed outcome is therefore `ERROR/INVALID`. Descriptively, the idle
and isolated medians were both about 0.667 handles/minute, while the two shared
conditions were 32.360 and 17.334 handles/minute, with synchronized positive
growth in every child. Those values strongly motivate a new design but cannot
satisfy this run's frozen decision. The follow-up must use an independent
sampler thread and a separately frozen replication rule.

The original result, event ledger, and 48 content-addressed child ledgers are
preserved unchanged.
