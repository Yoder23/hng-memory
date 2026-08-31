from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .multihead import EvidenceFrame, MultiHeadMemory
from .store import MemoryFilter


@dataclass(frozen=True, slots=True)
class ActionAssessment:
    decision: str
    evidence_score: float
    support_weight: float
    contradiction_weight: float
    evidence_count: int
    frames: tuple[EvidenceFrame, ...]

    def as_dict(self) -> dict:
        return {
            "decision": self.decision,
            "evidence_score": self.evidence_score,
            "support_weight": self.support_weight,
            "contradiction_weight": self.contradiction_weight,
            "evidence_count": self.evidence_count,
            "evidence": [f.as_dict() for f in self.frames],
        }



@dataclass(frozen=True, slots=True)
class RankedAction:
    label: str
    assessment: ActionAssessment


@dataclass(frozen=True, slots=True)
class ActionRecommendation:
    """Historically grounded action candidate for a semantic context.

    This is intentionally a *candidate narrowing* primitive, not a policy.  It lets an
    HDC assistant with a very large action library ask memory which actions have actual
    outcome evidence under states like the current one before doing final action routing.
    """
    label: str
    evidence_score: float
    support_weight: float
    contradiction_weight: float
    evidence_count: int
    best_similarity: float
    slots: tuple[int, ...]

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "evidence_score": self.evidence_score,
            "support_weight": self.support_weight,
            "contradiction_weight": self.contradiction_weight,
            "evidence_count": self.evidence_count,
            "best_similarity": self.best_similarity,
            "slots": list(self.slots),
        }


