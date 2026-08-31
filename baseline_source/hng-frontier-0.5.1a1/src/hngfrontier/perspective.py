from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import time
from typing import Mapping

from .store import MemoryFilter


def _level(value: int, *, name: str, minimum: int = 0, maximum: int = 5) -> int:
    value = int(value)
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class PerspectiveProfile:
    """Explicit, user-controlled durable perspective profile.

    HNG does not infer these fields from prose. Applications may populate them from their
    own account/profile system or from an HDC interpreter, and users should be able to
    inspect/change them.  The profile is intentionally small: semantic nuance belongs in
    optional HDC heads such as ``perspective``, ``expertise`` and ``priority``.
    """
    user_id: str
    tenant_id: str = ""
    role: str = ""
    authority_level: int = 0
    abstraction_level: int = 0
    expertise: Mapping[str, float] = field(default_factory=dict)
    responsibilities: tuple[str, ...] = ()
    priorities: tuple[str, ...] = ()
    extra: Mapping[str, object] = field(default_factory=dict)
    revision: int = 0

    def __post_init__(self):
        if not str(self.user_id):
            raise ValueError("user_id must be non-empty")
        _level(self.authority_level, name="authority_level")
        _level(self.abstraction_level, name="abstraction_level", maximum=4)
        for domain, score in self.expertise.items():
            if not str(domain):
                raise ValueError("expertise domain must be non-empty")
            if float(score) < 0.0 or float(score) > 1.0:
                raise ValueError("expertise levels must be in [0,1]")

    def as_dict(self) -> dict:
        return {
            "user_id": self.user_id, "tenant_id": self.tenant_id, "role": self.role,
            "authority_level": self.authority_level, "abstraction_level": self.abstraction_level,
            "expertise": {str(k): float(v) for k, v in self.expertise.items()},
            "responsibilities": list(self.responsibilities), "priorities": list(self.priorities),
            "extra": dict(self.extra), "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class PerspectiveOverride:
    """Conversation-local acting perspective for the same durable person."""
    role: str | None = None
    authority_level: int | None = None
    abstraction_level: int | None = None
    expertise: Mapping[str, float] | None = None
    responsibilities: tuple[str, ...] | None = None
    priorities: tuple[str, ...] | None = None
    extra: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self):
        if self.authority_level is not None:
            _level(self.authority_level, name="authority_level")
        if self.abstraction_level is not None:
            _level(self.abstraction_level, name="abstraction_level", maximum=4)

    def as_dict(self) -> dict:
        return {
            "role": self.role, "authority_level": self.authority_level,
            "abstraction_level": self.abstraction_level,
            "expertise": None if self.expertise is None else {str(k): float(v) for k, v in self.expertise.items()},
            "responsibilities": None if self.responsibilities is None else list(self.responsibilities),
            "priorities": None if self.priorities is None else list(self.priorities),
            "extra": dict(self.extra),
        }


@dataclass(frozen=True, slots=True)
class EffectivePerspective:
    user_id: str
    tenant_id: str
    role: str
    authority_level: int
    abstraction_level: int
    expertise: Mapping[str, float]
    responsibilities: tuple[str, ...]
    priorities: tuple[str, ...]
    profile_revision: int
    active_override: bool
    extra: Mapping[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "user_id": self.user_id, "tenant_id": self.tenant_id, "role": self.role,
            "authority_level": self.authority_level, "abstraction_level": self.abstraction_level,
            "expertise": {str(k): float(v) for k, v in self.expertise.items()},
            "responsibilities": list(self.responsibilities), "priorities": list(self.priorities),
            "profile_revision": self.profile_revision, "active_override": self.active_override,
            "extra": dict(self.extra),
        }


