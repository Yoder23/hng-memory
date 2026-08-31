from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

from .index import HDCIndex
from .store import ExperienceRecord, ExperienceStore, MemoryFilter, Relation
from .vectors import SegmentedNpyVectorStore, VectorProvider, hamming_similarity, pack_hv


class SubsetVectorProvider:
    """Expose sorted global slots as a dense local VectorProvider view."""
    def __init__(self, base: VectorProvider, global_slots: np.ndarray):
        self.base = base
        self.global_slots = np.asarray(global_slots, dtype=np.intp)
        self.hv_dim = base.hv_dim
        self.packed_bytes = base.packed_bytes

    @property
    def count(self) -> int:
        return int(self.global_slots.size)

    def read_slots(self, slots: np.ndarray) -> np.ndarray:
        local = np.asarray(slots, dtype=np.intp)
        return self.base.read_slots(self.global_slots[local])

    def read_range(self, start: int, end: int) -> np.ndarray:
        return self.base.read_slots(self.global_slots[int(start):int(end)])

    def exact_topk(self, query, slots: np.ndarray, top_k: int) -> list[tuple[int, float]]:
        local = np.asarray(slots, dtype=np.intp)
        if top_k <= 0 or local.size == 0:
            return []
        qp = pack_hv(query, self.hv_dim)
        sims = hamming_similarity(self.read_slots(local), qp, self.hv_dim)
        keep = min(int(top_k), local.size)
        ii = np.argpartition(sims, -keep)[-keep:] if keep < local.size else np.arange(local.size)
        ii = ii[np.argsort(sims[ii])[::-1]]
        return [(int(local[i]), float(sims[i])) for i in ii]



@dataclass(frozen=True, slots=True)
class HeadClause:
    vector: object
    weight: float = 1.0
    min_similarity: float | None = None
    route_required: bool = False


@dataclass(frozen=True, slots=True)
class QueryPlan:
    heads: Mapping[str, HeadClause]
    top_k: int = 10
    probe_radius: int = 1
    rerank_candidates: int = 128
    fusion_candidates: int = 1024
    vote_boost: float = 0.02
    agreement_bonus: float = 0.03

@dataclass(frozen=True, slots=True)
class MultiHeadStats:
    current_records: int
    queried_heads: tuple[str, ...]
    routed_by_head: Mapping[str, int]
    routed_union: int
    eligible_candidates: int
    exact_candidates: int
    exact_fraction: float
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class MultiHeadHit:
    slot: int
    score: float
    head_scores: Mapping[str, float]
    record: ExperienceRecord


@dataclass(frozen=True, slots=True)
class MultiHeadRecall:
    hits: tuple[MultiHeadHit, ...]
    stats: MultiHeadStats


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    relation: str
    weight: float
    record: ExperienceRecord


@dataclass(frozen=True, slots=True)
class EvidenceFrame:
    anchor: MultiHeadHit
    episode: tuple[ExperienceRecord, ...]
    linked: tuple[EvidenceLink, ...]
    stats: MultiHeadStats

    def as_dict(self) -> dict:
        return {
            "anchor": {
                "slot": self.anchor.slot,
                "score": self.anchor.score,
                "head_scores": dict(self.anchor.head_scores),
                "episode_id": self.anchor.record.episode_id,
                "source": self.anchor.record.source,
                "action": self.anchor.record.action,
                "outcome": self.anchor.record.outcome,
                "outcome_score": self.anchor.record.outcome_score,
            },
            "episode": [
                {"slot": r.slot, "record_type": r.record_type, "source": r.source,
                 "action": r.action, "outcome": r.outcome, "outcome_score": r.outcome_score}
                for r in self.episode
            ],
            "linked": [
                {"relation": x.relation, "weight": x.weight, "slot": x.record.slot,
                 "source": x.record.source, "action": x.record.action,
                 "outcome": x.record.outcome, "outcome_score": x.record.outcome_score}
                for x in self.linked
            ],
            "retrieval": {
                "queried_heads": self.stats.queried_heads,
                "routed_by_head": dict(self.stats.routed_by_head),
                "routed_union": self.stats.routed_union,
                "eligible_candidates": self.stats.eligible_candidates,
                "exact_candidates": self.stats.exact_candidates,
                "exact_fraction": self.stats.exact_fraction,
                "elapsed_seconds": self.stats.elapsed_seconds,
            },
        }


