from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

POPCOUNT8 = np.array([int(i).bit_count() for i in range(256)], dtype=np.uint8)


def _fsync_path(path: str | os.PathLike[str]) -> None:
    """Flush a path using a Windows-compatible writable handle."""
    if os.name == "nt":
        with open(path, "r+b", buffering=0) as handle:
            os.fsync(handle.fileno())
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def pack_hv(vector, hv_dim: int) -> np.ndarray:
    arr = np.asarray(vector)
    if arr.ndim != 1 or arr.size != hv_dim:
        raise ValueError(f"expected ({hv_dim},), got {arr.shape}")
    if arr.dtype == np.bool_:
        bits = arr.astype(np.uint8, copy=False)
    elif np.all((arr == -1) | (arr == 1)):
        bits = (arr > 0).astype(np.uint8, copy=False)
    elif np.all((arr == 0) | (arr == 1)):
        bits = arr.astype(np.uint8, copy=False)
    else:
        raise ValueError("hypervector must be bool, {0,1}, or {-1,+1}")
    return np.packbits(bits, bitorder="little")


def unpack_hv(packed, hv_dim: int, *, bipolar: bool = True) -> np.ndarray:
    arr = np.asarray(packed, dtype=np.uint8).reshape(-1)
    bits = np.unpackbits(arr, bitorder="little", count=int(hv_dim))
    if bipolar:
        return (bits.astype(np.int8) * 2) - 1
    return bits.astype(np.uint8, copy=False)


def hamming_similarity(packed_vectors: np.ndarray, query_packed: np.ndarray, hv_dim: int) -> np.ndarray:
    xor = np.bitwise_xor(packed_vectors, query_packed)
    if hasattr(np, "bitwise_count"):
        differing = np.bitwise_count(xor).sum(axis=1, dtype=np.uint32)
    else:
        differing = POPCOUNT8[xor].sum(axis=1, dtype=np.uint32)
    return 1.0 - differing.astype(np.float32) / float(hv_dim)


@runtime_checkable
class VectorProvider(Protocol):
    hv_dim: int
    packed_bytes: int

    @property
    def count(self) -> int: ...
    def read_slots(self, slots: np.ndarray) -> np.ndarray: ...
    def read_range(self, start: int, end: int) -> np.ndarray: ...
    def exact_topk(self, query, slots: np.ndarray, top_k: int) -> list[tuple[int, float]]: ...


class SingleNpyVectorProvider:
    """Read-only provider over a standard .npy uint8 matrix [N, ceil(D/8)]."""

    def __init__(self, path: str | os.PathLike[str], *, hv_dim: int):
        self.path = os.fspath(path)
        self.hv_dim = int(hv_dim)
        self.packed_bytes = (self.hv_dim + 7) // 8
        self._mm = np.load(self.path, mmap_mode="r")
        if self._mm.ndim != 2 or self._mm.shape[1] != self.packed_bytes or self._mm.dtype != np.uint8:
            raise ValueError(".npy vector matrix has incompatible shape/dtype")

    @property
    def count(self) -> int:
        return int(self._mm.shape[0])

    def read_slots(self, slots: np.ndarray) -> np.ndarray:
        return np.asarray(self._mm[np.asarray(slots, dtype=np.intp)], dtype=np.uint8)

    def read_range(self, start: int, end: int) -> np.ndarray:
        return np.asarray(self._mm[int(start):int(end)], dtype=np.uint8)

    def exact_topk(self, query, slots: np.ndarray, top_k: int) -> list[tuple[int, float]]:
        slots = np.asarray(slots, dtype=np.intp)
        if top_k <= 0 or slots.size == 0:
            return []
        qp = pack_hv(query, self.hv_dim)
        sims = hamming_similarity(self.read_slots(slots), qp, self.hv_dim)
        keep = min(int(top_k), slots.size)
        if keep < slots.size:
            ii = np.argpartition(sims, -keep)[-keep:]
        else:
            ii = np.arange(slots.size)
        ii = ii[np.argsort(sims[ii])[::-1]]
        return [(int(slots[i]), float(sims[i])) for i in ii]

    def close(self):
        mm = getattr(self._mm, "_mmap", None)
        if mm is not None:
            mm.close()
        self._mm = None


