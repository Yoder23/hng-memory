from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .store import ExperienceRecord, ExperienceStore

_ALLOWED_KINDS = {"fact", "open_loop", "commitment", "constraint", "entity", "topic"}


@dataclass(frozen=True, slots=True)
class WorkingItemSpec:
    """Explicit deterministic working-memory mutation supplied by the assistant/interpreter."""
    kind: str
    key: str
    value: str
    extra: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in _ALLOWED_KINDS:
            raise ValueError(f"unsupported working-memory kind: {self.kind}")
        if not self.key:
            raise ValueError("working-memory item key must be non-empty")

    def as_dict(self) -> dict:
        return {"kind": self.kind, "key": self.key, "value": self.value, "extra": dict(self.extra)}

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "WorkingItemSpec":
        return cls(
            kind=str(value["kind"]),
            key=str(value["key"]),
            value=str(value.get("value", "")),
            extra=dict(value.get("extra") or {}),
        )


@dataclass(frozen=True, slots=True)
class WorkingUpdate:
    """A replayable state mutation committed inside a transition memory record.

    HNG deliberately does not infer these mutations from text. The HDC assistant/interpreter
    supplies them explicitly, which makes state continuity deterministic and auditable.
    """
    set_goal: str | None = None
    add: tuple[WorkingItemSpec, ...] = ()
    resolve: tuple[str, ...] = ()
    supersede: tuple[WorkingItemSpec, ...] = ()
    clear_goal: bool = False

    def as_dict(self) -> dict:
        return {
            "set_goal": self.set_goal,
            "clear_goal": bool(self.clear_goal),
            "add": [x.as_dict() for x in self.add],
            "resolve": list(self.resolve),
            "supersede": [x.as_dict() for x in self.supersede],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object] | None) -> "WorkingUpdate":
        value = dict(value or {})
        return cls(
            set_goal=None if value.get("set_goal") is None else str(value.get("set_goal")),
            clear_goal=bool(value.get("clear_goal", False)),
            add=tuple(WorkingItemSpec.from_dict(x) for x in (value.get("add") or ())),
            resolve=tuple(str(x) for x in (value.get("resolve") or ())),
            supersede=tuple(WorkingItemSpec.from_dict(x) for x in (value.get("supersede") or ())),
        )


@dataclass(frozen=True, slots=True)
class WorkingItem:
    kind: str
    key: str
    value: str
    opened_slot: int
    updated_slot: int
    extra: Mapping[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "key": self.key,
            "value": self.value,
            "opened_slot": self.opened_slot,
            "updated_slot": self.updated_slot,
            "extra": dict(self.extra),
        }


@dataclass(frozen=True, slots=True)
class Correction:
    kind: str
    key: str
    old_value: str
    new_value: str
    slot: int

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "key": self.key,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "slot": self.slot,
        }


@dataclass(frozen=True, slots=True)
class WorkingState:
    conversation_id: int
    episode_id: int
    last_slot: int | None
    turn_index: int
    goal: str | None
    items: tuple[WorkingItem, ...]
    corrections: tuple[Correction, ...]
    recent_slots: tuple[int, ...]

    def items_of(self, kind: str) -> tuple[WorkingItem, ...]:
        return tuple(x for x in self.items if x.kind == kind)

    @property
    def open_loops(self) -> tuple[WorkingItem, ...]:
        return self.items_of("open_loop")

    @property
    def commitments(self) -> tuple[WorkingItem, ...]:
        return self.items_of("commitment")

    @property
    def constraints(self) -> tuple[WorkingItem, ...]:
        return self.items_of("constraint")

    @property
    def facts(self) -> tuple[WorkingItem, ...]:
        return self.items_of("fact")

    @property
    def entities(self) -> tuple[WorkingItem, ...]:
        return self.items_of("entity")

    @property
    def topics(self) -> tuple[WorkingItem, ...]:
        return self.items_of("topic")

    def as_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "episode_id": self.episode_id,
            "last_slot": self.last_slot,
            "turn_index": self.turn_index,
            "goal": self.goal,
            "items": [x.as_dict() for x in self.items],
            "corrections": [x.as_dict() for x in self.corrections],
            "recent_slots": list(self.recent_slots),
        }