@dataclass(frozen=True, slots=True)
class PerspectivePolicy:
    """Non-semantic eligibility policy applied before exact semantic ranking.

    Access scope is always independent of semantic similarity.  Role/authority/abstraction
    can be gated for action/control queries while still allowing generic memories that carry
    no actor metadata.
    """
    enforce_access: bool = True
    gate_role: bool = True
    gate_authority: bool = True
    gate_abstraction: bool = True
    abstraction_tolerance: int = 1
    allow_unscoped_actor: bool = True
    scopes: tuple[str, ...] = ("private", "tenant", "global")

    @classmethod
    def disabled(cls) -> "PerspectivePolicy":
        return cls(False, False, False, False, 4, True, ())

    @classmethod
    def context(cls) -> "PerspectivePolicy":
        return cls(True, True, True, True, 1, True, ("private", "tenant", "global"))

    @classmethod
    def action(cls) -> "PerspectivePolicy":
        return cls(True, True, True, True, 1, True, ("private", "tenant", "global"))

    def apply(self, base: MemoryFilter | None, p: EffectivePerspective | None) -> MemoryFilter | None:
        if p is None or self == self.disabled():
            return base
        f = base or MemoryFilter()
        kwargs = {}
        if self.enforce_access:
            kwargs.update(access_user_id=p.user_id, access_tenant_id=p.tenant_id, scopes=self.scopes)
        if self.gate_role and p.role:
            kwargs.update(actor_role=p.role, allow_unscoped_actor=self.allow_unscoped_actor)
        if self.gate_authority:
            kwargs.update(max_authority_level=p.authority_level, allow_unscoped_actor=self.allow_unscoped_actor)
        if self.gate_abstraction:
            lo = max(0, p.abstraction_level - int(self.abstraction_tolerance))
            hi = min(4, p.abstraction_level + int(self.abstraction_tolerance))
            kwargs.update(min_abstraction_level=lo, max_abstraction_level=hi,
                          allow_unscoped_actor=self.allow_unscoped_actor)
        return replace(f, **kwargs)


