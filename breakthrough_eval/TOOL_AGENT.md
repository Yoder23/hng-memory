# Tool-agent advisory evaluation

## Controlled executing protocol

The benchmark runs 108 episodes across twelve state slots, three API versions, four operational
roles, and three semantically close actions. Each arm receives the same deterministic task stream,
candidate actions, arguments, tool behavior, mandatory non-memory safety guard, and conflicting
tool observations. The tool mutates state, returns recoverable failures, can produce in-scope
irreversible mistakes, and changes its correct action across API versions.

The compared arms are agent alone, ordinary recent memory, StrongStructuredBaseline, and the
production ToolAgentAdapter in advisory-challenge mode. HNG is never a hard gate. The caller-owned
agent may act without evidence, follows explicit challenges where an alternative is available, and
always remains subject to the same independent safety guard.

## Preserved pre-change failure

The untouched adapter recorded outcome semantics but did not forward temporal validity, tenant,
user, scope, role, or authority fields. A v1 success therefore remained globally applicable and
was assessed as SUPPORT in v2. The frozen pre-change run produced:

| Arm | Task success | Repeated failures | Irreversible mistakes | Decision p95 |
|---|---:|---:|---:|---:|
| Agent alone | 33.3% | 48 | 0 | 0.039 ms |
| Ordinary recent memory | 46.3% | 25 | 30 | 0.035 ms |
| StrongStructuredBaseline | 63.9% | 2 | 0 | 0.013 ms |
| HNG advisory | 29.6% | 38 | 18 | 14.025 ms |

HNG was worse than every memory baseline and worse than agent alone. This loss is preserved in
tool_agent/BEFORE_RESULTS.json and tool_agent/raw/before_events_retry2.jsonl.

## Failure-driven general fix

ToolAgentAdapter.execute now accepts optional TemporalValidity and access/perspective fields and
forwards them to HNGMemory.remember_transition. Existing callers remain compatible because every
new argument is optional. A production regression proves a private v1 outcome is SUPPORT in v1,
is excluded with environment_version_mismatch in v2, and retains its tenant, user, role, and scope.

The identical post-change run produced:

| Arm | Task success | Repeated failures | Irreversible mistakes | Decision p95 |
|---|---:|---:|---:|---:|
| Agent alone | 33.3% | 48 | 0 | 0.029 ms |
| Ordinary recent memory | 46.3% | 25 | 30 | 0.047 ms |
| StrongStructuredBaseline | 63.9% | 2 | 0 | 0.016 ms |
| HNG advisory | 63.9% | 2 | 0 | 1.880 ms |

HNG improves by 34.3 percentage points relative to its untouched implementation, eliminates all
18 irreversible mistakes, and reduces repeated failures from 38 to 2. Against ordinary recent
memory, the post-change paired delta is +17.6 points, McNemar exact p=0.00794, with a paired
bootstrap 95% interval of [+5.6, +29.6] points. Against StrongStructuredBaseline, every episode
matches exactly: delta 0, p=1, and interval [0, 0].

The correct conclusion is a recovered temporal/access-context defect followed by an exact
behavioral tie with the simpler structured policy. HNG remains about two orders of magnitude slower
at p95 on this small in-process benchmark. This does not establish HNG-specific tool-agent
superiority.

## Claim boundary

This is an executing deterministic simulator, but it is synthetic. It uses generated HDC vectors,
not the missing production HDC interpreter, and it is not a recognized public tool-agent benchmark
or a real deployed agent. ToolAgentAdapter remains advisory and must not serve as sole safety
authority. The benchmark demonstrates a supported integration pattern and a fixed production bug;
the program track remains partial.
