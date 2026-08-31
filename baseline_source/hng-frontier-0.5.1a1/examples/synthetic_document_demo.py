from __future__ import annotations

from pathlib import Path
import shutil
import numpy as np

from hngfrontier import CallableDocumentAdapter, DocumentUnitEncoding, HDCDocumentMemory

DIM = 2048


def hv(seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 2, size=DIM, dtype=np.uint8)


def noisy(v: np.ndarray, frac: float, seed: int) -> np.ndarray:
    out = np.array(v, copy=True)
    rng = np.random.default_rng(seed)
    idx = rng.choice(out.size, size=max(1, int(out.size * frac)), replace=False)
    out[idx] ^= 1
    return out


# A tiny synthetic technical document with three semantic regions.  The adapter stands in
# for an application-owned HDC document interpreter: HNG receives native semantic states,
# not embeddings or LLM-generated summaries.
topics = {
    "storage": hv(10),
    "retrieval": hv(20),
    "safety": hv(30),
}
roles = {
    "body": hv(100),
    "claim": hv(101),
    "caveat": hv(102),
    "conclusion": hv(103),
}
entities = {
    "memory": hv(200),
    "index": hv(201),
    "agent": hv(202),
}

rows = [
    ("The memory store persists native HDC state.", 0, "storage", "claim", "memory"),
    ("Packed states are stored separately from derived routing data.", 0, "storage", "body", "memory"),
    ("A corrupted source state cannot be repaired from a derived index alone.", 0, "storage", "caveat", "memory"),
    ("Associative routing narrows the semantic candidate set.", 1, "retrieval", "claim", "index"),
    ("The final candidates are verified against full HDC state.", 1, "retrieval", "body", "index"),
    ("An index may lag new writes while a fresh tail remains exactly searchable.", 1, "retrieval", "caveat", "index"),
    ("Historical outcomes can challenge a proposed agent action.", 2, "safety", "claim", "agent"),
    ("Missing evidence is returned as insufficient evidence rather than support.", 2, "safety", "body", "agent"),
    ("Memory is evidence, not a complete safety policy.", 2, "safety", "caveat", "agent"),
    ("The system therefore acts as an external semantic evidence plane.", 2, "safety", "conclusion", "agent"),
]


def encode(text: str, *, context):
    _ = text
    _, _, topic_name, role_name, entity_name = rows[context.ordinal]
    topic = noisy(topics[topic_name], 0.02, 1000 + context.ordinal)
    claim = noisy(topics[topic_name], 0.06 if role_name == "body" else 0.02, 2000 + context.ordinal)
    entity = noisy(entities[entity_name], 0.02, 3000 + context.ordinal)
    evidence = noisy(claim, 0.02, 4000 + context.ordinal)
    role = noisy(roles[role_name], 0.01, 5000 + context.ordinal)
    return DocumentUnitEncoding(
        heads={"topic": topic, "claim": claim, "entity": entity, "evidence": evidence, "role": role},
        kind=role_name,
        importance=0.9 if role_name in {"claim", "caveat", "conclusion"} else 0.2,
    )


root = Path("/tmp/hng-frontier-document-demo")
shutil.rmtree(root, ignore_errors=True)

with HDCDocumentMemory(
    root,
    hv_dim=DIM,
    space_id="synthetic-doc-demo-v1",
    auto_index=False,
    index_options={"table_count": 12, "bits_per_table": 10, "sketch_bits": 128},
) as docs:
    docs.ingest(1, [(text, section) for text, section, *_ in rows], CallableDocumentAdapter(encode))
    docs.rebuild_index()

    frame = docs.summarize_document(
        1,
        budget_units=7,
        discover_structure=True,
        priority_role_queries={
            "caveat": roles["caveat"],
            "conclusion": roles["conclusion"],
        },
        priority_similarity=0.90,
    )

    print("SEMANTIC SEGMENTS:", len(frame.segments))
    print("SELECTED EVIDENCE:", len(frame.selected_records))
    print("NATIVE HDC HEADS:", sorted(frame.to_hdc_context()["document_heads"]))
    print()
    print(frame.to_context_text())
