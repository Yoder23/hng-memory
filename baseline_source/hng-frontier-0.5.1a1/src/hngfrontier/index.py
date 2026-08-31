from __future__ import annotations

import itertools
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from .vectors import POPCOUNT8, VectorProvider, pack_hv


def _keys_for_vectors(packed_vectors: np.ndarray, positions: np.ndarray) -> np.ndarray:
    n = packed_vectors.shape[0]
    keys = np.zeros(n, dtype=np.uint32)
    for out_bit, pos in enumerate(positions):
        p = int(pos)
        sampled = (packed_vectors[:, p >> 3] >> (p & 7)) & 1
        keys |= sampled.astype(np.uint32) << out_bit
    return keys


def _key_for_query(query_packed: np.ndarray, positions: np.ndarray) -> int:
    key = 0
    for out_bit, pos in enumerate(positions):
        p = int(pos)
        key |= (((int(query_packed[p >> 3]) >> (p & 7)) & 1) << out_bit)
    return key


def _probe_keys(key: int, bits: int, radius: int) -> Iterable[int]:
    yield key
    for distance in range(1, radius + 1):
        for combo in itertools.combinations(range(bits), distance):
            mask = 0
            for bit in combo:
                mask |= 1 << bit
            yield key ^ mask


def _extract_sketches(packed_vectors: np.ndarray, positions: np.ndarray) -> np.ndarray:
    n = packed_vectors.shape[0]
    out = np.zeros((n, (positions.size + 7)//8), dtype=np.uint8)
    for out_bit, pos in enumerate(positions):
        p = int(pos)
        sampled = (packed_vectors[:, p >> 3] >> (p & 7)) & 1
        out[:, out_bit >> 3] |= sampled.astype(np.uint8) << (out_bit & 7)
    return out


def _extract_query_sketch(query_packed: np.ndarray, positions: np.ndarray) -> np.ndarray:
    out = np.zeros((positions.size + 7)//8, dtype=np.uint8)
    for out_bit, pos in enumerate(positions):
        p = int(pos)
        bit = (int(query_packed[p >> 3]) >> (p & 7)) & 1
        out[out_bit >> 3] |= np.uint8(bit << (out_bit & 7))
    return out


@dataclass(frozen=True, slots=True)
class IndexStats:
    indexed_records: int
    current_records: int
    routed_candidates: int
    eligible_candidates: int
    exact_candidates: int
    tail_candidates: int
    routed_fraction: float
    exact_fraction: float
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class IndexResult:
    hits: list[tuple[int, float]]
    stats: IndexStats


class HDCIndex:
    """Provider-agnostic HDC associative index.

    The index is derived state. It is serialized as a standard NumPy NPZ archive;
    semantic truth remains in the VectorProvider.
    """

    VERSION = 1

    def __init__(self, *, hv_dim: int, source_count: int, table_count: int, bits_per_table: int,
                 sketch_bits: int, positions: np.ndarray, sketch_positions: np.ndarray,
                 key_offsets: np.ndarray, keys: np.ndarray, starts: np.ndarray,
                 postings: np.ndarray, sketches: np.ndarray, seed: int):
        self.hv_dim = int(hv_dim)
        self.source_count = int(source_count)
        self.table_count = int(table_count)
        self.bits_per_table = int(bits_per_table)
        self.sketch_bits = int(sketch_bits)
        self.positions = positions
        self.sketch_positions = sketch_positions
        self.key_offsets = key_offsets
        self.keys = keys
        self.starts = starts
        self.postings = postings
        self.sketches = sketches
        self.seed = int(seed)

    @classmethod
    def build(cls, provider: VectorProvider, *, table_count: int = 48, bits_per_table: int = 14,
              sketch_bits: int = 512, seed: int = 0x484E4746, sample_records: int = 8192,
              chunk_records: int = 16384) -> "HDCIndex":
        n = provider.count; dim = provider.hv_dim
        if n > np.iinfo(np.uint32).max: raise ValueError("index supports <=2^32-1 records")
        if not (1 <= bits_per_table <= min(30, dim)): raise ValueError("invalid bits_per_table")
        if not (1 <= sketch_bits <= dim): raise ValueError("invalid sketch_bits")
        rng = np.random.default_rng(seed)
        # Balanced routing positions: choose from high-entropy corpus bits.
        if n:
            sample_n = min(sample_records, n)
            sample_slots = rng.choice(n, size=sample_n, replace=False) if sample_n < n else np.arange(n)
            sample = provider.read_slots(sample_slots)
            bits = np.unpackbits(sample, axis=1, bitorder="little", count=dim)
            p = bits.mean(axis=0, dtype=np.float64)
            balance = 1.0 - np.abs(p - 0.5) * 2.0
            pool_n = min(dim, max(table_count * bits_per_table * 4, dim // 2))
            pool = np.argpartition(balance, -pool_n)[-pool_n:]
        else:
            pool = np.arange(dim)
        positions = np.empty((table_count, bits_per_table), dtype=np.uint32)
        for t in range(table_count):
            positions[t] = rng.choice(pool, size=bits_per_table, replace=False)
        sketch_positions = rng.choice(dim, size=sketch_bits, replace=False).astype(np.uint32)

        postings = np.empty((table_count, n), dtype=np.uint32)
        all_keys: list[np.ndarray] = []
        all_starts: list[np.ndarray] = []
        offsets = [0]
        keybuf = np.empty(n, dtype=np.uint32)
        for t in range(table_count):
            for start in range(0, n, chunk_records):
                end = min(n, start + chunk_records)
                keybuf[start:end] = _keys_for_vectors(provider.read_range(start, end), positions[t])
            if n:
                order = np.argsort(keybuf, kind="stable").astype(np.uint32, copy=False)
                sorted_keys = keybuf[order]
                mask = np.empty(n, dtype=bool); mask[0] = True; mask[1:] = sorted_keys[1:] != sorted_keys[:-1]
                starts = np.flatnonzero(mask).astype(np.uint32)
                unique = sorted_keys[starts].astype(np.uint32, copy=False)
                postings[t] = order
            else:
                starts = np.empty(0, dtype=np.uint32); unique = np.empty(0, dtype=np.uint32)
            all_keys.append(unique.copy()); all_starts.append(starts.copy()); offsets.append(offsets[-1] + unique.size)
        keys = np.concatenate(all_keys) if all_keys else np.empty(0, dtype=np.uint32)
        starts = np.concatenate(all_starts) if all_starts else np.empty(0, dtype=np.uint32)
        key_offsets = np.asarray(offsets, dtype=np.uint64)
        sketches = np.empty((n, (sketch_bits + 7)//8), dtype=np.uint8)
        for start in range(0, n, chunk_records):
            end = min(n, start + chunk_records)
            sketches[start:end] = _extract_sketches(provider.read_range(start, end), sketch_positions)
        return cls(hv_dim=dim, source_count=n, table_count=table_count, bits_per_table=bits_per_table,
                   sketch_bits=sketch_bits, positions=positions, sketch_positions=sketch_positions,
                   key_offsets=key_offsets, keys=keys, starts=starts, postings=postings,
                   sketches=sketches, seed=seed)

    def save(self, path: str | os.PathLike[str]) -> str:
        path = os.fspath(path); Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path,
                 version=np.asarray([self.VERSION], dtype=np.uint16),
                 hv_dim=np.asarray([self.hv_dim], dtype=np.uint32),
                 source_count=np.asarray([self.source_count], dtype=np.uint64),
                 table_count=np.asarray([self.table_count], dtype=np.uint16),
                 bits_per_table=np.asarray([self.bits_per_table], dtype=np.uint16),
                 sketch_bits=np.asarray([self.sketch_bits], dtype=np.uint16),
                 seed=np.asarray([self.seed], dtype=np.uint64),
                 positions=self.positions, sketch_positions=self.sketch_positions,
                 key_offsets=self.key_offsets, keys=self.keys, starts=self.starts,
                 postings=self.postings, sketches=self.sketches)
        return path

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "HDCIndex":
        z = np.load(path, allow_pickle=False)
        if int(z["version"][0]) != cls.VERSION: raise ValueError("unsupported index version")
        return cls(hv_dim=int(z["hv_dim"][0]), source_count=int(z["source_count"][0]),
                   table_count=int(z["table_count"][0]), bits_per_table=int(z["bits_per_table"][0]),
                   sketch_bits=int(z["sketch_bits"][0]), positions=z["positions"], sketch_positions=z["sketch_positions"],
                   key_offsets=z["key_offsets"], keys=z["keys"], starts=z["starts"], postings=z["postings"],
                   sketches=z["sketches"], seed=int(z["seed"][0]))

    def _table_arrays(self, t: int):
        a, b = int(self.key_offsets[t]), int(self.key_offsets[t+1])
        return self.keys[a:b], self.starts[a:b]

    def candidate_votes(self, query, *, probe_radius: int = 1) -> tuple[np.ndarray, np.ndarray]:
        if probe_radius < 0 or probe_radius > self.bits_per_table: raise ValueError("invalid probe radius")
        probes_per_table = sum(math.comb(self.bits_per_table, d) for d in range(probe_radius + 1))
        if probes_per_table > 4096: raise ValueError("probe expansion too large")
        if self.source_count == 0: return np.empty(0, np.uint32), np.empty(0, np.uint16)
        qp = pack_hv(query, self.hv_dim)
        chunks = []
        for t in range(self.table_count):
            qkey = _key_for_query(qp, self.positions[t])
            probes = np.fromiter(_probe_keys(qkey, self.bits_per_table, probe_radius), dtype=np.uint32, count=probes_per_table)
            keys, starts = self._table_arrays(t)
            idx = np.searchsorted(keys, probes)
            valid = idx < keys.size
            if not np.any(valid): continue
            idxv = idx[valid]; pv = probes[valid]
            match = keys[idxv] == pv
            for j in idxv[match]:
                jj = int(j); begin = int(starts[jj]); end = int(starts[jj+1]) if jj+1 < starts.size else self.source_count
                if end > begin: chunks.append(self.postings[t, begin:end])
        if not chunks: return np.empty(0, np.uint32), np.empty(0, np.uint16)
        slots, votes = np.unique(np.concatenate(chunks), return_counts=True)
        return slots.astype(np.uint32, copy=False), votes.astype(np.uint16, copy=False)

    def sketch_similarity(self, query, slots: np.ndarray) -> np.ndarray:
        """Approximate similarity over stored sketch bits for local index slots."""
        slots = np.asarray(slots, dtype=np.intp)
        if slots.size == 0:
            return np.empty(0, dtype=np.float32)
        if np.any(slots < 0) or np.any(slots >= self.source_count):
            raise IndexError("sketch slot outside indexed snapshot")
        qp = pack_hv(query, self.hv_dim)
        qs = _extract_query_sketch(qp, self.sketch_positions)
        xor = np.bitwise_xor(self.sketches[slots], qs)
        diff = np.bitwise_count(xor).sum(axis=1, dtype=np.uint16) if hasattr(np, "bitwise_count") else POPCOUNT8[xor].sum(axis=1, dtype=np.uint16)
        return 1.0 - diff.astype(np.float32) / float(self.sketch_bits)

    def _shortlist(self, qp: np.ndarray, slots: np.ndarray, votes: np.ndarray, *, limit: int, vote_boost: float) -> np.ndarray:
        if slots.size <= limit: return slots.astype(np.intp, copy=False)
        qs = _extract_query_sketch(qp, self.sketch_positions)
        xor = np.bitwise_xor(self.sketches[slots], qs)
        diff = np.bitwise_count(xor).sum(axis=1, dtype=np.uint16) if hasattr(np, "bitwise_count") else POPCOUNT8[xor].sum(axis=1, dtype=np.uint16)
        sim = 1.0 - diff.astype(np.float32) / float(self.sketch_bits)
        if vote_boost:
            sim += np.float32(vote_boost) * votes.astype(np.float32) / float(self.table_count)
        keep = min(limit, slots.size)
        ii = np.argpartition(sim, -keep)[-keep:]
        return slots[ii].astype(np.intp, copy=False)

    def search(self, provider: VectorProvider, query, *, top_k: int = 10, probe_radius: int = 1,
               rerank_candidates: int = 128, candidate_filter: Callable[[np.ndarray], np.ndarray] | None = None,
               vote_boost: float = 0.0, include_tail: bool = True) -> IndexResult:
        if provider.hv_dim != self.hv_dim: raise ValueError("provider/index dimension mismatch")
        if provider.count < self.source_count: raise ValueError("provider is older than index")
        t0 = time.perf_counter(); qp = pack_hv(query, self.hv_dim)
        slots, votes = self.candidate_votes(query, probe_radius=probe_radius)
        routed_n = int(slots.size)
        if candidate_filter is not None and slots.size:
            mask = np.asarray(candidate_filter(slots), dtype=bool)
            slots, votes = slots[mask], votes[mask]
        eligible_n = int(slots.size)
        shortlist = self._shortlist(qp, slots, votes, limit=rerank_candidates, vote_boost=vote_boost) if slots.size else np.empty(0, np.intp)
        tail = np.arange(self.source_count, provider.count, dtype=np.intp) if include_tail and provider.count > self.source_count else np.empty(0, np.intp)
        if candidate_filter is not None and tail.size:
            tail = tail[np.asarray(candidate_filter(tail), dtype=bool)]
        exact_slots = np.concatenate((shortlist, tail)) if tail.size else shortlist
        hits = provider.exact_topk(query, exact_slots, top_k)
        elapsed = time.perf_counter() - t0
        current = provider.count
        return IndexResult(hits, IndexStats(self.source_count, current, routed_n, eligible_n, int(exact_slots.size), int(tail.size),
                                            routed_n/current if current else 0.0, exact_slots.size/current if current else 0.0,
                                            elapsed))