class MultiHeadMemory:
    """Persistent multi-head semantic memory.

    SQLite is the sole authoritative experience/relationship store. Each configured
    semantic head uses standard segmented .npy packed-vector slabs. One disposable
    HDCIndex is built per head. Retrieval fuses routing/sketch signals first, then
    performs exact full-HV verification on one shared shortlist.
    """

    def __init__(self, root: str | os.PathLike[str], *, heads: Iterable[str] = ("state", "goal", "action", "outcome", "entity", "sequence"),
                 hv_dim: int = 10_000, space_id: str = "default", segment_size: int = 8192,
                 auto_index: bool = True, index_options: Mapping[str, int] | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.heads = tuple(str(h) for h in heads)
        self.hv_dim = int(hv_dim)
        self.space_id = str(space_id)
        self.index_options = dict(index_options or {})
        self.db = ExperienceStore(self.root / "memory.sqlite", hv_dim=self.hv_dim, heads=self.heads, space_id=self.space_id)
        self.vector_stores = {
            h: SegmentedNpyVectorStore(self.root / "vectors" / h, hv_dim=self.hv_dim,
                                       segment_size=segment_size, committed_count=self.db.committed_count)
            for h in self.heads
        }
        self.index_dir = self.root / "indices"; self.index_dir.mkdir(exist_ok=True)
        self.indices: dict[str, HDCIndex] = {}
        self._head_slots_cache: dict[str, np.ndarray] = {}
        for h in self.heads:
            p = self._index_path(h)
            if p.exists():
                self.indices[h] = HDCIndex.load(p)
        if auto_index and self.db.committed_count:
            for h in self.heads:
                if h not in self.indices and self.db.head_slots(h).size:
                    self.rebuild_index(h)

    def _index_path(self, head: str) -> Path:
        return self.index_dir / f"{head}.npz"

    def _head_slots(self, head: str) -> np.ndarray:
        arr = self._head_slots_cache.get(head)
        if arr is None:
            arr = self.db.head_slots(head)
            self._head_slots_cache[head] = arr
        return arr

    def _invalidate_head_slots(self):
        self._head_slots_cache.clear()

    def remember(self, heads: Mapping[str, object], source: str, *, timestamp_ns: int | None = None,
                 conversation_id: int = 0, episode_id: int = 0, role: str = "", record_type: str = "experience",
                 namespace: str = "", importance: float = 0.0, tags: Iterable[str] = (), action: str = "",
                 outcome: str = "", outcome_score: float = 0.0, extra: Mapping[str, object] | None = None,
                 tenant_id: str = "", actor_user_id: str = "", actor_role: str = "",
                 authority_level: int = -1, abstraction_level: int = -1, memory_scope: str = "global",
                 perspective_version: int = 0,
                 relations: Iterable[Relation] = (), durable: bool = False) -> int:
        if not heads:
            raise ValueError("at least one semantic head is required")
        unknown = set(heads) - set(self.heads)
        if unknown:
            raise ValueError(f"unknown semantic heads: {sorted(unknown)}")
        if durable:
            self.db.set_synchronous("FULL")
        try:
            slot = self.db.begin_write()
            try:
                for name, vector in heads.items():
                    self.vector_stores[name].write_slot(slot, vector, durable=durable)
            except Exception:
                self.db.rollback_write(); raise
            self.db.commit_memory(slot, source, head_names=heads.keys(), timestamp_ns=timestamp_ns,
                                  conversation_id=conversation_id, episode_id=episode_id, role=role,
                                  record_type=record_type, namespace=namespace, importance=importance, tags=tags,
                                  action=action, outcome=outcome, outcome_score=outcome_score, extra=extra,
                                  tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                                  authority_level=authority_level, abstraction_level=abstraction_level,
                                  memory_scope=memory_scope, perspective_version=perspective_version,
                                  relations=relations)
            for store in self.vector_stores.values():
                store.set_committed_count(self.db.committed_count)
            self._invalidate_head_slots()
            return slot
        finally:
            if durable:
                self.db.set_synchronous("NORMAL")

    def rebuild_index(self, head: str | None = None) -> None:
        names = (head,) if head else self.heads
        for name in names:
            if name not in self.vector_stores:
                raise ValueError(f"unknown head {name}")
            slots = self.db.head_slots(name)
            self._head_slots_cache[name] = slots
            if slots.size == 0:
                self.indices.pop(name, None)
                try: self._index_path(name).unlink()
                except FileNotFoundError: pass
                continue
            base = self.vector_stores[name]
            base.set_committed_count(self.db.committed_count)
            idx = HDCIndex.build(SubsetVectorProvider(base, slots), **self.index_options)
            idx.save(self._index_path(name))
            self.indices[name] = idx

    def should_rebuild_index(self, head: str, *, tail_fraction: float = 0.01, tail_records: int = 50_000) -> bool:
        slots = self._head_slots(head)
        idx = self.indices.get(head)
        if idx is None:
            return bool(slots.size)
        tail = max(0, slots.size - idx.source_count)
        return tail >= tail_records or (slots.size and tail / slots.size >= tail_fraction)

    def _route_head(self, head: str, query, *, probe_radius: int, vote_boost: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        if head not in self.indices:
            self.rebuild_index(head)
        idx = self.indices.get(head)
        current_globals = self._head_slots(head)
        if idx is None or current_globals.size == 0:
            return (np.empty(0, np.intp), np.empty(0, np.float32), np.empty(0, np.uint16), np.empty(0, np.intp))
        if current_globals.size < idx.source_count:
            raise ValueError(f"head {head} provider older than index")
        local, votes = idx.candidate_votes(query, probe_radius=probe_radius)
        global_slots = current_globals[local.astype(np.intp)] if local.size else np.empty(0, np.intp)
        sims = idx.sketch_similarity(query, local.astype(np.intp)) if local.size else np.empty(0, np.float32)
        if vote_boost and local.size:
            sims = sims + np.float32(vote_boost) * votes.astype(np.float32) / float(idx.table_count)
        tail_local = np.arange(idx.source_count, current_globals.size, dtype=np.intp)
        tail_globals = current_globals[tail_local] if tail_local.size else np.empty(0, np.intp)
        return global_slots, sims, votes, tail_globals

    def recall(self, query_heads: Mapping[str, object], *, weights: Mapping[str, float] | None = None,
               top_k: int = 10, memory_filter: MemoryFilter | None = None, probe_radius: int = 1,
               rerank_candidates: int = 128, fusion_candidates: int = 1024, vote_boost: float = 0.02,
               agreement_bonus: float = 0.03, min_similarity: Mapping[str, float] | None = None,
               required_route_heads: Iterable[str] = ()) -> MultiHeadRecall:
        if not query_heads:
            return MultiHeadRecall((), MultiHeadStats(self.db.committed_count, (), {}, 0, 0, 0, 0.0, 0.0))
        unknown = set(query_heads) - set(self.heads)
        if unknown:
            raise ValueError(f"unknown query heads: {sorted(unknown)}")
        w = {h: float((weights or {}).get(h, 1.0)) for h in query_heads}
        if any(x <= 0 for x in w.values()):
            raise ValueError("head weights must be positive")
        total_w = sum(w.values())
        t0 = time.perf_counter()
        routed_by_head: dict[str, int] = {}
        query_order = {h: i for i, h in enumerate(query_heads)}
        required_route_heads = tuple(required_route_heads)
        unknown_required = set(required_route_heads) - set(query_heads)
        if unknown_required:
            raise ValueError(f"required route heads are not queried: {sorted(unknown_required)}")

        routed_payloads: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        all_parts: list[np.ndarray] = []
        tail_parts: list[np.ndarray] = []
        for head, query in query_heads.items():
            globals_, sketch, _votes, tail_globals = self._route_head(head, query, probe_radius=probe_radius, vote_boost=vote_boost)
            routed_by_head[head] = int(globals_.size + tail_globals.size)
            routed_payloads[head] = (globals_, sketch, tail_globals)
            if globals_.size:
                all_parts.append(globals_)
            if tail_globals.size:
                all_parts.append(tail_globals); tail_parts.append(tail_globals)

        if not all_parts:
            stats = MultiHeadStats(self.db.committed_count, tuple(query_heads), routed_by_head, 0, 0, 0, 0.0, time.perf_counter()-t0)
            return MultiHeadRecall((), stats)

        # Vectorized candidate fusion: avoid one Python dict entry per routed record.
        slots = np.unique(np.concatenate(all_parts)).astype(np.intp, copy=False)
        routed_union = int(slots.size)
        approx_sum = np.zeros(slots.size, dtype=np.float32)
        matches = np.zeros(slots.size, dtype=np.uint8)
        head_masks = np.zeros(slots.size, dtype=np.uint64)
        for head, (globals_, sketch, tail_globals) in routed_payloads.items():
            bit = np.uint64(1 << query_order[head])
            if globals_.size:
                loc = np.searchsorted(slots, globals_)
                approx_sum[loc] += np.float32(w[head]) * sketch.astype(np.float32, copy=False)
                matches[loc] += 1
                head_masks[loc] |= bit
            if tail_globals.size:
                loc = np.searchsorted(slots, tail_globals)
                # Fresh tail has no stored sketch; keep it alive for exact verification.
                approx_sum[loc] += np.float32(w[head])
                matches[loc] += 1
                head_masks[loc] |= bit

        if required_route_heads:
            req_mask = np.uint64(0)
            for h in required_route_heads:
                req_mask |= np.uint64(1 << query_order[h])
            route_ok = (head_masks & req_mask) == req_mask
            slots = slots[route_ok]
            approx_sum = approx_sum[route_ok]
            matches = matches[route_ok]
            if slots.size == 0:
                stats = MultiHeadStats(self.db.committed_count, tuple(query_heads), routed_by_head, routed_union, 0, 0, 0.0, time.perf_counter()-t0)
                return MultiHeadRecall((), stats)

        scores = approx_sum / np.float32(total_w) + np.float32(agreement_bonus) * matches.astype(np.float32) / float(len(query_heads))
        mask = self.db.cache.mask(slots, memory_filter)
        slots, scores = slots[mask], scores[mask]
        eligible = int(slots.size)
        if slots.size == 0:
            stats = MultiHeadStats(self.db.committed_count, tuple(query_heads), routed_by_head, routed_union, 0, 0, 0.0, time.perf_counter()-t0)
            return MultiHeadRecall((), stats)

        keep_fusion = min(max(int(rerank_candidates), int(fusion_candidates)), slots.size)
        if slots.size > keep_fusion:
            ii = np.argpartition(scores, -keep_fusion)[-keep_fusion:]
            slots, scores = slots[ii], scores[ii]

        if slots.size > rerank_candidates:
            keep = int(rerank_candidates)
            ii = np.argpartition(scores, -keep)[-keep:]
            slots = slots[ii]

        if tail_parts:
            tail_arr = np.unique(np.concatenate(tail_parts)).astype(np.intp, copy=False)
            tail_arr = tail_arr[self.db.cache.mask(tail_arr, memory_filter)]
            slots = np.unique(np.concatenate((slots, tail_arr)))

        exact_sum = np.zeros(slots.size, dtype=np.float32)
        head_score_arrays: dict[str, np.ndarray] = {}
        for head, query in query_heads.items():
            present = self.db.cache.mask(slots, MemoryFilter(include_deleted=True), require_head=head)
            hs = np.zeros(slots.size, dtype=np.float32)
            if np.any(present):
                qp = pack_hv(query, self.hv_dim)
                hv = self.vector_stores[head].read_slots(slots[present])
                hs[present] = hamming_similarity(hv, qp, self.hv_dim)
            head_score_arrays[head] = hs
            exact_sum += np.float32(w[head]) * hs
        fused = exact_sum / np.float32(total_w)
        valid_exact = np.ones(slots.size, dtype=bool)
        for head, threshold in (min_similarity or {}).items():
            if head not in head_score_arrays:
                raise ValueError(f"similarity constraint provided for unqueried head {head}")
            valid_exact &= head_score_arrays[head] >= float(threshold)
        valid_idx = np.flatnonzero(valid_exact)
        if valid_idx.size == 0:
            elapsed = time.perf_counter() - t0
            stats = MultiHeadStats(self.db.committed_count, tuple(query_heads), routed_by_head, routed_union, eligible,
                                   int(slots.size), slots.size/self.db.committed_count if self.db.committed_count else 0.0, elapsed)
            return MultiHeadRecall((), stats)
        keep = min(int(top_k), valid_idx.size)
        if keep < valid_idx.size:
            rel = np.argpartition(fused[valid_idx], -keep)[-keep:]
            ii = valid_idx[rel]
        else:
            ii = valid_idx
        ii = ii[np.argsort(fused[ii])[::-1]]
        chosen = slots[ii]
        records = {r.slot: r for r in self.db.get_many(int(x) for x in chosen)}
        hits = []
        for j in ii:
            slot = int(slots[j]); rec = records.get(slot)
            if rec is None or rec.deleted:
                continue
            hs = {h: float(arr[j]) for h, arr in head_score_arrays.items()}
            hits.append(MultiHeadHit(slot=slot, score=float(fused[j]), head_scores=hs, record=rec))
        elapsed = time.perf_counter() - t0
        stats = MultiHeadStats(self.db.committed_count, tuple(query_heads), routed_by_head, routed_union, eligible,
                               int(slots.size), slots.size/self.db.committed_count if self.db.committed_count else 0.0, elapsed)
        return MultiHeadRecall(tuple(hits), stats)

    def recall_adaptive(self, query_heads: Mapping[str, object], *, start_radius: int = 1, max_radius: int = 2,
                        min_hits: int = 1, accept_score: float | None = None, **kwargs) -> MultiHeadRecall:
        """Increase probe radius only when the cheaper search lacks sufficient evidence."""
        if start_radius < 0 or max_radius < start_radius:
            raise ValueError("invalid adaptive probe radii")
        last: MultiHeadRecall | None = None
        for radius in range(int(start_radius), int(max_radius) + 1):
            last = self.recall(query_heads, probe_radius=radius, **kwargs)
            enough = len(last.hits) >= int(min_hits)
            if enough and (accept_score is None or last.hits[0].score >= float(accept_score)):
                return last
        assert last is not None
        return last

    def recall_plan(self, plan: QueryPlan, *, memory_filter: MemoryFilter | None = None) -> MultiHeadRecall:
        query_heads = {h: c.vector for h, c in plan.heads.items()}
        weights = {h: float(c.weight) for h, c in plan.heads.items()}
        mins = {h: float(c.min_similarity) for h, c in plan.heads.items() if c.min_similarity is not None}
        required = tuple(h for h, c in plan.heads.items() if c.route_required)
        return self.recall(query_heads, weights=weights, top_k=plan.top_k, memory_filter=memory_filter,
                           probe_radius=plan.probe_radius, rerank_candidates=plan.rerank_candidates,
                           fusion_candidates=plan.fusion_candidates, vote_boost=plan.vote_boost,
                           agreement_bonus=plan.agreement_bonus, min_similarity=mins,
                           required_route_heads=required)

    def frame(self, result: MultiHeadRecall) -> EvidenceFrame | None:
        if not result.hits:
            return None
        anchor = result.hits[0]
        episode = tuple(self.db.episode(anchor.record.episode_id, conversation_id=anchor.record.conversation_id)) if anchor.record.episode_id else (anchor.record,)
        linked = tuple(EvidenceLink(rel, weight, rec) for rel, rec, weight in self.db.outgoing(anchor.slot))
        return EvidenceFrame(anchor, episode, linked, result.stats)

    def recall_frame(self, query_heads: Mapping[str, object], **kwargs) -> EvidenceFrame | None:
        return self.frame(self.recall(query_heads, **kwargs))

    def sync(self):
        for v in self.vector_stores.values():
            v.sync()
        self.db.sync()

    def close(self):
        for v in self.vector_stores.values():
            v.close()
        self.db.close()

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): self.close()
