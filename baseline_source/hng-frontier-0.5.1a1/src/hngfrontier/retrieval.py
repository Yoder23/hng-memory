from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import math
import time
from typing import Iterable, Mapping, Protocol, runtime_checkable

import numpy as np

from .semantic import SemanticKind, SemanticValue
from .vectors import POPCOUNT8


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    evidence_id: str
    score: float
    provider: str


@runtime_checkable
class SemanticRetriever(Protocol):
    def add(self, evidence_id: str, value: SemanticValue) -> None: ...
    def search(self, value: SemanticValue, *, top_k: int = 10, allowed_ids: set[str] | None = None) -> tuple[RetrievalHit, ...]: ...
    def rebuild(self) -> None: ...
    def stats(self) -> Mapping[str, object]: ...


@runtime_checkable
class LexicalRetriever(Protocol):
    def add(self, evidence_id: str, text: str) -> None: ...
    def search(self, text: str, *, top_k: int = 10, allowed_ids: set[str] | None = None) -> tuple[RetrievalHit, ...]: ...


@runtime_checkable
class DocumentRetriever(Protocol):
    def ingest(self, document_id: str, chunks: Iterable[tuple[str, str, Mapping[str, object]]]) -> None: ...
    def search(self, query: str, *, top_k: int = 10, filters: Mapping[str, object] | None = None) -> tuple[RetrievalHit, ...]: ...


class ReferenceBinaryRetriever:
    """Dependency-free exact Hamming reference and safe fallback."""

    def __init__(self, *, name: str = "reference-hng"):
        self.name = name
        self._vectors: dict[str, SemanticValue] = {}
        self._queries = 0

    def add(self, evidence_id: str, value: SemanticValue) -> None:
        if value.kind != SemanticKind.HDC_BINARY:
            raise TypeError("binary retriever requires HDC_BINARY")
        self._vectors[str(evidence_id)] = value

    def rebuild(self) -> None:
        return None

    def search(self, value: SemanticValue, *, top_k: int = 10, allowed_ids: set[str] | None = None) -> tuple[RetrievalHit, ...]:
        self._queries += 1
        ids = self._vectors if allowed_ids is None else {key: self._vectors[key] for key in allowed_ids if key in self._vectors}
        scored = [(key, item.exact_similarity(value)) for key, item in ids.items()]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return tuple(RetrievalHit(key, score, self.name) for key, score in scored[:top_k])

    def stats(self) -> Mapping[str, object]:
        return {"provider": self.name, "vectors": len(self._vectors), "queries": self._queries, "exact": True}


