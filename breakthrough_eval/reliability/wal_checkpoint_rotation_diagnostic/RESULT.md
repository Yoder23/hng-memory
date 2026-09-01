# WAL checkpoint/rotation intervention result

The exact preregistered run from commit
`55c25f1a2416a3848b0f47527099a6d59361363f` completed with `status=PASS` and
the frozen outcome `SUPPORTS_ROTATE_CHECKPOINT_WAL_BOUNDING`.

The untreated 120-second baseline reproduced the mechanism: one process reached
329 handles, every child gained 99 Section handles, the shared WAL-index grew
from one to 100 32-KiB units, and the WAL reached 1,681,635,712 bytes. Its final
row count and evidence generation both exactly matched 1,000 seed records plus
39,205 reported writes; `quick_check=ok`.

Two independent treatments each ran four 30-second fresh-connection epochs,
with all clients stopped before every TRUNCATE checkpoint:

| Treatment | Maximum process handles | Maximum Section delta/epoch | Checkpoints | Post-checkpoint WAL | Throughput vs. baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| replication 0 | 252 | 21 | 4/4 passed | 0 bytes each | 128.3% |
| replication 1 | 256 | 25 | 4/4 passed | 0 bytes each | 113.4% |

All eight checkpoints returned `busy=0` and completed in 0.029-0.041 seconds.
Every epoch reported all 12 children with zero exits, errors, missing reads, or
malformed reads. Both treatment databases ended with `quick_check=ok` and exact
row/generation equality: 32,829 and 39,582 rows respectively. The intervention
did not trade away aggregate operation throughput at the frozen 50% floor.

This validly supports bounded worker-connection epochs plus a fully quiescent
TRUNCATE checkpoint as a mechanism-specific treatment. It is not yet a
two-hour reliability qualification. The next sustained protocol must integrate
the treatment, preserve backup/recovery and integrity gates, and pass the full
duration without relaxing resource limits. `RESULTS.json` and `events.jsonl`
are authoritative.
