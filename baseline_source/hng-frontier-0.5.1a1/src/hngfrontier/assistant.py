from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from typing import Iterable, Mapping, Protocol

from .harness import ActionAssessment, ActionRecommendation, MemoryHarness
from .multihead import EvidenceFrame, MultiHeadMemory, MultiHeadRecall, MultiHeadStats
from .store import ExperienceRecord, MemoryFilter, Relation
from .perspective import (EffectivePerspective, PerspectiveOverride, PerspectivePolicy, PerspectiveProfile, PerspectiveStore)
from .working import Correction, WorkingItem, WorkingMemory, WorkingState, WorkingUpdate
from .vectors import unpack_hv


@dataclass(frozen=True, slots=True)
class AssistantContext:
    working_state: WorkingState
    semantic_heads: Mapping[str, object]
    recent_records: tuple[ExperienceRecord, ...]
    perspective: EffectivePerspective | None = None


class AssistantSemanticAdapter(Protocol):
    """Bridge owned by the assistant's semantic interpreter.

    HNG never interprets raw language here. The adapter receives deterministic working
    state plus the prior committed HDC semantic heads, allowing a native HDC interpreter
    to resolve elliptical follow-ups without reconstructing state from text.
    """
    def encode(self, value: object, *, context: AssistantContext) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class CallableAssistantAdapter:
    fn: object

    def encode(self, value: object, *, context: AssistantContext) -> Mapping[str, object]:
        return self.fn(value, context=context)  # type: ignore[misc]


@dataclass(frozen=True, slots=True)
class Provenance:
    slot: int
    episode_id: int
    score: float
    head_scores: Mapping[str, float]
    source: str

    def as_dict(self) -> dict:
        return {
            "slot": self.slot,
            "episode_id": self.episode_id,
            "score": self.score,
            "head_scores": dict(self.head_scores),
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class EpisodeMemory:
    episode_id: int
    anchor_slot: int
    score: float
    records: tuple[ExperienceRecord, ...]

    def as_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "anchor_slot": self.anchor_slot,
            "score": self.score,
            "records": [_record_dict(x) for x in self.records],
        }


