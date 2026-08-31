from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, Mapping, Protocol

import numpy as np


class SemanticAdapter(Protocol):
    def encode(self, value) -> Mapping[str, np.ndarray]: ...


@dataclass(slots=True)
class CallableAdapter:
    """Wrap any external model/interpreter encoder as a Frontier semantic adapter."""
    fn: Callable[[object], Mapping[str, np.ndarray]]
    def encode(self, value) -> Mapping[str, np.ndarray]:
        return self.fn(value)


class DenseToHDCAdapter:
    """Compatibility bridge from dense model representations to bipolar HDC states.

    This is intentionally an adapter, not a claim that projected dense embeddings are
    equivalent to a native HDC semantic interpreter. Each head gets an independent
    deterministic random-hyperplane projection.
    """
    def __init__(self, *, input_dim: int, hv_dim: int = 10_000, heads=("state",), seed: int = 0x484E47):
        self.input_dim = int(input_dim); self.hv_dim = int(hv_dim); self.heads = tuple(heads); self.seed = int(seed)
        if self.input_dim <= 0 or self.hv_dim <= 0:
            raise ValueError("dimensions must be positive")
        self._proj: dict[str, np.ndarray] = {}

    def _matrix(self, head: str) -> np.ndarray:
        if head not in self._proj:
            digest = hashlib.blake2b(head.encode("utf-8"), digest_size=8).digest()
            hseed = (self.seed ^ int.from_bytes(digest, "little")) & 0xFFFFFFFFFFFFFFFF
            rng = np.random.default_rng(hseed)
            self._proj[head] = rng.choice(np.array([-1, 1], dtype=np.int8), size=(self.input_dim, self.hv_dim))
        return self._proj[head]

    def project(self, dense, *, head: str = "state") -> np.ndarray:
        x = np.asarray(dense, dtype=np.float32)
        if x.shape != (self.input_dim,):
            raise ValueError(f"expected dense vector ({self.input_dim},), got {x.shape}")
        if head not in self.heads:
            raise ValueError(f"unknown head {head}")
        y = x @ self._matrix(head)
        return np.where(y >= 0, 1, -1).astype(np.int8)

    def encode(self, value) -> Mapping[str, np.ndarray]:
        if isinstance(value, Mapping):
            return {h: self.project(v, head=h) for h, v in value.items()}
        if len(self.heads) != 1:
            raise ValueError("mapping of head->dense vector required for multi-head adapter")
        return {self.heads[0]: self.project(value, head=self.heads[0])}
