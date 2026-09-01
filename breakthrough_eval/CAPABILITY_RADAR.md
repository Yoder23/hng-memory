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
| long-term factual memory | 2 | LongMemEval-V2 and LoCoMo-Plus noncanonical negative results |
| dynamic-state tracking | 2 | completed LongMemEval-V2 pilot; all retrieval arms 0/6 |
| temporal reasoning | 2 | completed public noncanonical pilots |
| episodic recall | 2 | completed LoCoMo-Plus public-data pilot |
| action/outcome experience | 1 | synthetic executing probe; HNG loses to nearest experience |
| workflow knowledge | 2 | completed LongMemEval-V2 pilot; retrieval arms 1/6 |
| environment gotchas | 2 | completed LongMemEval-V2 pilot; retrieval arms 2/3 |
| contradiction | 1 | synthetic fixed candidates |
| belief revision | 1 | synthetic component probe; HNG ties strong authority policy |
| abstention | 1 | synthetic fixed candidates |
| personalization | 2 | PersonaMem-v2 public-data pilot; HNG ties BM25/Strong/full history |
| authority awareness | 1 | synthetic fixed candidates |
| document QA | 2 | official QMSum data, noncanonical retrieval probe |
| global corpus understanding | 0 | not run |
| RAG governance | 2 | public-data fixed-candidate pilots; HNG ties Strong/BM25 |
| provenance | 1 | synthetic behavioral ablation; HNG ties Strong |
| poison resistance | 1 | synthetic fixed candidates |
| multi-user isolation | 1 | local 100K-principal scoped probe; zero scoped leaks, raw APIs remain privileged/unscoped |
| tool-agent assistance | 0 | not run |
| efficiency | 2 | public-pilot token and latency measurements |

No axis currently reaches level 3. The machine-readable source is `CAPABILITY_RADAR.json`.