@dataclass(frozen=True, slots=True)
class MemoryFrame:
    """Frozen assistant-facing memory contract.

    This is the integration boundary. Retrieval/index/storage internals may evolve without
    changing what the assistant receives.
    """
    schema_version: int
    mode: str
    conversation_id: int
    generated_ns: int
    working_state: WorkingState
    perspective: EffectivePerspective | None
    immediate_context: tuple[ExperienceRecord, ...]
    recalled_episodes: tuple[EpisodeMemory, ...]
    supporting_evidence: tuple[ExperienceRecord, ...]
    contradicting_evidence: tuple[ExperienceRecord, ...]
    prior_actions: tuple[str, ...]
    prior_outcomes: tuple[str, ...]
    open_loops: tuple[WorkingItem, ...]
    commitments: tuple[WorkingItem, ...]
    constraints: tuple[WorkingItem, ...]
    corrections: tuple[Correction, ...]
    provenance: tuple[Provenance, ...]
    decision: str
    confidence: float
    retrieval: Mapping[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "conversation_id": self.conversation_id,
            "generated_ns": self.generated_ns,
            "working_state": self.working_state.as_dict(),
            "perspective": None if self.perspective is None else self.perspective.as_dict(),
            "immediate_context": [_record_dict(x) for x in self.immediate_context],
            "recalled_episodes": [x.as_dict() for x in self.recalled_episodes],
            "supporting_evidence": [_record_dict(x) for x in self.supporting_evidence],
            "contradicting_evidence": [_record_dict(x) for x in self.contradicting_evidence],
            "prior_actions": list(self.prior_actions),
            "prior_outcomes": list(self.prior_outcomes),
            "open_loops": [x.as_dict() for x in self.open_loops],
            "commitments": [x.as_dict() for x in self.commitments],
            "constraints": [x.as_dict() for x in self.constraints],
            "corrections": [x.as_dict() for x in self.corrections],
            "provenance": [x.as_dict() for x in self.provenance],
            "decision": self.decision,
            "confidence": self.confidence,
            "retrieval": dict(self.retrieval),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))

    def to_context_text(self, *, max_chars: int = 12000) -> str:
        """Optional bounded rendering for an LLM. HDC assistants can consume ``as_dict`` directly."""
        lines = [
            f"MEMORY FRAME v{self.schema_version}",
            f"mode={self.mode} decision={self.decision} confidence={self.confidence:.3f}",
            f"goal={self.working_state.goal or ''}",
        ]
        if self.perspective is not None:
            lines.append(
                "PERSPECTIVE: "
                f"user={self.perspective.user_id} role={self.perspective.role or 'unspecified'} "
                f"authority={self.perspective.authority_level} abstraction={self.perspective.abstraction_level} "
                f"priorities={','.join(self.perspective.priorities)}"
            )
        if self.working_state.facts:
            lines.append("CURRENT FACTS: " + " | ".join(f"{x.key}={x.value}" for x in self.working_state.facts))
        if self.open_loops:
            lines.append("OPEN LOOPS: " + " | ".join(x.value for x in self.open_loops))
        if self.constraints:
            lines.append("CONSTRAINTS: " + " | ".join(x.value for x in self.constraints))
        if self.corrections:
            lines.append("CORRECTIONS: " + " | ".join(f"{x.key}: {x.old_value} -> {x.new_value}" for x in self.corrections[-8:]))
        if self.immediate_context:
            lines.append("IMMEDIATE CONTEXT:")
            lines.extend(f"- {x.source}" for x in self.immediate_context)
        if self.recalled_episodes:
            lines.append("RECALLED EPISODES:")
            for ep in self.recalled_episodes:
                lines.append(f"- episode {ep.episode_id} score={ep.score:.3f}")
                for r in ep.records:
                    detail = r.source
                    if r.action:
                        detail += f" action={r.action}"
                    if r.outcome:
                        detail += f" outcome={r.outcome}"
                    lines.append("  - " + detail)
        text = "\n".join(lines)
        return text[:max_chars]


def _record_dict(r: ExperienceRecord) -> dict:
    return {
        "slot": r.slot,
        "timestamp_ns": r.timestamp_ns,
        "conversation_id": r.conversation_id,
        "episode_id": r.episode_id,
        "tenant_id": r.tenant_id,
        "actor_user_id": r.actor_user_id,
        "actor_role": r.actor_role,
        "authority_level": r.authority_level,
        "abstraction_level": r.abstraction_level,
        "memory_scope": r.memory_scope,
        "perspective_version": r.perspective_version,
        "role": r.role,
        "record_type": r.record_type,
        "namespace": r.namespace,
        "importance": r.importance,
        "source": r.source,
        "action": r.action,
        "outcome": r.outcome,
        "outcome_score": r.outcome_score,
        "extra": dict(r.extra),
    }


@dataclass(frozen=True, slots=True)
class TransitionResult:
    slot: int
    before: WorkingState
    after: WorkingState


@dataclass(frozen=True, slots=True)
class ActionGateResult:
    assessment: ActionAssessment
    frame: MemoryFrame