class FaissBinaryRetriever:
    """FAISS candidate provider with an exact mutable tail and access-safe fallback.

    `auto` selects BinaryFlat below 50K records and BinaryIVF above it. ANN only
    proposes candidates; the control plane always performs exact original-vector checks.
    """

    def __init__(self, *, mode: str = "auto", flat_max_records: int = 50_000,
                 nlist: int | None = None, nprobe: int | None = None, hnsw_m: int = 32,
                 multihash_maps: int = 8, multihash_bits: int = 16, multihash_flips: int = 1,
                 exact_fallback: bool = True):
        try:
            import faiss  # type: ignore
        except ImportError as exc:
            raise ImportError("FAISS backend requires `pip install hng-frontier[faiss]`") from exc
        if mode not in {"auto", "faiss-flat", "faiss-ivf", "faiss-hnsw", "faiss-multihash"}:
            raise ValueError("unsupported FAISS binary mode")
        self.faiss = faiss
        self.mode = mode
        self.flat_max_records = int(flat_max_records)
        self.nlist = nlist
        self.nprobe = nprobe
        self.hnsw_m = int(hnsw_m)
        self.multihash_maps = int(multihash_maps)
        self.multihash_bits = int(multihash_bits)
        self.multihash_flips = int(multihash_flips)
        self.exact_fallback = bool(exact_fallback)
        self._vectors: dict[str, SemanticValue] = {}
        self._index = None
        self._ids: list[str] = []
        self._indexed: set[str] = set()
        self._built_mode = "unbuilt"
        self._build_ms = 0.0
        self._queries = 0

    def add(self, evidence_id: str, value: SemanticValue) -> None:
        if value.kind != SemanticKind.HDC_BINARY:
            raise TypeError("FAISS binary retriever requires HDC_BINARY")
        if self._vectors and next(iter(self._vectors.values())).dimension != value.dimension:
            raise ValueError("HDC dimensions must match within a provider")
        self._vectors[str(evidence_id)] = value

    def _matrix(self, ids: list[str]) -> np.ndarray:
        if not ids:
            return np.empty((0, 0), dtype=np.uint8)
        return np.ascontiguousarray(np.vstack([np.asarray(self._vectors[key].value, dtype=np.uint8) for key in ids]))

    def rebuild(self) -> None:
        start = time.perf_counter()
        self._ids = sorted(self._vectors)
        self._indexed = set(self._ids)
        if not self._ids:
            self._index = None
            self._built_mode = "empty"
            return
        dimension = int(self._vectors[self._ids[0]].dimension or 0)
        matrix = self._matrix(self._ids)
        mode = self.mode
        if mode == "auto":
            mode = "faiss-flat" if len(self._ids) < self.flat_max_records else "faiss-ivf"
        if mode == "faiss-flat":
            index = self.faiss.IndexBinaryFlat(dimension)
        elif mode == "faiss-hnsw":
            index = self.faiss.IndexBinaryHNSW(dimension, self.hnsw_m)
            index.hnsw.efSearch = 128
        elif mode == "faiss-multihash":
            index = self.faiss.IndexBinaryMultiHash(
                dimension, self.multihash_maps, self.multihash_bits)
            index.nflip = self.multihash_flips
        else:
            nlist = self.nlist or max(16, min(4096, int(round(math.sqrt(len(self._ids))))))
            quantizer = self.faiss.IndexBinaryFlat(dimension)
            index = self.faiss.IndexBinaryIVF(quantizer, dimension, nlist)
            sample = matrix if len(matrix) <= 200_000 else matrix[np.linspace(0, len(matrix) - 1, 200_000, dtype=np.intp)]
            index.train(sample)
            # Red-team calibration required 16-64 probes for exact top-1 across
            # 100K-1M geometries; prefer the conservative matched-recall side.
            index.nprobe = self.nprobe or min(nlist, max(32, nlist // 16))
        index.add(matrix)
        self._index = index
        self._built_mode = mode
        self._build_ms = (time.perf_counter() - start) * 1000.0

    def _exact(self, value: SemanticValue, ids: Iterable[str], *, top_k: int) -> list[RetrievalHit]:
        scored = [(key, self._vectors[key].exact_similarity(value)) for key in ids if key in self._vectors]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return [RetrievalHit(key, score, "faiss-exact-tail") for key, score in scored[:top_k]]

    def search(self, value: SemanticValue, *, top_k: int = 10, allowed_ids: set[str] | None = None) -> tuple[RetrievalHit, ...]:
        if value.kind != SemanticKind.HDC_BINARY:
            raise TypeError("FAISS binary retriever requires HDC_BINARY")
        self._queries += 1
        if self._index is None and self._vectors:
            self.rebuild()
        allowed = allowed_ids
        result: dict[str, RetrievalHit] = {}
        if self._index is not None and self._ids:
            query = np.ascontiguousarray(np.asarray(value.value, dtype=np.uint8).reshape(1, -1))
            search_k = min(len(self._ids), max(top_k * 8, 64))
            distances, positions = self._index.search(query, search_k)
            dimension = float(value.dimension or 1)
            for distance, position in zip(distances[0], positions[0]):
                if position < 0:
                    continue
                key = self._ids[int(position)]
                if allowed is None or key in allowed:
                    result[key] = RetrievalHit(key, 1.0 - float(distance) / dimension, self._built_mode)
        tail = set() if len(self._indexed) == len(self._vectors) else (
            set(self._vectors) - self._indexed if allowed is None else allowed - self._indexed)
        for hit in self._exact(value, tail, top_k=top_k):
            result[hit.evidence_id] = hit
        allowed_count = len(self._vectors) if allowed is None else len(allowed)
        if self.exact_fallback and len(result) < min(top_k, allowed_count):
            for hit in self._exact(value, self._vectors if allowed is None else allowed, top_k=top_k):
                result[hit.evidence_id] = hit
        ranked = sorted(result.values(), key=lambda hit: (-hit.score, hit.evidence_id))
        return tuple(ranked[:top_k])

    def stats(self) -> Mapping[str, object]:
        return {
            "provider": "faiss-binary", "configured_mode": self.mode, "built_mode": self._built_mode,
            "vectors": len(self._vectors), "indexed": len(self._indexed), "tail": len(self._vectors) - len(self._indexed),
            "build_ms": self._build_ms, "queries": self._queries,
        }


class DenseRetriever:
    def __init__(self):
        self._vectors: dict[str, SemanticValue] = {}

    def add(self, evidence_id: str, value: SemanticValue) -> None:
        if value.kind != SemanticKind.DENSE:
            raise TypeError("dense retriever requires DENSE values")
        self._vectors[str(evidence_id)] = value

    def rebuild(self) -> None:
        return None

    def search(self, value: SemanticValue, *, top_k: int = 10, allowed_ids: set[str] | None = None) -> tuple[RetrievalHit, ...]:
        keys = self._vectors if allowed_ids is None else {key: self._vectors[key] for key in allowed_ids if key in self._vectors}
        scored = sorted(((key, item.exact_similarity(value)) for key, item in keys.items()), key=lambda pair: (-pair[1], pair[0]))
        return tuple(RetrievalHit(key, score, "dense-exact") for key, score in scored[:top_k])

    def stats(self) -> Mapping[str, object]:
        return {"provider": "dense-exact", "vectors": len(self._vectors), "exact": True}


class BM25Retriever:
    def __init__(self, *, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = float(k1), float(b)
        self._docs: dict[str, tuple[str, ...]] = {}

    @staticmethod
    def _tokens(text: str) -> tuple[str, ...]:
        return tuple(token.strip(".,:;!?()[]{}\"'").lower() for token in str(text).split() if token.strip(".,:;!?()[]{}\"'"))

    def add(self, evidence_id: str, text: str) -> None:
        self._docs[str(evidence_id)] = self._tokens(text)

    def rebuild(self) -> None:
        return None

    def search(self, text: str, *, top_k: int = 10, allowed_ids: set[str] | None = None) -> tuple[RetrievalHit, ...]:
        ids = list(self._docs) if allowed_ids is None else [key for key in allowed_ids if key in self._docs]
        if not ids:
            return ()
        query = self._tokens(text)
        average = sum(len(self._docs[key]) for key in ids) / len(ids)
        document_frequency = Counter(token for token in set(query) for key in ids if token in set(self._docs[key]))
        scored: list[tuple[str, float]] = []
        for key in ids:
            counts = Counter(self._docs[key])
            length = len(self._docs[key])
            score = 0.0
            for token in query:
                frequency = counts[token]
                if not frequency:
                    continue
                df = document_frequency[token]
                inverse = math.log(1.0 + (len(ids) - df + 0.5) / (df + 0.5))
                score += inverse * frequency * (self.k1 + 1.0) / (frequency + self.k1 * (1.0 - self.b + self.b * length / max(1.0, average)))
            scored.append((key, score))
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return tuple(RetrievalHit(key, score, "bm25") for key, score in scored[:top_k] if score > 0.0)

    def stats(self) -> Mapping[str, object]:
        return {"provider": "bm25", "documents": len(self._docs), "k1": self.k1, "b": self.b}


class HybridRetriever:
    """Reciprocal-rank fusion across heterogeneous providers."""

    def __init__(self, providers: Mapping[str, object], *, rrf_k: int = 60):
        self.providers = dict(providers)
        self.rrf_k = int(rrf_k)

    def search(self, query: Mapping[str, object], *, top_k: int = 10,
               allowed_ids: set[str] | None = None) -> tuple[RetrievalHit, ...]:
        scores: defaultdict[str, float] = defaultdict(float)
        sources: defaultdict[str, list[str]] = defaultdict(list)
        for name, provider in self.providers.items():
            value = query.get(name)
            if value is None:
                continue
            hits = provider.search(value, top_k=max(top_k * 4, 20), allowed_ids=allowed_ids)
            for rank, hit in enumerate(hits, start=1):
                scores[hit.evidence_id] += 1.0 / (self.rrf_k + rank)
                sources[hit.evidence_id].append(hit.provider)
        ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
        return tuple(RetrievalHit(key, score, "hybrid:" + "+".join(sorted(set(sources[key])))) for key, score in ranked[:top_k])

    def rebuild(self) -> None:
        for provider in self.providers.values():
            provider.rebuild()

    def stats(self) -> Mapping[str, object]:
        return {"provider": "hybrid-rrf", "rrf_k": self.rrf_k, "children": {name: child.stats() for name, child in self.providers.items()}}


class USearchBinaryRetriever:
    """Optional USearch b1/Hamming provider with exact access-safe fallback."""

    def __init__(self, *, connectivity: int = 16, expansion_add: int = 128,
                 expansion_search: int = 128, exact_fallback: bool = True):
        try:
            from usearch.index import Index
        except ImportError as exc:
            raise ImportError("USearch backend requires the hng-frontier usearch extra") from exc
        self.Index = Index; self.connectivity = int(connectivity)
        self.expansion_add = int(expansion_add); self.expansion_search = int(expansion_search)
        self.exact_fallback = bool(exact_fallback); self._vectors: dict[str, SemanticValue] = {}
        self._ids: list[str] = []; self._indexed: set[str] = set()
        self._index = None; self._queries = 0; self._build_ms = 0.0

    def add(self, evidence_id: str, value: SemanticValue) -> None:
        if value.kind != SemanticKind.HDC_BINARY: raise TypeError("USearch binary retriever requires HDC_BINARY")
        if self._vectors and next(iter(self._vectors.values())).dimension != value.dimension:
            raise ValueError("HDC dimensions must match")
        self._vectors[str(evidence_id)] = value

    def rebuild(self) -> None:
        start=time.perf_counter(); self._ids=sorted(self._vectors); self._indexed=set(self._ids)
        if not self._ids: self._index=None; return
        dim=int(self._vectors[self._ids[0]].dimension or 0)
        index=self.Index(ndim=dim,metric="hamming",dtype="b1",connectivity=self.connectivity,
                         expansion_add=self.expansion_add,expansion_search=self.expansion_search)
        matrix=np.ascontiguousarray(np.vstack([np.asarray(self._vectors[key].value,dtype=np.uint8) for key in self._ids]))
        index.add(np.arange(len(self._ids),dtype=np.uint64),matrix); self._index=index
        self._build_ms=(time.perf_counter()-start)*1000

    def _exact(self,value:SemanticValue,ids:Iterable[str],top_k:int)->list[RetrievalHit]:
        pairs=sorted(((key,self._vectors[key].exact_similarity(value)) for key in ids if key in self._vectors),
                     key=lambda pair:(-pair[1],pair[0]))
        return [RetrievalHit(key,score,"usearch-exact-fallback") for key,score in pairs[:top_k]]

    def search(self,value:SemanticValue,*,top_k:int=10,allowed_ids:set[str]|None=None)->tuple[RetrievalHit,...]:
        if value.kind != SemanticKind.HDC_BINARY: raise TypeError("USearch binary retriever requires HDC_BINARY")
        self._queries+=1
        if self._index is None and self._vectors: self.rebuild()
        allowed=allowed_ids; result={}
        if self._index is not None:
            query=np.ascontiguousarray(np.asarray(value.value,dtype=np.uint8))
            matches=self._index.search(query,min(len(self._ids),max(64,top_k*8)))
            for key,distance in zip(np.asarray(matches.keys).reshape(-1),np.asarray(matches.distances).reshape(-1)):
                evidence_id=self._ids[int(key)]
                if allowed is None or evidence_id in allowed:
                    result[evidence_id]=RetrievalHit(evidence_id,1.0-float(distance)/float(value.dimension or 1),"usearch-hamming")
        tail = set(self._vectors)-self._indexed if allowed is None else allowed-self._indexed
        for hit in self._exact(value,tail,top_k): result[hit.evidence_id]=hit
        allowed_count=len(self._vectors) if allowed is None else len(allowed)
        if self.exact_fallback and len(result)<min(top_k,allowed_count):
            for hit in self._exact(value,self._vectors if allowed is None else allowed,top_k): result[hit.evidence_id]=hit
        return tuple(sorted(result.values(),key=lambda hit:(-hit.score,hit.evidence_id))[:top_k])

    def stats(self)->Mapping[str,object]:
        return {"provider":"usearch-hamming","vectors":len(self._vectors),"indexed":len(self._indexed),
                "tail":len(self._vectors)-len(self._indexed),"build_ms":self._build_ms,
                "queries":self._queries,"expansion_search":self.expansion_search}