class WorkingMemory:
    """Deterministic conversation state rebuilt from committed transition records.

    This is intentionally *not* ANN memory. Recent continuity and active state are known
    facts and should never depend on nearest-neighbor retrieval. Each transition embeds a
    replayable ``working_update`` in its authoritative SQLite record, so the materialized
    working state can always be reconstructed after a restart.
    """

    def __init__(self, store: ExperienceStore, *, recent_limit: int = 8):
        self.store = store
        self.recent_limit = int(recent_limit)
        if self.recent_limit < 0:
            raise ValueError("recent_limit must be >= 0")
        self._cache: dict[int, tuple[int | None, WorkingState]] = {}

    def invalidate(self, conversation_id: int | None = None) -> None:
        if conversation_id is None:
            self._cache.clear()
        else:
            self._cache.pop(int(conversation_id), None)

    def _records(self, conversation_id: int) -> list[ExperienceRecord]:
        rows = self.store.con.execute(
            "SELECT slot FROM memories WHERE conversation_id=? AND deleted=0 AND record_type='transition' ORDER BY slot",
            (int(conversation_id),),
        ).fetchall()
        return self.store.get_many(int(r[0]) for r in rows)

    def _advance(self, state: WorkingState, rec: ExperienceRecord) -> WorkingState:
        active = {x.key: x for x in state.items}
        corrections = list(state.corrections)
        goal = state.goal
        update = WorkingUpdate.from_dict((rec.extra or {}).get("working_update") if rec.extra else None)
        if update.clear_goal:
            goal = None
        if update.set_goal is not None:
            goal = update.set_goal
        for key in update.resolve:
            active.pop(str(key), None)
        for spec in update.supersede:
            previous = active.get(spec.key)
            if previous is not None:
                corrections.append(Correction(spec.kind, spec.key, previous.value, spec.value, rec.slot))
                opened = previous.opened_slot
            else:
                opened = rec.slot
            active[spec.key] = WorkingItem(spec.kind, spec.key, spec.value, opened, rec.slot, dict(spec.extra))
        for spec in update.add:
            previous = active.get(spec.key)
            opened = previous.opened_slot if previous is not None else rec.slot
            active[spec.key] = WorkingItem(spec.kind, spec.key, spec.value, opened, rec.slot, dict(spec.extra))
        recent = (*state.recent_slots, rec.slot)
        if self.recent_limit:
            recent = recent[-self.recent_limit:]
        else:
            recent = ()
        return WorkingState(
            conversation_id=state.conversation_id, episode_id=rec.episode_id or state.episode_id,
            last_slot=rec.slot, turn_index=state.turn_index + 1, goal=goal,
            items=tuple(sorted(active.values(), key=lambda x: (x.kind, x.key))),
            corrections=tuple(corrections[-32:]), recent_slots=tuple(recent),
        )

    def advance_committed(self, before: WorkingState, rec: ExperienceRecord) -> WorkingState:
        """Advance the in-process materialized state after an authoritative commit.

        This keeps live turn updates O(1) in conversation length. Restart recovery still
        reconstructs state by replaying committed records, so the cache is never truth.
        """
        if rec.conversation_id != before.conversation_id:
            raise ValueError("conversation mismatch")
        if before.last_slot is not None and rec.slot <= before.last_slot:
            self.invalidate(before.conversation_id)
            return self.state(before.conversation_id)
        after = self._advance(before, rec)
        self._cache[before.conversation_id] = (rec.slot, after)
        return after

    def state(self, conversation_id: int) -> WorkingState:
        conversation_id = int(conversation_id)
        row = self.store.con.execute(
            "SELECT MAX(slot) FROM memories WHERE conversation_id=? AND deleted=0 AND record_type='transition'",
            (conversation_id,),
        ).fetchone()
        max_slot = None if row is None or row[0] is None else int(row[0])
        cached = self._cache.get(conversation_id)
        if cached is not None and cached[0] == max_slot:
            return cached[1]

        records = self._records(conversation_id)
        state = WorkingState(conversation_id, 0, None, 0, None, (), (), ())
        for rec in records:
            state = self._advance(state, rec)
        self._cache[conversation_id] = (max_slot, state)
        return state

    def recent_records(self, conversation_id: int) -> tuple[ExperienceRecord, ...]:
        state = self.state(conversation_id)
        return tuple(self.store.get_many(state.recent_slots))
