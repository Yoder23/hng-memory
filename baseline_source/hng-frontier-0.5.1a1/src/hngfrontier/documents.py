from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol, Sequence

import numpy as np

from .multihead import MultiHeadMemory, MultiHeadRecall
from .store import ExperienceRecord, MemoryFilter
from .vectors import hamming_similarity, pack_hv, unpack_hv


PRIORITY_KINDS = frozenset({"warning", "caveat", "limitation", "contradiction", "conclusion"})


@dataclass(frozen=True, slots=True)
class DocumentAdapterContext:
    document_id: int
    ordinal: int
    section_id: int
    previous_heads: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class DocumentUnitEncoding:
    heads: Mapping[str, object]
    kind: str = "body"
    importance: float = 0.0
    tags: tuple[str, ...] = ()
    claim_key: str = ""
    polarity: int = 0
    extra: Mapping[str, object] | None = None


class DocumentSemanticAdapter(Protocol):
    """Application-owned raw-unit -> native HDC document-state bridge."""
    def encode_unit(self, text: str, *, context: DocumentAdapterContext) -> DocumentUnitEncoding: ...


@dataclass(frozen=True, slots=True)
class CallableDocumentAdapter:
    fn: object

    def encode_unit(self, text: str, *, context: DocumentAdapterContext) -> DocumentUnitEncoding:
        out = self.fn(text, context=context)  # type: ignore[misc]
        if isinstance(out, DocumentUnitEncoding):
            return out
        if isinstance(out, Mapping):
            return DocumentUnitEncoding(heads=out)
        raise TypeError("document adapter must return DocumentUnitEncoding or head mapping")


def bundle_hvs(vectors: Sequence[object] | np.ndarray, hv_dim: int) -> np.ndarray:
    """Majority-bundle binary/bipolar HDC vectors into one bipolar prototype."""
    if isinstance(vectors, np.ndarray) and vectors.ndim == 2 and vectors.shape[1] == hv_dim:
        arr = vectors
    else:
        arr = np.asarray([np.asarray(v).reshape(-1) for v in vectors])
    if arr.ndim != 2 or arr.shape[0] == 0 or arr.shape[1] != hv_dim:
        raise ValueError("bundle_hvs requires a non-empty [N, hv_dim] matrix")
    if arr.dtype == np.bool_ or np.all((arr == 0) | (arr == 1)):
        ones = arr.astype(np.int32, copy=False).sum(axis=0)
        bits = ones * 2 >= arr.shape[0]
    elif np.all((arr == -1) | (arr == 1)):
        # Deterministic tie break to +1. This is important for reproducible summaries.
        bits = arr.astype(np.int32, copy=False).sum(axis=0) >= 0
    else:
        raise ValueError("vectors must be binary/bipolar")
    return np.where(bits, 1, -1).astype(np.int8)


def bundle_packed(packed: np.ndarray, hv_dim: int) -> np.ndarray:
    packed = np.asarray(packed, dtype=np.uint8)
    if packed.ndim != 2 or packed.shape[0] == 0:
        raise ValueError("packed must be a non-empty matrix")
    bits = np.unpackbits(packed, axis=1, bitorder="little", count=int(hv_dim))
    return np.where(bits.sum(axis=0, dtype=np.int32) * 2 >= bits.shape[0], 1, -1).astype(np.int8)


@dataclass(frozen=True, slots=True)
class DocumentSegment:
    segment_id: int
    start_ordinal: int
    end_ordinal: int
    slots: tuple[int, ...]
    representative_slot: int
    prototype_heads: Mapping[str, np.ndarray]

    def as_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "start_ordinal": self.start_ordinal,
            "end_ordinal": self.end_ordinal,
            "slots": list(self.slots),
            "representative_slot": self.representative_slot,
        }