class PerspectiveStore:
    """Durable profile + conversation perspective tables in the authoritative SQLite DB."""
    def __init__(self, experience_store):
        self.store = experience_store
        self.con = experience_store.con
        # Perspective is read on every assistant turn. Cache both positive and negative
        # lookups so conversations without an activated profile stay on the pre-0.5
        # fast path rather than issuing SQLite reads on every transition. Mutations below
        # invalidate the relevant cache entries.
        self._profile_cache: dict[str, PerspectiveProfile | None] = {}
        self._effective_cache: dict[int, EffectivePerspective | None] = {}
        if not experience_store.read_only:
            self._init_schema()

    def _init_schema(self):
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_profiles(
              user_id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL DEFAULT '',
              revision INTEGER NOT NULL DEFAULT 1,
              role TEXT NOT NULL DEFAULT '',
              authority_level INTEGER NOT NULL DEFAULT 0,
              abstraction_level INTEGER NOT NULL DEFAULT 0,
              expertise_json TEXT NOT NULL DEFAULT '{}',
              responsibilities_json TEXT NOT NULL DEFAULT '[]',
              priorities_json TEXT NOT NULL DEFAULT '[]',
              extra_json TEXT NOT NULL DEFAULT '{}',
              updated_ns INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversation_perspectives(
              conversation_id INTEGER PRIMARY KEY,
              user_id TEXT NOT NULL,
              override_json TEXT NOT NULL DEFAULT '{}',
              updated_ns INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_profile_tenant ON user_profiles(tenant_id, user_id);
            """
        )
        self.con.commit()

    def set_profile(self, profile: PerspectiveProfile) -> PerspectiveProfile:
        if self.store.read_only:
            raise PermissionError("read-only perspective store")
        current = self.profile(profile.user_id)
        revision = (current.revision + 1) if current is not None else max(1, int(profile.revision) or 1)
        now = time.time_ns()
        self.con.execute(
            """INSERT INTO user_profiles(user_id,tenant_id,revision,role,authority_level,abstraction_level,
               expertise_json,responsibilities_json,priorities_json,extra_json,updated_ns)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET tenant_id=excluded.tenant_id,revision=excluded.revision,
               role=excluded.role,authority_level=excluded.authority_level,abstraction_level=excluded.abstraction_level,
               expertise_json=excluded.expertise_json,responsibilities_json=excluded.responsibilities_json,
               priorities_json=excluded.priorities_json,extra_json=excluded.extra_json,updated_ns=excluded.updated_ns""",
            (profile.user_id, profile.tenant_id, revision, profile.role, int(profile.authority_level),
             int(profile.abstraction_level), json.dumps(dict(profile.expertise), sort_keys=True, separators=(",", ":")),
             json.dumps(list(profile.responsibilities), separators=(",", ":")),
             json.dumps(list(profile.priorities), separators=(",", ":")),
             json.dumps(dict(profile.extra), sort_keys=True, separators=(",", ":")), now),
        )
        self.con.commit()
        # The profile changed, so both the profile object and any conversation-level
        # effective perspective derived from it are stale. Clearing the small effective
        # cache is deterministic and avoids a reverse-index bookkeeping structure.
        self._profile_cache.pop(str(profile.user_id), None)
        self._effective_cache.clear()
        out = self.profile(profile.user_id)
        assert out is not None
        return out

    def profile(self, user_id: str) -> PerspectiveProfile | None:
        user_id = str(user_id)
        if user_id in self._profile_cache:
            return self._profile_cache[user_id]
        r = self.con.execute("SELECT * FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
        if r is None:
            self._profile_cache[user_id] = None
            return None
        out = PerspectiveProfile(
            user_id=str(r["user_id"]), tenant_id=str(r["tenant_id"]), role=str(r["role"]),
            authority_level=int(r["authority_level"]), abstraction_level=int(r["abstraction_level"]),
            expertise={str(k): float(v) for k, v in json.loads(r["expertise_json"] or "{}").items()},
            responsibilities=tuple(str(x) for x in json.loads(r["responsibilities_json"] or "[]")),
            priorities=tuple(str(x) for x in json.loads(r["priorities_json"] or "[]")),
            extra=dict(json.loads(r["extra_json"] or "{}")), revision=int(r["revision"]),
        )
        self._profile_cache[user_id] = out
        return out

    def activate(self, conversation_id: int, user_id: str, override: PerspectiveOverride | None = None) -> EffectivePerspective:
        if self.store.read_only:
            raise PermissionError("read-only perspective store")
        if self.profile(user_id) is None:
            raise KeyError(f"unknown user profile: {user_id}")
        payload = (override or PerspectiveOverride()).as_dict()
        self.con.execute(
            """INSERT INTO conversation_perspectives(conversation_id,user_id,override_json,updated_ns)
               VALUES(?,?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET user_id=excluded.user_id,
               override_json=excluded.override_json,updated_ns=excluded.updated_ns""",
            (int(conversation_id), str(user_id), json.dumps(payload, sort_keys=True, separators=(",", ":")), time.time_ns()),
        )
        self.con.commit()
        self._effective_cache.pop(int(conversation_id), None)
        out = self.effective(conversation_id)
        assert out is not None
        return out

    def clear(self, conversation_id: int) -> None:
        if self.store.read_only:
            raise PermissionError("read-only perspective store")
        conversation_id = int(conversation_id)
        self.con.execute("DELETE FROM conversation_perspectives WHERE conversation_id=?", (conversation_id,))
        self.con.commit()
        self._effective_cache[conversation_id] = None

    def effective(self, conversation_id: int) -> EffectivePerspective | None:
        conversation_id = int(conversation_id)
        if conversation_id in self._effective_cache:
            return self._effective_cache[conversation_id]
        r = self.con.execute("SELECT user_id,override_json FROM conversation_perspectives WHERE conversation_id=?",
                             (conversation_id,)).fetchone()
        if r is None:
            self._effective_cache[conversation_id] = None
            return None
        p = self.profile(str(r["user_id"]))
        if p is None:
            self._effective_cache[conversation_id] = None
            return None
        raw = dict(json.loads(r["override_json"] or "{}"))
        has_override = any(v not in (None, {}, [], ()) for v in raw.values())
        role = p.role if raw.get("role") is None else str(raw.get("role"))
        authority = p.authority_level if raw.get("authority_level") is None else int(raw.get("authority_level"))
        abstraction = p.abstraction_level if raw.get("abstraction_level") is None else int(raw.get("abstraction_level"))
        expertise = dict(p.expertise) if raw.get("expertise") is None else {str(k): float(v) for k, v in dict(raw.get("expertise") or {}).items()}
        responsibilities = p.responsibilities if raw.get("responsibilities") is None else tuple(str(x) for x in raw.get("responsibilities") or ())
        priorities = p.priorities if raw.get("priorities") is None else tuple(str(x) for x in raw.get("priorities") or ())
        extra = dict(p.extra); extra.update(dict(raw.get("extra") or {}))
        out = EffectivePerspective(
            user_id=p.user_id, tenant_id=p.tenant_id, role=role, authority_level=authority,
            abstraction_level=abstraction, expertise=expertise, responsibilities=responsibilities,
            priorities=priorities, profile_revision=p.revision, active_override=has_override, extra=extra,
        )
        self._effective_cache[conversation_id] = out
        return out
