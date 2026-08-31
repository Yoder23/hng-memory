# HNG Frontier 0.5 — Perspective / digital-twin gauntlet

This is an adversarial synthetic HDC benchmark for one question: when the literal semantic situation is the same, can HNG route memory/action evidence according to the person who is asking?

## Workload

- 4,096-bit HDC heads.
- 64 identical semantic contexts evaluated across eight personas.
- Personas vary by role, authority, abstraction level, expertise, and priority.
- 1,536 shared historical transition records.
- 8,192-action HDC library (512 families x 16 deliberately close variants).
- Role HDC states are intentionally close to one another.
- The raw HDC action query identifies the correct 16-action family but not the historically appropriate variant.
- 512 main persona queries.
- 64 same-user active-role switches.
- Private-memory cross-user isolation adversary.
- Durable profile-priority update without rewriting historical transitions.

## Results

| Method | Exact action top-1 |
|---|---:|
| Raw 8,192-action HDC router | **6.25%** |
| HNG semantic memory, no user perspective | **12.5%** |
| HNG role/authority gating only (128-query sample) | **50.0%** |
| HNG soft perspective HDC heads (128-query sample) | **100%** |
| **HNG full perspective-conditioned memory** | **100%** |

Additional results:

- semantic-only role/perspective violation rate: **75%**;
- full HNG perspective violation rate: **0%**;
- full perspective median recommendation latency: **7.16 ms**, p95 **17.28 ms**;
- same durable user switching to an acting role: **100%** correct over 64 queries;
- private-memory isolation: **0 leaks / 2 adversarial checks**;
- profile priority update changed subsequent routing correctly without rewriting historical records.

The soft HDC perspective result is intentionally included: if the assistant can encode the user perspective cleanly in semantic state, HDC similarity can itself be powerful. The hard policy layer is still necessary for access control and for guaranteeing that semantically close but role-inappropriate evidence does not cross an actor boundary.

## Interpretation

This benchmark does **not** prove real-user personalization. It demonstrates the mechanism under controlled HDC geometry:

`same semantic state + different actor perspective -> different evidence -> different appropriate action`.

The public validation target is PersonaMem/PersonaMem-v2 and LaMP-style personalization using real assistant/interpreter traces.