@dataclass(frozen=True, slots=True)
class DocumentSummaryFrame:
    """LLM-free document synopsis produced from HDC state + authoritative source units.

    ``document_heads`` and each segment prototype are the native semantic summary for an
    HDC consumer. ``selected_records`` is an extractive evidence view for humans/LLMs.
    No generated prose is required to create the frame.
    """

    document_id: int
    unit_count: int
    segments: tuple[DocumentSegment, ...]
    document_heads: Mapping[str, np.ndarray]
    selected_records: tuple[ExperienceRecord, ...]
    priority_records: tuple[ExperienceRecord, ...]
    discovered_structure: bool
    boundary_threshold: float | None

    @property
    def selected_slots(self) -> tuple[int, ...]:
        return tuple(r.slot for r in self.selected_records)

    def as_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "unit_count": self.unit_count,
            "segment_count": len(self.segments),
            "selected_records": [
                {
                    "slot": r.slot,
                    "section_id": r.episode_id,
                    "record_type": r.record_type,
                    "importance": r.importance,
                    "source": r.source,
                    "extra": dict(r.extra),
                }
                for r in self.selected_records
            ],
            "priority_slots": [r.slot for r in self.priority_records],
            "discovered_structure": self.discovered_structure,
            "boundary_threshold": self.boundary_threshold,
        }

    def to_hdc_context(self) -> dict[str, object]:
        """Native semantic synopsis for an HDC consumer; contains no generated language."""
        return {
            "document_id": self.document_id,
            "document_heads": dict(self.document_heads),
            "segments": tuple({
                "segment_id": s.segment_id,
                "start_ordinal": s.start_ordinal,
                "end_ordinal": s.end_ordinal,
                "prototype_heads": dict(s.prototype_heads),
                "representative_slot": s.representative_slot,
            } for s in self.segments),
            "evidence_slots": self.selected_slots,
        }

    def to_context_text(self, *, max_chars: int = 20_000) -> str:
        lines = [
            f"DOCUMENT MEMORY FRAME document={self.document_id}",
            f"units={self.unit_count} semantic_segments={len(self.segments)} selected={len(self.selected_records)}",
            "SUMMARY EVIDENCE:",
        ]
        by_slot = {r.slot: r for r in self.selected_records}
        priority = {r.slot for r in self.priority_records}
        for seg in self.segments:
            rec = by_slot.get(seg.representative_slot)
            if rec is not None:
                lines.append(f"- segment {seg.segment_id}: {rec.source}")
            for slot in seg.slots:
                if slot in priority and slot != seg.representative_slot and slot in by_slot:
                    p = by_slot[slot]
                    lines.append(f"  - {p.record_type.upper()}: {p.source}")
        text = "\n".join(lines)
        return text[:max_chars]