class MemoryHarness:
    """External evidence/control surface around a model or agent.

    The harness does not assert truth or safety by itself. It retrieves explicit prior
    evidence and can implement a policy that challenges proposed actions when similar
    historical episodes have negative outcomes.
    """
    def __init__(self, memory: MultiHeadMemory):
        self.memory = memory

    def recall(self, semantic_heads: Mapping[str, object], **kwargs) -> EvidenceFrame | None:
        return self.memory.recall_frame(semantic_heads, **kwargs)

    def assess_action(self, context_heads: Mapping[str, object], proposed_action, *,
                      action_head: str = "action", weights: Mapping[str, float] | None = None,
                      top_k: int = 12, memory_filter: MemoryFilter | None = None,
                      minimum_evidence: float = 1.5, challenge_below: float = -0.15,
                      support_above: float = 0.15, semantic_floor: float = 0.80,
                      action_floor: float | None = None, strict_route: bool = True,
                      adaptive_probe: bool = True, max_probe_radius: int = 2) -> ActionAssessment:
        q = dict(context_heads); q[action_head] = proposed_action
        effective_weights = dict(weights or {})
        effective_weights.setdefault(action_head, 3.0)
        exact_constraints = {head: float(semantic_floor) for head in q}
        exact_constraints[action_head] = float(semantic_floor if action_floor is None else action_floor)
        route_constraints = tuple(q) if strict_route else (action_head,)
        recall_kwargs = dict(weights=effective_weights, top_k=top_k, memory_filter=memory_filter,
                             min_similarity=exact_constraints, required_route_heads=route_constraints)
        if adaptive_probe:
            result = self.memory.recall_adaptive(q, start_radius=1, max_radius=max_probe_radius,
                                                 min_hits=1, **recall_kwargs)
        else:
            result = self.memory.recall(q, probe_radius=1, **recall_kwargs)
        frames: list[EvidenceFrame] = []
        support = 0.0; contradiction = 0.0; total = 0.0
        for hit in result.hits:
            frame = self.memory.frame(type(result)((hit,), result.stats))
            if frame is None:
                continue
            frames.append(frame)
            # Similarity is used as evidence strength; outcome_score is explicit experience metadata.
            strength = max(0.0, hit.score - 0.5) * 2.0
            val = float(hit.record.outcome_score)
            total += strength
            if val >= 0:
                support += strength * val
            else:
                contradiction += strength * (-val)
        denom = support + contradiction
        evidence_score = (support - contradiction) / denom if denom > 0 else 0.0
        if total < minimum_evidence:
            decision = "insufficient_evidence"
        elif evidence_score <= challenge_below:
            decision = "challenge"
        elif evidence_score >= support_above:
            decision = "support"
        else:
            decision = "conflicted"
        return ActionAssessment(decision, evidence_score, support, contradiction, len(frames), tuple(frames))


    def recommend_actions(self, context_heads: Mapping[str, object], *,
                          max_actions: int = 16, top_k_memories: int = 96,
                          memory_filter: MemoryFilter | None = None, semantic_floor: float = 0.80,
                          strict_route: bool = True, adaptive_probe: bool = True,
                          max_probe_radius: int = 2) -> tuple[ActionRecommendation, ...]:
        """Narrow a large action library using explicit historical outcome evidence.

        The query contains *context* heads only.  HNG first recalls matching historical
        transitions and aggregates their outcome evidence by the action label recorded in
        those transitions.  The caller can then map the returned labels to native HDC action
        vectors and perform any final action-library routing it wants.

        This avoids evaluating every action in a large library against memory one-by-one.
        """
        if max_actions <= 0 or top_k_memories <= 0 or not context_heads:
            return ()
        q = dict(context_heads)
        exact_constraints = {head: float(semantic_floor) for head in q}
        route_constraints = tuple(q) if strict_route else ()
        kwargs = dict(
            top_k=int(top_k_memories), memory_filter=memory_filter,
            min_similarity=exact_constraints, required_route_heads=route_constraints,
            rerank_candidates=max(128, int(top_k_memories) * 2),
            fusion_candidates=max(1024, int(top_k_memories) * 4),
        )
        if adaptive_probe:
            result = self.memory.recall_adaptive(q, start_radius=1, max_radius=max_probe_radius,
                                                 min_hits=1, **kwargs)
        else:
            result = self.memory.recall(q, probe_radius=1, **kwargs)

        agg: dict[str, dict[str, object]] = {}
        for hit in result.hits:
            label = hit.record.action.strip()
            if not label:
                continue
            # Fused exact similarity becomes the strength of this precedent; explicit
            # outcome_score supplies valence.  Neutral/unknown outcomes contribute no vote.
            strength = max(0.0, float(hit.score) - 0.5) * 2.0
            valence = float(hit.record.outcome_score)
            row = agg.setdefault(label, {
                "support": 0.0, "contradiction": 0.0, "count": 0,
                "best": 0.0, "slots": [],
            })
            row["count"] = int(row["count"]) + 1
            row["best"] = max(float(row["best"]), float(hit.score))
            cast_slots = row["slots"]
            assert isinstance(cast_slots, list)
            cast_slots.append(int(hit.slot))
            if valence > 0:
                row["support"] = float(row["support"]) + strength * valence
            elif valence < 0:
                row["contradiction"] = float(row["contradiction"]) + strength * (-valence)

        out: list[ActionRecommendation] = []
        for label, row in agg.items():
            support = float(row["support"]); contradiction = float(row["contradiction"])
            denom = support + contradiction
            evidence_score = (support - contradiction) / denom if denom > 0 else 0.0
            slots = tuple(int(x) for x in row["slots"])  # type: ignore[arg-type]
            out.append(ActionRecommendation(
                label=label, evidence_score=float(evidence_score), support_weight=support,
                contradiction_weight=contradiction, evidence_count=int(row["count"]),
                best_similarity=float(row["best"]), slots=slots,
            ))
        # Prefer positive net evidence, then confidence, then amount/quality of evidence.
        out.sort(key=lambda x: (x.support_weight - x.contradiction_weight, x.evidence_score,
                                x.best_similarity, x.evidence_count), reverse=True)
        return tuple(out[:int(max_actions)])

    def compare_actions(self, context_heads: Mapping[str, object], candidate_actions: Mapping[str, object], **kwargs) -> tuple[RankedAction, ...]:
        """Rank proposed actions by explicit historical outcome evidence."""
        ranked = [RankedAction(str(label), self.assess_action(context_heads, vector, **kwargs))
                  for label, vector in candidate_actions.items()]
        order = {"support": 3, "conflicted": 2, "insufficient_evidence": 1, "challenge": 0}
        ranked.sort(key=lambda x: (order.get(x.assessment.decision, -1), x.assessment.evidence_score,
                                   x.assessment.support_weight - x.assessment.contradiction_weight), reverse=True)
        return tuple(ranked)
