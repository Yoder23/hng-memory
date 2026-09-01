# Action experience

## Executed synthetic probe

`scripts/action_experience_probe.py` executes 100 attempts across ten deterministic states, four
semantically similar actions, and an environment-version change at attempt 51. Each arm acts,
observes success/failure, and accumulates experience without changing model weights. The HNG arm
uses the shipped `HNGMemory` store and action evaluator with deterministic synthetic binary vectors.

| Arm | Success | Regret | Repeated failures | Abstentions |
|---|---:|---:|---:|---:|
| Semantic action router | 20% | 80 | 64 | 0 |
| Nearest-neighbor experience | 75% | 25 | 0 | 10 |
| Weighted multi-vector | 68% | 32 | 0 | 20 |
| Structured database | 68% | 32 | 0 | 20 |
| Graph memory | 68% | 32 | 0 | 20 |
| StrongStructuredBaseline | 68% | 32 | 0 | 20 |
| HNG governed transitions | 68% | 32 | 0 | 52 |

HNG's 20-attempt success curve is 35%, 90%, 60%, 55%, then 100%; the drop spans the frozen
environment change. It solves all 20 state/environment combinations, never repeats an already
failed action, and abstains on every decision made before an applicable successful transition is
known. However, it exactly ties the structured/graph/strong policies and loses by 7 percentage
points to the simpler nearest-experience policy. Its extra abstentions do not improve success.

Machine evidence is `action_experience/RESULTS.json`.

## Claim boundary

The simulator executes deterministic actions and measures their outcomes, but it is synthetic, not
a real tool environment or recognized public workload. Its binary vectors are generated for the
harness and cannot be substituted for the missing production HDC assistant/checkpoint.

The broader frozen suite still shows governance of stale environments, wrong actors, untrusted
outcomes, supersession, conflict, sparse verified evidence, and authority mismatch.

A qualifying public benchmark must freeze an action library and environment, expose semantically
close actions with version/user/role-specific outcomes, accumulate attempts without weight updates,
and compare semantic routing, nearest-neighbor experience, weighted vectors, structured SQL, graph
memory, StrongStructuredBaseline, and HNG. Until one is run, this track remains `PARTIAL` and not
run at public quality.
