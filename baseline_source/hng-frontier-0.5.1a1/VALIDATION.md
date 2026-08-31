# HNG Frontier 0.5.0a1 validation

## Automated suite

`30/30` tests pass.

The suite retains all prior assistant/document checks and adds perspective-specific coverage for:

- durable profile + acting-role persistence across restart;
- HDC adapter access to effective perspective;
- exact cross-user private-memory isolation;
- exact tenant isolation with global-memory visibility;
- role/authority gating of semantically attractive but actor-inappropriate evidence;
- same-role disambiguation through expertise/priority HDC heads;
- perspective revision snapshots on historical experiences.

## Perspective gauntlet

See `benchmarks/PERSPECTIVE_GAUNTLET.md` and `.json`.

- 4,096-bit HDC heads;
- 64 semantic contexts x eight personas;
- 1,536 historical transitions;
- 8,192 actions / 16 close variants per family;
- 512 main queries;
- full perspective-conditioned exact action accuracy: **100%**;
- semantic-only exact action accuracy: **12.5%**;
- raw action router exact top-1: **6.25%**, correct family top-16: **100%**;
- semantic-only perspective violation: **75%**;
- full HNG perspective violation: **0%**;
- full conditioned median: **7.16 ms**, p95 **17.28 ms** in this environment;
- active role switch: **64/64**;
- private-memory leakage: **0**;
- durable priority change adapted routing correctly without history rewrite.

## Prior gates retained

The 0.4 document-memory and 0.3.1 assistant-gauntlet artifacts remain part of the repository. Perspective conditioning does not replace deterministic turn continuity or state/action/outcome memory; it adds the missing actor coordinate.

## Remaining external gate

No synthetic test proves real human personalization. Before strong publication claims, replay production HDC traces and run public personalization benchmarks (PersonaMem/PersonaMem-v2/LaMP or equivalent) against profile-in-prompt and retrieval-augmented personalization baselines.
