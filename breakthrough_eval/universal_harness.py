"""Universal same-task/same-model memory-system experiment harness.

The harness owns experimental invariants and event logging. Memory adapters own only context
construction. A model runner owns only downstream inference. This keeps retrieval, governance,
and generation measurements separable.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
SCHEMA_VERSION = 1


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    text: str
    timestamp: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)
    dense_score: float | None = None
    retrieval_score: float | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "text": self.text,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
            "dense_score": self.dense_score,
            "retrieval_score": self.retrieval_score,
        }


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    case_id: str
    evidence_class: str
    task: Mapping[str, object]
    model_id: str
    model_digest: str
    prompt_template: str
    state: Mapping[str, object] = field(default_factory=dict)
    tools: tuple[str, ...] = ()
    data_revision: str = ""
    seed: int = 0
    fixed_candidates: bool = False
    token_budget: int | None = None

    def invariant_payload(self) -> dict[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "case_id": self.case_id,
            "task": dict(self.task),
            "model_id": self.model_id,
            "model_digest": self.model_digest,
            "prompt_template": self.prompt_template,
            "state": dict(self.state),
            "tools": list(self.tools),
            "data_revision": self.data_revision,
            "seed": self.seed,
            "fixed_candidates": self.fixed_candidates,
            "token_budget": self.token_budget,
        }


@dataclass(frozen=True)
class PreparedMemory:
    system: str
    context: str
    selected_ids: tuple[str, ...]
    excluded: tuple[Mapping[str, object], ...] = ()
    diagnostics: Mapping[str, object] = field(default_factory=dict)
    preparation_ms: float = 0.0


class MemoryAdapter(Protocol):
    name: str

    def prepare(
        self,
        spec: ExperimentSpec,
        candidates: tuple[Candidate, ...],
    ) -> PreparedMemory:
        ...


class NoneAdapter:
    name = "none"

    def prepare(self, spec: ExperimentSpec, candidates: tuple[Candidate, ...]) -> PreparedMemory:
        return PreparedMemory(self.name, "", ())


class FullContextAdapter:
    name = "full_context"

    def prepare(self, spec: ExperimentSpec, candidates: tuple[Candidate, ...]) -> PreparedMemory:
        started = time.perf_counter()
        context = canonical_json({"memories": [item.as_dict() for item in candidates]})
        return PreparedMemory(
            self.name,
            context,
            tuple(item.candidate_id for item in candidates),
            preparation_ms=(time.perf_counter() - started) * 1000,
        )


class RecentContextAdapter:
    name = "recent_context"

    def __init__(self, limit: int = 8):
        self.limit = int(limit)

    def prepare(self, spec: ExperimentSpec, candidates: tuple[Candidate, ...]) -> PreparedMemory:
        started = time.perf_counter()
        ordered = sorted(candidates, key=lambda item: (item.timestamp, item.candidate_id))
        selected = tuple(ordered[-self.limit :])
        context = canonical_json({"memories": [item.as_dict() for item in selected]})
        return PreparedMemory(
            self.name,
            context,
            tuple(item.candidate_id for item in selected),
            preparation_ms=(time.perf_counter() - started) * 1000,
        )


class SummaryMemoryAdapter:
    name = "summary_memory"

    def __init__(self, summarizer: Callable[[ExperimentSpec, tuple[Candidate, ...]], str]):
        self.summarizer = summarizer

    def prepare(self, spec: ExperimentSpec, candidates: tuple[Candidate, ...]) -> PreparedMemory:
        started = time.perf_counter()
        context = self.summarizer(spec, candidates)
        return PreparedMemory(
            self.name,
            context,
            tuple(item.candidate_id for item in candidates),
            diagnostics={"summary_sha256": sha256(context)},
            preparation_ms=(time.perf_counter() - started) * 1000,
        )


def terms(text: str) -> list[str]:
    return [value.lower() for value in TOKEN_RE.findall(text)]


def bm25_scores(query: str, candidates: Sequence[Candidate], *, k1: float = 1.2, b: float = 0.75) -> list[float]:
    documents = [terms(item.text) for item in candidates]
    query_terms = terms(query)
    if not documents:
        return []
    average_length = sum(map(len, documents)) / len(documents) or 1.0
    document_frequency = {
        term: sum(term in document for document in documents)
        for term in set(query_terms)
    }
    scores: list[float] = []
    for document in documents:
        score = 0.0
        for term in query_terms:
            frequency = document.count(term)
            if not frequency:
                continue
            df = document_frequency[term]
            inverse = math.log(1.0 + (len(documents) - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (1.0 - b + b * len(document) / average_length)
            score += inverse * frequency * (k1 + 1.0) / denominator
        scores.append(score)
    return scores


class BM25Adapter:
    name = "bm25"

    def __init__(self, top_k: int = 12):
        self.top_k = int(top_k)

    def prepare(self, spec: ExperimentSpec, candidates: tuple[Candidate, ...]) -> PreparedMemory:
        started = time.perf_counter()
        query = canonical_json(spec.task)
        scores = bm25_scores(query, candidates)
        ranked = sorted(
            zip(candidates, scores),
            key=lambda pair: (-pair[1], pair[0].candidate_id),
        )[: self.top_k]
        context = canonical_json({
            "memories": [
                {**item.as_dict(), "bm25_score": score}
                for item, score in ranked
            ]
        })
        return PreparedMemory(
            self.name,
            context,
            tuple(item.candidate_id for item, _ in ranked),
            diagnostics={"retrieval": "bm25", "top_k": self.top_k},
            preparation_ms=(time.perf_counter() - started) * 1000,
        )


class DenseAdapter:
    name = "dense_rag"

    def __init__(self, top_k: int = 12):
        self.top_k = int(top_k)

    def prepare(self, spec: ExperimentSpec, candidates: tuple[Candidate, ...]) -> PreparedMemory:
        started = time.perf_counter()
        if any(item.dense_score is None for item in candidates):
            raise ValueError("dense_rag requires a frozen dense_score for every candidate")
        ranked = sorted(
            candidates,
            key=lambda item: (-float(item.dense_score), item.candidate_id),
        )[: self.top_k]
        return PreparedMemory(
            self.name,
            canonical_json({"memories": [item.as_dict() for item in ranked]}),
            tuple(item.candidate_id for item in ranked),
            diagnostics={"retrieval": "frozen_dense_scores", "top_k": self.top_k},
            preparation_ms=(time.perf_counter() - started) * 1000,
        )


class HybridAdapter:
    name = "hybrid_rag"

    def __init__(self, top_k: int = 12, rrf_k: int = 60):
        self.top_k = int(top_k)
        self.rrf_k = int(rrf_k)

    def prepare(self, spec: ExperimentSpec, candidates: tuple[Candidate, ...]) -> PreparedMemory:
        started = time.perf_counter()
        if any(item.dense_score is None for item in candidates):
            raise ValueError("hybrid_rag requires a frozen dense_score for every candidate")
        lexical_scores = bm25_scores(canonical_json(spec.task), candidates)
        lexical = sorted(
            zip(candidates, lexical_scores),
            key=lambda pair: (-pair[1], pair[0].candidate_id),
        )
        dense = sorted(candidates, key=lambda item: (-float(item.dense_score), item.candidate_id))
        score: dict[str, float] = {}
        for rank, (item, _) in enumerate(lexical, 1):
            score[item.candidate_id] = score.get(item.candidate_id, 0.0) + 1.0 / (self.rrf_k + rank)
        for rank, item in enumerate(dense, 1):
            score[item.candidate_id] = score.get(item.candidate_id, 0.0) + 1.0 / (self.rrf_k + rank)
        by_id = {item.candidate_id: item for item in candidates}
        selected_ids = sorted(score, key=lambda item_id: (-score[item_id], item_id))[: self.top_k]
        selected = [by_id[item_id] for item_id in selected_ids]
        context = canonical_json({
            "memories": [
                {**item.as_dict(), "rrf_score": score[item.candidate_id]}
                for item in selected
            ]
        })
        return PreparedMemory(
            self.name,
            context,
            tuple(selected_ids),
            diagnostics={"retrieval": "bm25_dense_rrf", "top_k": self.top_k, "rrf_k": self.rrf_k},
            preparation_ms=(time.perf_counter() - started) * 1000,
        )


class StructuredStateAdapter:
    name = "structured_state"

    def prepare(self, spec: ExperimentSpec, candidates: tuple[Candidate, ...]) -> PreparedMemory:
        started = time.perf_counter()
        return PreparedMemory(
            self.name,
            canonical_json({"current_state": dict(spec.state)}),
            (),
            preparation_ms=(time.perf_counter() - started) * 1000,
        )


class StructuredEpisodicAdapter:
    name = "structured_episodic_memory"

    def prepare(self, spec: ExperimentSpec, candidates: tuple[Candidate, ...]) -> PreparedMemory:
        started = time.perf_counter()
        context = canonical_json({
            "current_state": dict(spec.state),
            "episodes": [item.as_dict() for item in candidates],
        })
        return PreparedMemory(
            self.name,
            context,
            tuple(item.candidate_id for item in candidates),
            preparation_ms=(time.perf_counter() - started) * 1000,
        )


class CallbackAdapter:
    """Adapter for StrongStructuredBaseline, HNG, ablations, or runnable external systems."""

    def __init__(
        self,
        name: str,
        callback: Callable[[ExperimentSpec, tuple[Candidate, ...]], PreparedMemory],
    ):
        self.name = name
        self.callback = callback

    def prepare(self, spec: ExperimentSpec, candidates: tuple[Candidate, ...]) -> PreparedMemory:
        prepared = self.callback(spec, candidates)
        if prepared.system != self.name:
            raise ValueError(f"callback returned system {prepared.system!r}, expected {self.name!r}")
        return prepared


@dataclass(frozen=True)
class ModelResult:
    output: object
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float = 0.0
    raw: Mapping[str, object] = field(default_factory=dict)


class UniversalHarness:
    def __init__(
        self,
        event_log: Path,
        model_runner: Callable[[ExperimentSpec, str], ModelResult],
    ):
        self.event_log = event_log
        self.model_runner = model_runner

    @staticmethod
    def render_prompt(spec: ExperimentSpec, memory_context: str) -> str:
        if "{task}" not in spec.prompt_template or "{memory_context}" not in spec.prompt_template:
            raise ValueError("prompt_template must contain {task} and {memory_context}")
        return spec.prompt_template.format(
            task=canonical_json(spec.task),
            memory_context=memory_context,
        )

    def run_case(
        self,
        spec: ExperimentSpec,
        candidates: Sequence[Candidate],
        adapters: Sequence[MemoryAdapter],
    ) -> tuple[dict[str, object], ...]:
        pool = tuple(candidates)
        candidate_payload = [item.as_dict() for item in pool]
        pool_hash = sha256(candidate_payload)
        invariant_hash = sha256(spec.invariant_payload())
        events: list[dict[str, object]] = []
        for adapter in adapters:
            prepared = adapter.prepare(spec, pool)
            prompt = self.render_prompt(spec, prepared.context)
            if spec.token_budget is not None and len(prompt) > spec.token_budget * 4:
                raise ValueError(
                    f"{adapter.name} exceeds approximate token budget: {len(prompt)} chars"
                )
            result = self.model_runner(spec, prompt)
            event = {
                "schema_version": SCHEMA_VERSION,
                "event_type": "universal_memory_experiment",
                "experiment_id": spec.experiment_id,
                "case_id": spec.case_id,
                "system": adapter.name,
                "evidence_class": spec.evidence_class,
                "invariant_sha256": invariant_hash,
                "candidate_pool_sha256": pool_hash,
                "candidate_ids": [item.candidate_id for item in pool],
                "fixed_candidates": spec.fixed_candidates,
                "model_id": spec.model_id,
                "model_digest": spec.model_digest,
                "prompt_template_sha256": sha256(spec.prompt_template),
                "prompt_sha256": sha256(prompt),
                "memory_context_sha256": sha256(prepared.context),
                "selected_ids": list(prepared.selected_ids),
                "excluded": [dict(item) for item in prepared.excluded],
                "preparation_ms": prepared.preparation_ms,
                "diagnostics": dict(prepared.diagnostics),
                "output": result.output,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "model_latency_ms": result.latency_ms,
                "raw": dict(result.raw),
            }
            self.event_log.parent.mkdir(parents=True, exist_ok=True)
            with self.event_log.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
            events.append(event)
        if spec.fixed_candidates:
            assert len({event["candidate_pool_sha256"] for event in events}) == 1
            assert len({event["invariant_sha256"] for event in events}) == 1
            assert len({event["model_digest"] for event in events}) == 1
            assert len({event["prompt_template_sha256"] for event in events}) == 1
        return tuple(events)
