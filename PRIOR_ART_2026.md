# Prior-art adoption update

Research cutoff remains 2026-08-31. The full independent source-by-source review is in `research_eval/PRIOR_ART.md`.

HNG 0.6 adopts rather than ignores the strongest relevant ideas:

| Prior-art lesson | 0.6 response |
|---|---|
| MemGPT/Letta: explicit memory management and bounded context | deterministic working state and bounded `GovernedMemoryFrame` |
| Hindsight: separate observations, experience, opinions/beliefs | explicit evidence kinds and fact/belief/hypothesis trust weights |
| MAGMA/APEX-MEM: structured relations and temporal state | source-event identity, episodes, versions, validity, supersession |
| Memory-R1: memory operations such as add/update/delete/no-op | append, invalidate, supersede, deterministic state update; raw evidence retained |
| PersonaMem/LaMP: personalization needs real public evaluation | structured uncertain profiles; no HDC superiority claim |
| FAISS binary indexes | production Hamming provider and scale-based modes |
| USearch | provider interface retained for future high-update evaluation |
| Milvus/Weaviate multi-vector | provider/fusion layer; exact HNG floors remain final |
| RAPTOR/GraphRAG/SVD-RAG | external optional hierarchy; old HNG segmentation demoted |
| agidb/Kohaku and HDC associative memory | native HDC continuity retained; associative memory itself not claimed novel |

The research claim is now narrow: **evidence governance over episodic assistant memory**, combining deterministic semantic state, typed transitions/outcomes, exact applicability, independence, temporal validity, trust, perspective eligibility, provenance, and external abstaining action assessment.

This architecture still requires public comparisons with Hindsight, MAGMA, APEX-MEM, Memory-R1, Letta, PersonaMem-v2, and long-document systems. Unavailable systems remain un-defeated.