class AssistantMemory:
    """Assistant-ready HNG memory facade.

    Immediate continuity is deterministic through WorkingMemory. Long-horizon recall is
    associative through MultiHeadMemory. One committed transition record carries both the
    semantic heads and the replayable working-state mutation.
    """

    DEFAULT_HEADS = ("state", "goal", "entity", "sequence", "perspective", "expertise", "priority", "action", "outcome", "next_state")

    def __init__(self, root: str | Path, *, hv_dim: int = 10_000, space_id: str = "default",
                 heads: Iterable[str] = DEFAULT_HEADS, recent_limit: int = 8,
                 auto_index: bool = True, index_options: Mapping[str, int] | None = None):
        self.memory = MultiHeadMemory(root, heads=tuple(heads), hv_dim=hv_dim, space_id=space_id,
                                      auto_index=auto_index, index_options=index_options)
        self.working = WorkingMemory(self.memory.db, recent_limit=recent_limit)
        self.perspectives = PerspectiveStore(self.memory.db)
        self.harness = MemoryHarness(self.memory)

    def set_user_profile(self, profile: PerspectiveProfile) -> PerspectiveProfile:
        return self.perspectives.set_profile(profile)

    def user_profile(self, user_id: str) -> PerspectiveProfile | None:
        return self.perspectives.profile(user_id)

    def activate_perspective(self, conversation_id: int, user_id: str,
                             override: PerspectiveOverride | None = None) -> EffectivePerspective:
        return self.perspectives.activate(conversation_id, user_id, override)

    def clear_perspective(self, conversation_id: int) -> None:
        self.perspectives.clear(conversation_id)

    def perspective(self, conversation_id: int) -> EffectivePerspective | None:
        return self.perspectives.effective(conversation_id)

    def working_state(self, conversation_id: int) -> WorkingState:
        return self.working.state(conversation_id)

    def current_semantic_heads(self, conversation_id: int) -> Mapping[str, object]:
        """Return the HDC working-state heads carried forward from the last committed transition.

        ``next_state`` becomes the current ``state`` when present. Other persistent context
        heads are read exactly from the last transition. This is direct slot access, not ANN.
        """
        working = self.working_state(conversation_id)
        if working.last_slot is None:
            return {}
        rec = self.memory.db.get(working.last_slot)
        if rec is None:
            return {}
        out: dict[str, object] = {}
        def has(head: str) -> bool:
            bit = self.memory.db.head_bits.get(head)
            return bit is not None and (rec.head_mask & bit) != 0
        if "next_state" in self.memory.vector_stores and has("next_state"):
            packed = self.memory.vector_stores["next_state"].read_slots([working.last_slot])[0]
            out["state"] = unpack_hv(packed, self.memory.hv_dim)
            out["next_state"] = out["state"]
        elif "state" in self.memory.vector_stores and has("state"):
            packed = self.memory.vector_stores["state"].read_slots([working.last_slot])[0]
            out["state"] = unpack_hv(packed, self.memory.hv_dim)
        for head in ("goal", "entity", "sequence"):
            if head in self.memory.vector_stores and has(head):
                packed = self.memory.vector_stores[head].read_slots([working.last_slot])[0]
                out[head] = unpack_hv(packed, self.memory.hv_dim)
        return out

    def integration_context(self, conversation_id: int) -> AssistantContext:
        return AssistantContext(
            working_state=self.working_state(conversation_id),
            semantic_heads=self.current_semantic_heads(conversation_id),
            recent_records=self.working.recent_records(conversation_id),
            perspective=self.perspective(conversation_id),
        )

    def encode_query(self, adapter: AssistantSemanticAdapter, value: object, *, conversation_id: int) -> Mapping[str, object]:
        return adapter.encode(value, context=self.integration_context(conversation_id))

    def record_transition(self, semantic_heads: Mapping[str, object], observation: str, *,
                          conversation_id: int, episode_id: int, action: str = "", outcome: str = "",
                          outcome_score: float = 0.0, working_update: WorkingUpdate | None = None,
                          role: str = "assistant", namespace: str = "", importance: float = 0.0,
                          tags: Iterable[str] = (), timestamp_ns: int | None = None,
                          extra: Mapping[str, object] | None = None, durable: bool = False,
                          memory_scope: str | None = None, perspective: EffectivePerspective | None = None) -> TransitionResult:
        before = self.working.state(conversation_id)
        active_perspective = perspective if perspective is not None else self.perspective(conversation_id)
        if memory_scope is None:
            memory_scope = "private" if active_perspective is not None else "global"
        if memory_scope not in {"private", "tenant", "global"}:
            raise ValueError("memory_scope must be private, tenant, or global")
        next_slot = self.memory.db.committed_count
        rels = []
        if before.last_slot is not None:
            rels.append(Relation(src_slot=next_slot, relation="FOLLOWS", dst_slot=before.last_slot, weight=1.0))
        merged_extra = dict(extra or {})
        merged_extra["working_update"] = (working_update or WorkingUpdate()).as_dict()
        merged_extra["transition"] = {
            "previous_slot": before.last_slot,
            "turn_index": before.turn_index,
            "has_next_state": "next_state" in semantic_heads,
        }
        if active_perspective is not None:
            merged_extra["perspective"] = active_perspective.as_dict()
        slot = self.memory.remember(
            semantic_heads,
            observation,
            timestamp_ns=timestamp_ns,
            conversation_id=conversation_id,
            episode_id=episode_id,
            role=role,
            record_type="transition",
            namespace=namespace,
            importance=importance,
            tags=tags,
            action=action,
            outcome=outcome,
            outcome_score=outcome_score,
            extra=merged_extra,
            tenant_id="" if active_perspective is None else active_perspective.tenant_id,
            actor_user_id="" if active_perspective is None else active_perspective.user_id,
            actor_role="" if active_perspective is None else active_perspective.role,
            authority_level=-1 if active_perspective is None else active_perspective.authority_level,
            abstraction_level=-1 if active_perspective is None else active_perspective.abstraction_level,
            memory_scope=memory_scope,
            perspective_version=0 if active_perspective is None else active_perspective.profile_revision,
            relations=rels,
            durable=durable,
        )
        rec = self.memory.db.get(slot)
        if rec is None:
            raise RuntimeError("committed transition record is missing")
        after = self.working.advance_committed(before, rec)
        return TransitionResult(slot=slot, before=before, after=after)

    def _frame_from_recall(self, conversation_id: int, result: MultiHeadRecall, *, mode: str,
                           decision: str = "inform", confidence: float | None = None,
                           max_episodes: int = 4) -> MemoryFrame:
        working = self.working.state(conversation_id)
        immediate = self.working.recent_records(conversation_id)
        episodes: list[EpisodeMemory] = []
        provenance: list[Provenance] = []
        support: list[ExperienceRecord] = []
        contradict: list[ExperienceRecord] = []
        actions: list[str] = []
        outcomes: list[str] = []
        seen_episodes: set[int] = set()
        for hit in result.hits:
            provenance.append(Provenance(hit.slot, hit.record.episode_id, hit.score, hit.head_scores, hit.record.source))
            if hit.record.outcome_score > 0:
                support.append(hit.record)
            elif hit.record.outcome_score < 0:
                contradict.append(hit.record)
            if hit.record.action:
                actions.append(hit.record.action)
            if hit.record.outcome:
                outcomes.append(hit.record.outcome)
            eid = hit.record.episode_id
            if len(episodes) < max_episodes and eid not in seen_episodes:
                records = tuple(self.memory.db.episode(eid, conversation_id=hit.record.conversation_id)) if eid else (hit.record,)
                episodes.append(EpisodeMemory(eid, hit.slot, hit.score, records))
                seen_episodes.add(eid)
        if confidence is None:
            confidence = result.hits[0].score if result.hits else 0.0
        stats = result.stats
        retrieval = {
            "queried_heads": list(stats.queried_heads),
            "routed_by_head": dict(stats.routed_by_head),
            "routed_union": stats.routed_union,
            "eligible_candidates": stats.eligible_candidates,
            "exact_candidates": stats.exact_candidates,
            "exact_fraction": stats.exact_fraction,
            "elapsed_seconds": stats.elapsed_seconds,
        }
        return MemoryFrame(
            schema_version=2,
            mode=mode,
            conversation_id=int(conversation_id),
            generated_ns=time.time_ns(),
            working_state=working,
            perspective=self.perspective(conversation_id),
            immediate_context=immediate,
            recalled_episodes=tuple(episodes),
            supporting_evidence=tuple(support),
            contradicting_evidence=tuple(contradict),
            prior_actions=tuple(dict.fromkeys(actions)),
            prior_outcomes=tuple(dict.fromkeys(outcomes)),
            open_loops=working.open_loops,
            commitments=working.commitments,
            constraints=working.constraints,
            corrections=working.corrections,
            provenance=tuple(provenance),
            decision=decision,
            confidence=float(confidence),
            retrieval=retrieval,
        )

    def _apply_perspective_filter(self, conversation_id: int, memory_filter: MemoryFilter | None,
                                  policy: PerspectivePolicy | None) -> MemoryFilter | None:
        if policy is None:
            policy = PerspectivePolicy.context()
        return policy.apply(memory_filter, self.perspective(conversation_id))

    def prepare_context(self, query_heads: Mapping[str, object], *, conversation_id: int,
                        top_k: int = 8, memory_filter: MemoryFilter | None = None,
                        weights: Mapping[str, float] | None = None, probe_radius: int = 1,
                        rerank_candidates: int = 128, min_similarity: Mapping[str, float] | None = None,
                        required_route_heads: Iterable[str] = (),
                        perspective_policy: PerspectivePolicy | None = None) -> MemoryFrame:
        memory_filter = self._apply_perspective_filter(conversation_id, memory_filter, perspective_policy)
        result = self.memory.recall(
            query_heads,
            weights=weights,
            top_k=top_k,
            memory_filter=memory_filter,
            probe_radius=probe_radius,
            rerank_candidates=rerank_candidates,
            min_similarity=min_similarity,
            required_route_heads=required_route_heads,
        )
        return self._frame_from_recall(conversation_id, result, mode="context")

    def prepare_context_from_adapter(self, adapter: AssistantSemanticAdapter, value: object, *, conversation_id: int, **kwargs) -> MemoryFrame:
        heads = self.encode_query(adapter, value, conversation_id=conversation_id)
        return self.prepare_context(heads, conversation_id=conversation_id, **kwargs)


    def recall_transitions(self, context_heads: Mapping[str, object], *, conversation_id: int,
                           proposed_action=None, semantic_floor: float = 0.80, action_floor: float | None = None,
                           top_k: int = 8, memory_filter: MemoryFilter | None = None, adaptive_probe: bool = True,
                           max_probe_radius: int = 2, perspective_policy: PerspectivePolicy | None = None) -> MemoryFrame:
        """Recall historical transitions under explicit semantic conjunction.

        When ``proposed_action`` is supplied the action head becomes a required evidence
        constraint. Returned records expose the historical ``action``, ``outcome`` and
        ``outcome_score`` while ``next_state`` remains available as an exact semantic head.
        """
        q = dict(context_heads)
        if proposed_action is not None:
            q["action"] = proposed_action
        mins = {h: float(semantic_floor) for h in q}
        if proposed_action is not None:
            mins["action"] = float(semantic_floor if action_floor is None else action_floor)
        required = tuple(q)
        memory_filter = self._apply_perspective_filter(conversation_id, memory_filter,
                                                       PerspectivePolicy.action() if perspective_policy is None else perspective_policy)
        kwargs = dict(
            weights={h: (3.0 if h == "action" and proposed_action is not None else 1.0) for h in q},
            top_k=top_k, memory_filter=memory_filter, rerank_candidates=128,
            min_similarity=mins, required_route_heads=required,
        )
        if adaptive_probe:
            result = self.memory.recall_adaptive(q, start_radius=1, max_radius=max_probe_radius,
                                                 min_hits=1, **kwargs)
        else:
            result = self.memory.recall(q, probe_radius=1, **kwargs)
        return self._frame_from_recall(conversation_id, result, mode="transition_recall")

    def recommend_actions(self, context_heads: Mapping[str, object], *, conversation_id: int,
                          perspective_policy: PerspectivePolicy | None = None, **kwargs) -> tuple[ActionRecommendation, ...]:
        """Return a small historically grounded candidate set for a large action library.

        ``conversation_id`` is accepted for symmetry with the assistant-facing APIs; long-
        term recommendations intentionally search across conversations unless a MemoryFilter
        restricts them.
        """
        memory_filter = kwargs.pop("memory_filter", None)
        kwargs["memory_filter"] = self._apply_perspective_filter(
            conversation_id, memory_filter, PerspectivePolicy.action() if perspective_policy is None else perspective_policy
        )
        return self.harness.recommend_actions(context_heads, **kwargs)

    def evaluate_action(self, context_heads: Mapping[str, object], proposed_action, *, conversation_id: int,
                        perspective_policy: PerspectivePolicy | None = None, **kwargs) -> ActionGateResult:
        memory_filter = kwargs.pop("memory_filter", None)
        kwargs["memory_filter"] = self._apply_perspective_filter(
            conversation_id, memory_filter, PerspectivePolicy.action() if perspective_policy is None else perspective_policy
        )
        assessment = self.harness.assess_action(context_heads, proposed_action, **kwargs)
        # Rebuild a compact recall object from the evidence anchors to produce the same stable MemoryFrame contract.
        hits = tuple(f.anchor for f in assessment.frames)
        if hits:
            result = MultiHeadRecall(hits, assessment.frames[0].stats)
        else:
            stats = MultiHeadStats(
                current_records=self.memory.db.committed_count,
                queried_heads=tuple(context_heads),
                routed_by_head={}, routed_union=0, eligible_candidates=0, exact_candidates=0,
                exact_fraction=0.0, elapsed_seconds=0.0,
            )
            result = MultiHeadRecall((), stats)
        frame = self._frame_from_recall(
            conversation_id,
            result,
            mode="action_gate",
            decision=assessment.decision,
            confidence=abs(assessment.evidence_score) if assessment.evidence_count else 0.0,
        )
        return ActionGateResult(assessment=assessment, frame=frame)

    def sync(self) -> None:
        self.memory.sync()

    def rebuild_index(self, head: str | None = None) -> None:
        self.memory.rebuild_index(head)

    def close(self) -> None:
        self.memory.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