class SegmentedNpyVectorStore:
    """Append-oriented vector store using only standard .npy segment files.

    Segment membership is arithmetic: slot // segment_size. The authoritative
    committed count belongs to the episodic SQLite store, so preallocated unused
    rows are never considered committed memories.
    """

    def __init__(self, directory: str | os.PathLike[str], *, hv_dim: int, segment_size: int = 8192, committed_count: int = 0):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.hv_dim = int(hv_dim)
        self.packed_bytes = (self.hv_dim + 7) // 8
        self.segment_size = int(segment_size)
        if self.segment_size <= 0:
            raise ValueError("segment_size must be positive")
        self._committed_count = int(committed_count)
        self._maps: dict[int, np.memmap] = {}

    def set_committed_count(self, value: int) -> None:
        self._committed_count = int(value)

    @property
    def count(self) -> int:
        return self._committed_count

    def _path(self, seg: int) -> Path:
        return self.directory / f"vectors-{seg:06d}.npy"

    def _segment(self, seg: int, *, writable: bool) -> np.memmap:
        if seg in self._maps:
            return self._maps[seg]
        path = self._path(seg)
        if not path.exists():
            if not writable:
                raise FileNotFoundError(path)
            mm = np.lib.format.open_memmap(path, mode="w+", dtype=np.uint8, shape=(self.segment_size, self.packed_bytes))
            mm[:] = 0
            mm.flush()
        else:
            mm = np.load(path, mmap_mode="r+" if writable else "r")
            if mm.shape != (self.segment_size, self.packed_bytes) or mm.dtype != np.uint8:
                raise ValueError(f"invalid vector segment {path}")
        self._maps[seg] = mm
        return mm

    def write_slot(self, slot: int, vector, *, durable: bool = False) -> None:
        slot = int(slot)
        if slot < 0:
            raise ValueError("slot must be >=0")
        seg, off = divmod(slot, self.segment_size)
        mm = self._segment(seg, writable=True)
        mm[off] = pack_hv(vector, self.hv_dim)
        if durable:
            mm.flush()
            _fsync_path(self._path(seg))

    def read_slots(self, slots: np.ndarray) -> np.ndarray:
        slots = np.asarray(slots, dtype=np.intp)
        if slots.size == 0:
            return np.empty((0, self.packed_bytes), dtype=np.uint8)
        if np.any(slots < 0) or np.any(slots >= self._committed_count):
            raise IndexError("slot outside committed prefix")
        out = np.empty((slots.size, self.packed_bytes), dtype=np.uint8)
        segs = slots // self.segment_size
        for seg in np.unique(segs):
            mask = segs == seg
            offs = slots[mask] % self.segment_size
            out[mask] = self._segment(int(seg), writable=False)[offs]
        return out

    def read_range(self, start: int, end: int) -> np.ndarray:
        start, end = int(start), int(end)
        if start < 0 or end < start or end > self._committed_count:
            raise IndexError("range outside committed prefix")
        if start == end:
            return np.empty((0, self.packed_bytes), dtype=np.uint8)
        # Fast path inside one segment.
        s0, o0 = divmod(start, self.segment_size)
        s1, o1 = divmod(end - 1, self.segment_size)
        if s0 == s1:
            return np.asarray(self._segment(s0, writable=False)[o0:o1 + 1], dtype=np.uint8)
        chunks = []
        pos = start
        while pos < end:
            seg, off = divmod(pos, self.segment_size)
            take = min(end - pos, self.segment_size - off)
            chunks.append(np.asarray(self._segment(seg, writable=False)[off:off + take], dtype=np.uint8))
            pos += take
        return np.concatenate(chunks, axis=0)

    def exact_topk(self, query, slots: np.ndarray, top_k: int) -> list[tuple[int, float]]:
        slots = np.asarray(slots, dtype=np.intp)
        if top_k <= 0 or slots.size == 0:
            return []
        qp = pack_hv(query, self.hv_dim)
        sims = hamming_similarity(self.read_slots(slots), qp, self.hv_dim)
        keep = min(int(top_k), slots.size)
        ii = np.argpartition(sims, -keep)[-keep:] if keep < slots.size else np.arange(slots.size)
        ii = ii[np.argsort(sims[ii])[::-1]]
        return [(int(slots[i]), float(sims[i])) for i in ii]

    def sync(self):
        for seg, mm in list(self._maps.items()):
            if getattr(mm, "mode", "r") != "r":
                mm.flush()
                _fsync_path(self._path(seg))

    def close(self):
        for mm in self._maps.values():
            try:
                mm.flush()
            except Exception:
                pass
            raw = getattr(mm, "_mmap", None)
            if raw is not None:
                raw.close()
        self._maps.clear()
