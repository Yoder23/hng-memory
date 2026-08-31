from __future__ import annotations

from dataclasses import dataclass
import statistics
import time
from typing import Mapping

from .assistant import AssistantMemory


@dataclass(frozen=True, slots=True)
class ContextExpectation:
    name: str
    conversation_id: int
    query_heads: Mapping[str, object]
    expected_episode_id: int
    top_k: int = 8


@dataclass(frozen=True, slots=True)
class ActionExpectation:
    name: str
    conversation_id: int
    context_heads: Mapping[str, object]
    proposed_action: object
    expected_decision: str
    kwargs: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ContinuityExpectation:
    name: str
    conversation_id: int
    expected_goal: str | None = None
    expected_open_keys: tuple[str, ...] = ()
    expected_constraint_keys: tuple[str, ...] = ()
    expected_fact_values: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class CaseResult:
    name: str
    kind: str
    passed: bool
    elapsed_seconds: float
    observed: object
    expected: object


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    results: tuple[CaseResult, ...]

    @property
    def passed(self) -> int:
        return sum(x.passed for x in self.results)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 1.0

    @property
    def median_ms(self) -> float:
        values = [x.elapsed_seconds * 1000.0 for x in self.results]
        return statistics.median(values) if values else 0.0

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total": self.total,
            "pass_rate": self.pass_rate,
            "median_ms": self.median_ms,
            "results": [
                {
                    "name": x.name,
                    "kind": x.kind,
                    "passed": x.passed,
                    "elapsed_seconds": x.elapsed_seconds,
                    "observed": x.observed,
                    "expected": x.expected,
                }
                for x in self.results
            ],
        }


class AssistantReadinessEvaluator:
    """Small, model-independent replay gate for real assistant traces.

    Feed it semantic heads produced by the real HDC interpreter. It deliberately scores
    behavior (correct episode, correct guard decision, correct deterministic continuity),
    not only ANN latency.
    """

    def __init__(self, memory: AssistantMemory):
        self.memory = memory

    def run(self, *, contexts: tuple[ContextExpectation, ...] = (),
            actions: tuple[ActionExpectation, ...] = (),
            continuity: tuple[ContinuityExpectation, ...] = ()) -> ReadinessReport:
        out: list[CaseResult] = []
        for case in continuity:
            t0 = time.perf_counter()
            state = self.memory.working_state(case.conversation_id)
            facts = {x.key: x.value for x in state.facts}
            observed = {
                "goal": state.goal,
                "open_keys": tuple(x.key for x in state.open_loops),
                "constraint_keys": tuple(x.key for x in state.constraints),
                "facts": facts,
            }
            expected = {
                "goal": case.expected_goal,
                "open_keys": case.expected_open_keys,
                "constraint_keys": case.expected_constraint_keys,
                "facts": dict(case.expected_fact_values or {}),
            }
            passed = (
                observed["goal"] == expected["goal"]
                and observed["open_keys"] == expected["open_keys"]
                and observed["constraint_keys"] == expected["constraint_keys"]
                and all(facts.get(k) == v for k, v in expected["facts"].items())
            )
            out.append(CaseResult(case.name, "continuity", passed, time.perf_counter()-t0, observed, expected))

        for case in contexts:
            t0 = time.perf_counter()
            frame = self.memory.prepare_context(case.query_heads, conversation_id=case.conversation_id, top_k=case.top_k)
            observed = tuple(x.episode_id for x in frame.recalled_episodes)
            passed = case.expected_episode_id in observed
            out.append(CaseResult(case.name, "context", passed, time.perf_counter()-t0,
                                  observed, case.expected_episode_id))

        for case in actions:
            t0 = time.perf_counter()
            result = self.memory.evaluate_action(
                case.context_heads, case.proposed_action, conversation_id=case.conversation_id,
                **dict(case.kwargs or {}),
            )
            observed = result.assessment.decision
            out.append(CaseResult(case.name, "action", observed == case.expected_decision,
                                  time.perf_counter()-t0, observed, case.expected_decision))
        return ReadinessReport(tuple(out))
