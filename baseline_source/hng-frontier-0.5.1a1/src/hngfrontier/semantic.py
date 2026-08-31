from __future__ import annotations

import base64
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

import numpy as np

from .vectors import POPCOUNT8, pack_hv


class SemanticKind(str, Enum):
    HDC_BINARY = "hdc_binary"
    DENSE = "dense"
    STRUCTURED = "structured"
    LEXICAL = "lexical"


@dataclass(frozen=True, slots=True)
class SemanticValue:
    """One named semantic value without coupling the control plane to its representation."""

    kind: SemanticKind
    value: object
    dimension: int | None = None
    model: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def hdc(cls, vector, *, dimension: int | None = None, model: str = "native-hdc") -> "SemanticValue":
        array = np.asarray(vector)
        dim = int(dimension if dimension is not None else array.size)
        return cls(SemanticKind.HDC_BINARY, pack_hv(array, dim), dim, model)

    @classmethod
    def dense(cls, vector, *, model: str = "") -> "SemanticValue":
        array = np.asarray(vector, dtype=np.float32).reshape(-1)
        return cls(SemanticKind.DENSE, array.copy(), int(array.size), model)

    @classmethod
    def structured(cls, value: object) -> "SemanticValue":
        return cls(SemanticKind.STRUCTURED, value)

    @classmethod
    def lexical(cls, text: str) -> "SemanticValue":
        return cls(SemanticKind.LEXICAL, str(text))

    def as_storage(self) -> dict[str, object]:
        if self.kind in {SemanticKind.HDC_BINARY, SemanticKind.DENSE}:
            array = np.asarray(self.value, dtype=np.uint8 if self.kind == SemanticKind.HDC_BINARY else np.float32)
            encoded: object = base64.b64encode(array.tobytes()).decode("ascii")
        else:
            encoded = self.value
        return {
            "kind": self.kind.value,
            "value": encoded,
            "dimension": self.dimension,
            "model": self.model,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_storage(cls, payload: Mapping[str, object]) -> "SemanticValue":
        kind = SemanticKind(str(payload["kind"]))
        value = payload.get("value")
        dim = None if payload.get("dimension") is None else int(payload["dimension"])
        if kind == SemanticKind.HDC_BINARY:
            value = np.frombuffer(base64.b64decode(str(value)), dtype=np.uint8).copy()
        elif kind == SemanticKind.DENSE:
            value = np.frombuffer(base64.b64decode(str(value)), dtype=np.float32).copy()
        return cls(kind, value, dim, str(payload.get("model") or ""), dict(payload.get("metadata") or {}))

    def exact_similarity(self, other: "SemanticValue") -> float:
        if self.kind != other.kind:
            return 0.0
        if self.kind == SemanticKind.HDC_BINARY:
            if self.dimension != other.dimension or self.dimension is None:
                return 0.0
            left = np.asarray(self.value, dtype=np.uint8)
            right = np.asarray(other.value, dtype=np.uint8)
            xor = np.bitwise_xor(left, right)
            differing = int(np.bitwise_count(xor).sum()) if hasattr(np, "bitwise_count") else int(POPCOUNT8[xor].sum())
            return 1.0 - differing / float(self.dimension)
        if self.kind == SemanticKind.DENSE:
            left = np.asarray(self.value, dtype=np.float32)
            right = np.asarray(other.value, dtype=np.float32)
            if left.shape != right.shape:
                return 0.0
            denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
            return 0.0 if denominator == 0.0 else float(np.dot(left, right) / denominator)
        if self.kind == SemanticKind.STRUCTURED:
            return 1.0 if self.value == other.value else 0.0
        left = set(str(self.value).lower().split())
        right = set(str(other.value).lower().split())
        return 0.0 if not left and not right else len(left & right) / max(1, len(left | right))


@dataclass(frozen=True, slots=True)
class SemanticState:
    fields: Mapping[str, SemanticValue] = field(default_factory=dict)
    revision: int = 0

    def missing(self, names: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(name for name in names if name not in self.fields)

    def merged(self, values: Mapping[str, SemanticValue], *, revision: int | None = None) -> "SemanticState":
        fields = dict(self.fields)
        fields.update(values)
        return SemanticState(fields, self.revision + 1 if revision is None else int(revision))

    def as_storage(self) -> dict[str, object]:
        return {"revision": self.revision, "fields": {name: value.as_storage() for name, value in self.fields.items()}}

    @classmethod
    def from_storage(cls, payload: Mapping[str, object] | None) -> "SemanticState":
        payload = dict(payload or {})
        fields = {name: SemanticValue.from_storage(value) for name, value in dict(payload.get("fields") or {}).items()}
        return cls(fields, int(payload.get("revision") or 0))


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    required_heads: tuple[str, ...] = ()
    optional_heads: tuple[str, ...] = ()
    min_similarity: Mapping[str, float] = field(default_factory=dict)
    strict_action_floor: float = 0.97
    require_environment_version: bool = False
    require_profile: bool = False

    def validate(self, state: SemanticState) -> tuple[str, ...]:
        missing = list(state.missing(self.required_heads))
        if self.require_environment_version and "environment_version" not in state.fields:
            missing.append("environment_version")
        return tuple(dict.fromkeys(missing))