class HDCDocumentMemory:
    """HDC-native document memory and coverage-oriented summarization.

    The caller's semantic interpreter owns text->HDC conversion. This layer persists the
    units, builds semantic prototypes, performs HDC segmentation/coverage selection, and
    returns a structured/extractive summary frame. It never calls an LLM.
    """

    DEFAULT_HEADS = ("topic", "claim", "entity", "evidence", "role")

    def __init__(self, root, *, hv_dim: int = 10_000, space_id: str = "document-default",
                 heads: Iterable[str] = DEFAULT_HEADS, auto_index: bool = True,
                 index_options: Mapping[str, int] | None = None):
        self.memory = MultiHeadMemory(root, heads=tuple(heads), hv_dim=hv_dim, space_id=space_id,
                                      auto_index=auto_index, index_options=index_options)
        self.hv_dim = int(hv_dim)
        self.heads = self.memory.heads

    def add_unit(self, document_id: int, text: str, heads: Mapping[str, object], *,
                 ordinal: int, section_id: int = 0, kind: str = "body", importance: float = 0.0,
                 tags: Iterable[str] = (), claim_key: str = "", polarity: int = 0,
                 extra: Mapping[str, object] | None = None, durable: bool = False) -> int:
        payload = dict(extra or {})
        payload.update({
            "document_id": int(document_id),
            "ordinal": int(ordinal),
            "section_id": int(section_id),
            "kind": str(kind),
            "claim_key": str(claim_key),
            "polarity": int(polarity),
        })
        return self.memory.remember(
            heads, text, conversation_id=int(document_id), episode_id=int(section_id),
            role="document", record_type=str(kind), namespace="hng.document",
            importance=float(importance), tags=tuple(tags), extra=payload, durable=durable,
        )

    def ingest(self, document_id: int, units: Iterable[tuple[str, int]], adapter: DocumentSemanticAdapter, *,
               durable: bool = False) -> tuple[int, ...]:
        """Ingest ``(text, section_id)`` units through an application-owned HDC interpreter.

        HNG does not call a language model or define text semantics. The adapter receives the
        previous native heads so an HDC encoder can preserve sequence/discourse state.
        """
        slots: list[int] = []
        previous: Mapping[str, object] = {}
        for ordinal, item in enumerate(units):
            text, section_id = item
            ctx = DocumentAdapterContext(int(document_id), int(ordinal), int(section_id), previous)
            enc = adapter.encode_unit(str(text), context=ctx)
            slot = self.add_unit(
                document_id, str(text), enc.heads, ordinal=ordinal, section_id=int(section_id),
                kind=enc.kind, importance=enc.importance, tags=enc.tags, claim_key=enc.claim_key,
                polarity=enc.polarity, extra=enc.extra, durable=durable,
            )
            slots.append(slot); previous = enc.heads
        return tuple(slots)

    def records(self, document_id: int) -> tuple[ExperienceRecord, ...]:
        rows = self.memory.db.con.execute(
            "SELECT slot FROM memories WHERE conversation_id=? AND namespace='hng.document' AND deleted=0 ORDER BY slot",
            (int(document_id),),
        ).fetchall()
        recs = self.memory.db.get_many(int(r[0]) for r in rows)
        recs.sort(key=lambda r: (int(r.extra.get("ordinal", r.slot)), r.slot))
        return tuple(recs)

    def _packed_for_records(self, records: Sequence[ExperienceRecord], head: str) -> tuple[np.ndarray, np.ndarray]:
        bit = self.memory.db.head_bits[head]
        eligible = [r for r in records if (r.head_mask & bit) != 0]
        slots = np.asarray([r.slot for r in eligible], dtype=np.intp)
        return slots, self.memory.vector_stores[head].read_slots(slots) if slots.size else np.empty((0, (self.hv_dim+7)//8), np.uint8)

    @staticmethod
    def _infer_boundary_threshold(similarities: np.ndarray) -> float:
        sims = np.asarray(similarities, dtype=np.float32)
        if sims.size < 3:
            return 0.0
        # Document boundaries are normally rare compared with within-topic adjacencies.
        # Two-means is biased toward splitting the dominant high-similarity population in
        # that imbalanced setting, so use the strongest natural gap in the 1-D spectrum.
        ordered = np.sort(sims)
        gaps = ordered[1:] - ordered[:-1]
        i = int(np.argmax(gaps))
        if float(gaps[i]) < 0.05:
            return float(ordered[0] - 1e-6)  # no convincing semantic boundary
        return float((ordered[i] + ordered[i + 1]) * 0.5)

    def _discover_segments(self, records: Sequence[ExperienceRecord], *, topic_head: str,
                           threshold: float | None = None, min_units: int = 2) -> tuple[list[list[ExperienceRecord]], float]:
        if not records:
            return [], 0.0
        slots, packed = self._packed_for_records(records, topic_head)
        if slots.size != len(records):
            # Structural discovery requires a topic state on each unit. Fall back to one segment.
            return [list(records)], 0.0
        if len(records) == 1:
            return [list(records)], 1.0
        xor = np.bitwise_xor(packed[:-1], packed[1:])
        if hasattr(np, "bitwise_count"):
            diff = np.bitwise_count(xor).sum(axis=1, dtype=np.uint32)
        else:
            from .vectors import POPCOUNT8
            diff = POPCOUNT8[xor].sum(axis=1, dtype=np.uint32)
        sims = 1.0 - diff.astype(np.float32) / float(self.hv_dim)
        t = self._infer_boundary_threshold(sims) if threshold is None else float(threshold)
        boundaries = [0] + [i + 1 for i, s in enumerate(sims) if float(s) < t] + [len(records)]
        segments = [list(records[a:b]) for a, b in zip(boundaries[:-1], boundaries[1:]) if b > a]
        # Merge pathological tiny segments into the previous/next run. This is an HDC synopsis,
        # not a paragraph boundary detector, so one noisy unit should not create a new theme.
        if min_units > 1 and len(segments) > 1:
            merged: list[list[ExperienceRecord]] = []
            pending: list[ExperienceRecord] = []
            for seg in segments:
                if len(seg) < min_units:
                    if merged:
                        merged[-1].extend(seg)
                    else:
                        pending.extend(seg)
                else:
                    if pending:
                        seg = pending + seg; pending = []
                    merged.append(seg)
            if pending:
                if merged: merged[-1].extend(pending)
                else: merged.append(pending)
            segments = merged
        return segments, t

    def _explicit_segments(self, records: Sequence[ExperienceRecord]) -> list[list[ExperienceRecord]]:
        order: list[int] = []
        by: dict[int, list[ExperienceRecord]] = {}
        for r in records:
            sid = int(r.extra.get("section_id", r.episode_id))
            if sid not in by:
                by[sid] = []; order.append(sid)
            by[sid].append(r)
        return [by[sid] for sid in order]

    def _prototype(self, records: Sequence[ExperienceRecord], head: str) -> np.ndarray | None:
        slots, packed = self._packed_for_records(records, head)
        if slots.size == 0:
            return None
        return bundle_packed(packed, self.hv_dim)

    def _representative(self, records: Sequence[ExperienceRecord], prototype: np.ndarray, *, head: str) -> ExperienceRecord:
        slots, packed = self._packed_for_records(records, head)
        if slots.size == 0:
            return max(records, key=lambda r: (r.importance, -r.slot))
        sims = hamming_similarity(packed, pack_hv(prototype, self.hv_dim), self.hv_dim)
        by_slot = {r.slot: r for r in records}
        # Centrality is the primary signal. Importance is deliberately weak so a rare warning
        # does not replace the semantic representative; warnings are selected independently.
        scores = sims * np.float32(0.95) + np.asarray([by_slot[int(slot)].importance for slot in slots], np.float32) * np.float32(0.05)
        i = int(np.argmax(scores))
        return by_slot[int(slots[i])]

    def summarize_document(self, document_id: int, *, budget_units: int = 64, topic_head: str = "topic",
                           discover_structure: bool = False, boundary_threshold: float | None = None,
                           priority_kinds: Iterable[str] = PRIORITY_KINDS,
                           priority_role_queries: Mapping[str, object] | None = None, role_head: str = "role",
                           priority_similarity: float = 0.86) -> DocumentSummaryFrame:
        records = self.records(document_id)
        if not records:
            raise KeyError(f"document {document_id} not found")
        if budget_units <= 0:
            raise ValueError("budget_units must be positive")
        if topic_head not in self.heads:
            raise ValueError(f"unknown topic head {topic_head}")

        # Load each configured semantic head at most once for this synopsis. Earlier versions
        # re-read every segment/head pair separately; that was correct but scaled poorly on
        # 10K-unit documents. The synopsis is a streaming/columnar operation over native HDC
        # states, so keep it that way.
        all_slots = np.asarray([r.slot for r in records], dtype=np.intp)
        slot_to_pos = {r.slot: i for i, r in enumerate(records)}
        packed_by_head: dict[str, np.ndarray | None] = {}
        for head in self.heads:
            bit = self.memory.db.head_bits[head]
            if all((r.head_mask & bit) != 0 for r in records):
                packed_by_head[head] = self.memory.vector_stores[head].read_slots(all_slots)
            else:
                packed_by_head[head] = None

        if discover_structure:
            topic_all = packed_by_head.get(topic_head)
            if topic_all is None:
                groups, used_threshold = [list(records)], 0.0
            elif len(records) == 1:
                groups, used_threshold = [list(records)], 1.0
            else:
                xor = np.bitwise_xor(topic_all[:-1], topic_all[1:])
                if hasattr(np, "bitwise_count"):
                    diff = np.bitwise_count(xor).sum(axis=1, dtype=np.uint32)
                else:
                    from .vectors import POPCOUNT8
                    diff = POPCOUNT8[xor].sum(axis=1, dtype=np.uint32)
                sims = 1.0 - diff.astype(np.float32) / float(self.hv_dim)
                used_threshold = self._infer_boundary_threshold(sims) if boundary_threshold is None else float(boundary_threshold)
                boundaries = [0] + [i + 1 for i, sim in enumerate(sims) if float(sim) < used_threshold] + [len(records)]
                groups = [list(records[a:b]) for a, b in zip(boundaries[:-1], boundaries[1:]) if b > a]
                # Same tiny-run protection as _discover_segments.
                if len(groups) > 1:
                    merged: list[list[ExperienceRecord]] = []
                    pending: list[ExperienceRecord] = []
                    for group in groups:
                        if len(group) < 2:
                            if merged: merged[-1].extend(group)
                            else: pending.extend(group)
                        else:
                            if pending: group = pending + group; pending = []
                            merged.append(group)
                    if pending:
                        if merged: merged[-1].extend(pending)
                        else: merged.append(pending)
                    groups = merged
        else:
            groups = self._explicit_segments(records); used_threshold = None

        def prototype_for(group: Sequence[ExperienceRecord], head: str) -> np.ndarray | None:
            mat = packed_by_head.get(head)
            if mat is not None:
                idx = np.fromiter((slot_to_pos[r.slot] for r in group), dtype=np.intp, count=len(group))
                return bundle_packed(mat[idx], self.hv_dim)
            return self._prototype(group, head)

        document_heads: dict[str, np.ndarray] = {}
        for head in self.heads:
            mat = packed_by_head.get(head)
            p = bundle_packed(mat, self.hv_dim) if mat is not None and mat.size else self._prototype(records, head)
            if p is not None: document_heads[head] = p

        segments: list[DocumentSegment] = []
        representatives: list[ExperienceRecord] = []
        topic_all = packed_by_head.get(topic_head)
        for sid, group in enumerate(groups):
            pheads: dict[str, np.ndarray] = {}
            for head in self.heads:
                p = prototype_for(group, head)
                if p is not None: pheads[head] = p
            topic_proto = pheads.get(topic_head)
            if topic_proto is None:
                rep = max(group, key=lambda r: r.importance)
            elif topic_all is not None:
                idx = np.fromiter((slot_to_pos[r.slot] for r in group), dtype=np.intp, count=len(group))
                sims = hamming_similarity(topic_all[idx], pack_hv(topic_proto, self.hv_dim), self.hv_dim)
                score = sims * np.float32(0.95) + np.asarray([r.importance for r in group], np.float32) * np.float32(0.05)
                rep = group[int(np.argmax(score))]
            else:
                rep = self._representative(group, topic_proto, head=topic_head)
            representatives.append(rep)
            ords = [int(r.extra.get("ordinal", r.slot)) for r in group]
            segments.append(DocumentSegment(sid, min(ords), max(ords), tuple(r.slot for r in group), rep.slot, pheads))

        priority_set = {str(x) for x in priority_kinds}
        if priority_role_queries:
            if role_head not in self.heads:
                raise ValueError(f"unknown role head {role_head}")
            role_all = packed_by_head.get(role_head)
            if role_all is None:
                raise ValueError("priority_role_queries require a role vector on every document unit")
            pmask = np.zeros(len(records), dtype=bool)
            for query in priority_role_queries.values():
                pmask |= hamming_similarity(role_all, pack_hv(query, self.hv_dim), self.hv_dim) >= float(priority_similarity)
            priority = sorted((records[i] for i in np.flatnonzero(pmask)), key=lambda r: (-r.importance, r.slot))
        else:
            priority = sorted((r for r in records if r.record_type in priority_set), key=lambda r: (-r.importance, r.slot))
        selected: dict[int, ExperienceRecord] = {}
        for r in priority:
            if len(selected) >= budget_units: break
            selected[r.slot] = r
        reps_ordered = sorted(representatives, key=lambda r: (-r.importance, r.slot)) if len(priority) + len(representatives) > budget_units else representatives
        for r in reps_ordered:
            if len(selected) >= budget_units: break
            selected.setdefault(r.slot, r)

        if len(selected) < budget_units:
            candidates = [r for r in records if r.slot not in selected]
            selected_pos = [slot_to_pos[s] for s in selected]
            selected_vecs = topic_all[np.asarray(selected_pos, np.intp)] if topic_all is not None and selected_pos else None
            doc_proto = document_heads[topic_head]
            qpacked = pack_hv(doc_proto, self.hv_dim)
            while candidates and len(selected) < budget_units:
                idx = np.fromiter((slot_to_pos[r.slot] for r in candidates), dtype=np.intp, count=len(candidates))
                packed = topic_all[idx] if topic_all is not None else self.memory.vector_stores[topic_head].read_slots(np.asarray([r.slot for r in candidates], np.intp))
                relevance = hamming_similarity(packed, qpacked, self.hv_dim)
                if selected_vecs is None or selected_vecs.size == 0:
                    redundancy = np.zeros(len(candidates), np.float32)
                else:
                    redundancy = np.zeros(len(candidates), np.float32)
                    for sv in selected_vecs:
                        redundancy = np.maximum(redundancy, hamming_similarity(packed, sv, self.hv_dim))
                importance = np.asarray([r.importance for r in candidates], dtype=np.float32)
                score = 0.40 * relevance + 0.35 * importance + 0.25 * (1.0 - redundancy)
                i = int(np.argmax(score)); r = candidates.pop(i)
                selected[r.slot] = r
                rv = (topic_all[slot_to_pos[r.slot]:slot_to_pos[r.slot]+1] if topic_all is not None
                      else self.memory.vector_stores[topic_head].read_slots(np.asarray([r.slot], np.intp)))
                selected_vecs = rv if selected_vecs is None else np.concatenate((selected_vecs, rv), axis=0)

        selected_records = tuple(sorted(selected.values(), key=lambda r: int(r.extra.get("ordinal", r.slot))))
        priority_slots = {r.slot for r in priority}
        priority_records = tuple(r for r in selected_records if r.slot in priority_slots)
        return DocumentSummaryFrame(
            document_id=int(document_id), unit_count=len(records), segments=tuple(segments),
            document_heads=document_heads, selected_records=selected_records,
            priority_records=priority_records, discovered_structure=bool(discover_structure),
            boundary_threshold=used_threshold,
        )

    def query_document(self, document_id: int, query_heads: Mapping[str, object], *, top_k: int = 10,
                       min_similarity: Mapping[str, float] | None = None,
                       required_route_heads: Iterable[str] = (), probe_radius: int = 1) -> MultiHeadRecall:
        return self.memory.recall(
            query_heads, top_k=top_k,
            memory_filter=MemoryFilter(conversation_id=int(document_id), namespace="hng.document"),
            min_similarity=min_similarity, required_route_heads=tuple(required_route_heads),
            probe_radius=probe_radius,
        )

    def query_document_adaptive(self, document_id: int, query_heads: Mapping[str, object], *, top_k: int = 10,
                                min_similarity: Mapping[str, float] | None = None,
                                required_route_heads: Iterable[str] = (), start_radius: int = 1,
                                max_radius: int = 2, min_hits: int = 1) -> MultiHeadRecall:
        return self.memory.recall_adaptive(
            query_heads, top_k=top_k,
            memory_filter=MemoryFilter(conversation_id=int(document_id), namespace="hng.document"),
            min_similarity=min_similarity, required_route_heads=tuple(required_route_heads),
            start_radius=int(start_radius), max_radius=int(max_radius), min_hits=int(min_hits),
        )

    def query_corpus(self, query_heads: Mapping[str, object], *, top_k: int = 10,
                     min_similarity: Mapping[str, float] | None = None,
                     required_route_heads: Iterable[str] = (), probe_radius: int = 1,
                     memory_filter: MemoryFilter | None = None) -> MultiHeadRecall:
        """Recall document evidence across the entire ingested corpus.

        The returned records retain ``conversation_id == document_id`` plus section/ordinal
        provenance. A caller may supply additional eligibility constraints, but the namespace is
        always forced to ``hng.document`` so assistant/event memories cannot contaminate the
        document evidence plane.
        """
        f = memory_filter or MemoryFilter()
        scoped = MemoryFilter(
            conversation_id=f.conversation_id, episode_id=f.episode_id, role=f.role,
            record_type=f.record_type, namespace="hng.document", min_importance=f.min_importance,
            include_deleted=f.include_deleted, tags_all=f.tags_all, tags_any=f.tags_any,
        )
        return self.memory.recall(
            query_heads, top_k=top_k, memory_filter=scoped, min_similarity=min_similarity,
            required_route_heads=tuple(required_route_heads), probe_radius=probe_radius,
        )

    def query_corpus_adaptive(self, query_heads: Mapping[str, object], *, top_k: int = 10,
                              min_similarity: Mapping[str, float] | None = None,
                              required_route_heads: Iterable[str] = (), start_radius: int = 1,
                              max_radius: int = 2, min_hits: int = 1,
                              memory_filter: MemoryFilter | None = None) -> MultiHeadRecall:
        f = memory_filter or MemoryFilter()
        scoped = MemoryFilter(
            conversation_id=f.conversation_id, episode_id=f.episode_id, role=f.role,
            record_type=f.record_type, namespace="hng.document", min_importance=f.min_importance,
            include_deleted=f.include_deleted, tags_all=f.tags_all, tags_any=f.tags_any,
        )
        return self.memory.recall_adaptive(
            query_heads, top_k=top_k, memory_filter=scoped, min_similarity=min_similarity,
            required_route_heads=tuple(required_route_heads), start_radius=int(start_radius),
            max_radius=int(max_radius), min_hits=int(min_hits),
        )

    def rebuild_index(self, head: str | None = None) -> None:
        self.memory.rebuild_index(head)

    def sync(self) -> None:
        self.memory.sync()

    def close(self) -> None:
        self.memory.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
