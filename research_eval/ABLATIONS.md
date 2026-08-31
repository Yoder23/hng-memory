# Ablation study

No core HNG source was changed. Ablations use shipped switches/workloads or external wrappers over the same generated data. Where a component could not be removed independently without rewriting the implementation, the result is marked not isolated rather than guessed.

| Component removed / changed | Full HNG | Ablated result | What the result supports | Evidence |
|---|---:|---:|---|---|
| Deterministic state carry | 100% ambiguous-turn accuracy | 0.78125% current-turn-only in the small ablation; 0% retrieval-only in the full gauntlet | State carry, not ANN, causes immediate-turn continuity. | Tier A |
| Working-state persistence | 100% restart behavior in compatibility run | Not independently removed; unit replay tests pass, but native Windows `fsync` crashes | Persistence is architecturally required but durability was not established on this OS. | Tier A, incomplete |
| Independent heads, using one composite | 100% targeted synthetic document recall@5 | Composite exact recall@5 also 100% | No multi-head gain on easy synthetic document QA. | Tier A |
| Required `sequence` head omitted | 100% correct new-action routing when supplied | 100% obsolete-action rate without it | Independent heads help only when the interpreter emits the required state variable. | Tier A |
| Exact full-HV action floor loosened | Wrong close action rejected | Wrong action receives `support` | Strict action identity is a real fail-closed control. | Tier A |
| Outcome-conditioned history | 100% history action top-1 | Raw action HDC scan 7.8125% | Historical transition labels disambiguate close actions, though this does not isolate outcomes from all other heads. | Tier A, partial |
| Action-specific strict threshold | `insufficient_evidence` for 5%-different action | Loose caller floor returns `support` | Threshold policy is safety-critical and should not be caller-arbitrary. | Tier A |
| Adaptive probing | Full HNG exact top-1 100% | Not independently isolated | No causal performance claim justified. | Not measured |
| Perspective conditioning | 100% top-1, 0% violations | Semantic-only 12.5%, 75% violations | Actor information matters. | Tier A |
| Hard role / authority gating | 100% full HNG | Hard metadata alone 50%; semantic-only has 75% violations | Hard eligibility is necessary for safety but does not select all variants. | Tier A |
| Expertise / priority heads | 100% full HNG | Not removed one at a time; ordinary dictionary with the same fields is 100% | Fields matter in the generated labels; HDC encoding is not uniquely responsible. | Tier A, partial |
| HDC representation | 100% full perspective | Dense float multi-head 100% on 128 queries | No unique HDC correctness advantage on this task. | Tier A |
| HNG perspective machinery | 100% | Ordinary structured dictionary 100% on 512 queries | Explicit keys fully reproduce this synthetic task and are much faster. | Tier A |
| Document hierarchy | 98.05% synthetic key claims | Public QMSum produces one segment for every document | Hierarchy gain does not transfer to the public workload. | Tier A/B |
| Exception / role document head withheld from baselines | HNG 100% priority/contradictions | Original importance baseline 63.67%/65.10% | Original comparison is information-unequal. | Tier A |
| Same exception / role detections given to baseline | HNG 100/98.05/100/100% | Importance-first baseline 100/100/100/100% | Role labels, not HNG hierarchy, explain the synthetic quality advantage. | Tier A |
| HNGIX routing | 100% exact top-1 | FAISS BinaryIVF also 100%, with lower latency at 100K/1M/10M | ANN implementation does not cause semantic correctness and is replaceable. | Tier A |

## Component attribution

The results support five narrow causal claims:

1. deterministic state carry solves an information-absence problem that retrieval cannot solve;
2. explicit semantic variables prevent incompatible transitions only when supplied;
3. exact action floors prevent close-action overgeneralization;
4. hard metadata gates prevent authority violations;
5. role/exception labels enable document coverage when they are reliable.

They do not support three broader claims:

- HDC is necessary for the personalization result;
- HNGIX is necessary for multi-head memory;
- the current document hierarchy adds value on human-written data.

Adaptive probing, clean outcome-only removal, working-memory removal, expertise-only removal, priority-only removal, and role-head-only removal were not exposed as independent switches. A future publication should make these first-class configurations and run them on public data.

