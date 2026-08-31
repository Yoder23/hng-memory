# Track A: cognitive and long-horizon memory

## Verdict

HNG demonstrates a useful deterministic control pattern on its native synthetic workload, but it does not establish public long-horizon assistant performance. The dominant local gain comes from exact state carry, not associative retrieval: carried-state accuracy is 100%, while the ambiguous current-turn-only baseline is 0.78% in the ablation and retrieval-only ambiguity is 0% in the full gauntlet.

## Executed evidence (Tier A)

The fresh full behavioral gauntlet used 4,096-bit heads, 20,480 history records, a 16,384-action library, and a 20,000-turn stream. It was reached with a labeled Windows-only no-op `fsync` compatibility shim after preserving the untouched durability failure.

| Test | HNG result | Interpretation |
|---|---:|---|
| Cross-chat episode recall | 100% | Works on generated, exactly encoded state/goal/entity heads. |
| Historical action exact top-1 | 100% | Transition lookup works in-distribution. |
| Ambiguous turn with carried state | 100% | Strong result for deterministic continuity. |
| Ambiguous turn, retrieval only | 0% | ANN cannot recover information absent from the query. |
| Changed world with sequence supplied | 100% | Independent heads route correctly when the interpreter supplies the changed variable. |
| Changed world without sequence | 100% obsolete-action rate | Critical system-level failure: missing semantics are not inferred. |
| Support / challenge / unseen action | 100% in shipped cases | External decision vocabulary behaves as designed. |
| Accuracy at 15% query-bit noise | 98.958% | Strong, but the shipped 100% claim did not reproduce. |
| Restart action accuracy | 100% | Behavioral replay only; crash durability was not validated. |
| 20K throughput | 2,285 records/s | Median append 0.226 ms; restart 672 ms in the compatibility run. |

The smaller 2,048-bit ablation confirms causality:

| Mode | Accuracy / rate |
|---|---:|
| Raw HDC action scan top-1 | 7.8125% |
| HNG history action top-1 | 100% |
| Cross-chat evidence rate | 100% |
| Ambiguous current turn only | 0.78125% |
| HNG carried state | 100% |

This is valuable for an HDC-native interpreter whose state vector is already authoritative. It does not show that HNG can extract the correct state from natural-language histories.

## Public benchmark status (Tier B)

LongMemEval-V2, LoCoMo-Plus, original LongMemEval, and LoCoMo were investigated but not executed. A fair run requires a production text-to-HDC interpreter and a fixed reader/generator shared by every backend. The release supplies only synthetic encoders and no model stack. Substituting ground-truth benchmark labels into HNG heads would violate the fairness rule, while constructing a new learned interpreter after inspecting the tests would no longer be an untouched baseline.

Therefore:

- there is no Tier B evidence for state recall, temporal reasoning, premise awareness, action regret, or downstream task success;
- Hindsight, MAGMA, APEX-MEM, Memory-R1, and Letta were not counted as HNG losses in direct benchmark tables, but their public evidence sets the relevant bar;
- the synthetic cross-chat result cannot be presented as a LongMemEval result.

## Architecture challenge

### Is it better than ordinary RAG?

For elliptical immediate turns, yes in the narrow sense that a committed state variable is categorically better than retrieving similar old text. That is an explicit state-machine advantage, not an ANN advantage. For cross-chat and general long-horizon recall on human language, the evidence is unresolved.

### Is it better than structured agent memory?

Not established. A versioned relational event store can represent `state + goal + action -> next_state + outcome`, carry the current state by key, deduplicate events, expire stale evidence, and apply exact policy filters. HNG adds a native HDC addressing interface and full-vector similarity floors; it does not locally beat such a system end to end.

### Does better retrieval improve the assistant?

Not tested with a common LLM/interpreter, so no downstream behavioral claim is justified. The release demonstrates memory decisions, not completed language-agent tasks.

## Recommendation

Keep deterministic working-state carry, transition/outcome records, evidence provenance, and explicit support/challenge/conflict/insufficient decisions. Add mandatory schema validation for required heads, temporal supersession, deduplication, trust/source weights, and recency-aware conflict handling before allowing decisions to control actions. Evaluate that subsystem in advisory mode on LongMemEval-V2 with one frozen interpreter and reader before calling it a cognitive substrate.

