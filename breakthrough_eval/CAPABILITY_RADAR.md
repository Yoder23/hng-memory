# Capability radar

The radar measures **evidence maturity**, not perceived capability quality. This avoids assigning
subjective performance scores to unrun tracks.

- 0: no qualifying downstream evidence;
- 1: local or synthetic evidence;
- 2: public data under a noncanonical/local protocol;
- 3: canonical public or real paired evidence.

| Capability | Maturity | Current evidence |
|---|---:|---|
| working-state continuity | 1 | frozen local gauntlets |
| long-term factual memory | 0 | not run |
| dynamic-state tracking | 1 | public pilot in progress; no score yet |
| temporal reasoning | 1 | synthetic fixed candidates |
| episodic recall | 1 | frozen local gauntlets |
| action/outcome experience | 1 | synthetic only |
| workflow knowledge | 1 | public pilot in progress |
| environment gotchas | 1 | public pilot in progress |
| contradiction | 1 | synthetic fixed candidates |
| belief revision | 0 | not run |
| abstention | 1 | synthetic fixed candidates |
| personalization | 1 | synthetic perspective only |
| authority awareness | 1 | synthetic fixed candidates |
| document QA | 2 | official QMSum data, noncanonical retrieval probe |
| global corpus understanding | 0 | not run |
| RAG governance | 1 | synthetic fixed-candidate LLM study |
| provenance | 0 | no behavioral ablation |
| poison resistance | 1 | synthetic fixed candidates |
| multi-user isolation | 1 | synthetic small scale |
| tool-agent assistance | 0 | not run |
| efficiency | 1 | frozen local component profile |

No axis currently reaches level 3. The machine-readable source is `CAPABILITY_RADAR.json`.