class ShadowEvaluator:
    """Append-only JSONL shadow-mode recorder.

    It never changes the assistant's behavior. The caller records the live/baseline outcome
    alongside what HNG would have supplied or challenged.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log_context(self, frame: MemoryFrame, *, baseline: Mapping[str, object] | None = None) -> None:
        self._append({"kind": "context", "frame": frame.as_dict(), "baseline": dict(baseline or {})})

    def log_action(self, result: ActionGateResult, *, proposed_action: str = "",
                   baseline: Mapping[str, object] | None = None) -> None:
        self._append({
            "kind": "action_gate",
            "proposed_action": proposed_action,
            "assessment": result.assessment.as_dict(),
            "frame": result.frame.as_dict(),
            "baseline": dict(baseline or {}),
        })

    def summarize(self) -> dict:
        if not self.path.exists():
            return {"records": 0, "contexts": 0, "actions": 0, "decisions": {}, "labeled_accuracy": None}
        records = 0; contexts = 0; actions = 0; decisions: dict[str, int] = {}
        labeled = 0; correct = 0
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line); records += 1
                if row.get("kind") == "context":
                    contexts += 1
                elif row.get("kind") == "action_gate":
                    actions += 1
                    decision = str((row.get("assessment") or {}).get("decision", ""))
                    decisions[decision] = decisions.get(decision, 0) + 1
                    expected = (row.get("baseline") or {}).get("expected_decision")
                    if expected is not None:
                        labeled += 1; correct += int(str(expected) == decision)
        return {
            "records": records, "contexts": contexts, "actions": actions, "decisions": decisions,
            "labeled_accuracy": (correct / labeled) if labeled else None, "labeled": labeled,
        }

    def _append(self, payload: Mapping[str, object]) -> None:
        record = {"timestamp_ns": time.time_ns(), **dict(payload)}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
