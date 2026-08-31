from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Mapping

from .governance import utc_now_iso
from .semantic import SemanticValue


@dataclass(frozen=True, slots=True)
class PerspectiveField:
    value: object
    confidence: float
    source: str
    user_confirmed: bool = False
    last_updated: str = field(default_factory=utc_now_iso)
    revision: int = 1
    valid_from: str | None = None

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("profile confidence must be in [0,1]")

    @property
    def authoritative(self) -> bool:
        return self.user_confirmed or (self.source in {"authoritative_database", "system_identity"} and self.confidence >= 0.95)

    def as_dict(self) -> dict[str, object]:
        return {
            "value": ({"__semantic_value__": self.value.as_storage()} if isinstance(self.value, SemanticValue) else self.value),
            "confidence": self.confidence, "source": self.source,
            "user_confirmed": self.user_confirmed, "last_updated": self.last_updated,
            "revision": self.revision, "valid_from": self.valid_from,
        }


@dataclass(frozen=True, slots=True)
class GovernedProfile:
    user_id: str
    tenant_id: str
    fields: Mapping[str, PerspectiveField]
    revision: int = 1
    updated_at: str = field(default_factory=utc_now_iso)

    def field(self, name: str) -> PerspectiveField | None:
        return self.fields.get(name)

    def as_dict(self) -> dict[str, object]:
        return {
            "user_id": self.user_id, "tenant_id": self.tenant_id, "revision": self.revision,
            "updated_at": self.updated_at, "fields": {name: value.as_dict() for name, value in self.fields.items()},
        }


@dataclass(frozen=True, slots=True)
class ProfileOverride:
    fields: Mapping[str, PerspectiveField]
    reason: str = "conversation-local explicit override"


@dataclass(frozen=True, slots=True)
class EffectiveProfile:
    user_id: str
    tenant_id: str
    fields: Mapping[str, PerspectiveField]
    profile_revision: int
    override_fields: tuple[str, ...] = ()

    def field(self, name: str) -> PerspectiveField | None:
        return self.fields.get(name)

    def value(self, name: str, default=None):
        field_value = self.field(name)
        return default if field_value is None else field_value.value

    def uncertain(self, names: tuple[str, ...], *, threshold: float = 0.8, require_authoritative: bool = False) -> tuple[str, ...]:
        uncertain = []
        for name in names:
            item = self.field(name)
            if item is None or item.confidence < threshold or (require_authoritative and not item.authoritative):
                uncertain.append(name)
        return tuple(uncertain)

    def as_dict(self) -> dict[str, object]:
        return {
            "user_id": self.user_id, "tenant_id": self.tenant_id, "profile_revision": self.profile_revision,
            "override_fields": list(self.override_fields),
            "fields": {name: value.as_dict() for name, value in self.fields.items()},
        }


class GovernedProfileStore:
    def __init__(self, connection):
        self.con = connection
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS governed_profiles(
              user_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, revision INTEGER NOT NULL,
              fields_json TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS governed_profile_overrides(
              conversation_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
              fields_json TEXT NOT NULL, reason TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS governed_profile_history(
              user_id TEXT NOT NULL,revision INTEGER NOT NULL,tenant_id TEXT NOT NULL,
              fields_json TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(user_id,revision));
            """
        )
        self.con.commit()

    @staticmethod
    def _field(payload: Mapping[str, object]) -> PerspectiveField:
        values = dict(payload)
        encoded = values.get("value")
        if isinstance(encoded, dict) and "__semantic_value__" in encoded:
            values["value"] = SemanticValue.from_storage(encoded["__semantic_value__"])
        return PerspectiveField(**values)

    def set_profile(self, profile: GovernedProfile) -> GovernedProfile:
        previous = self.profile(profile.user_id)
        revision = 1 if previous is None else previous.revision + 1
        updated = GovernedProfile(profile.user_id, profile.tenant_id, dict(profile.fields), revision, utc_now_iso())
        fields_json = json.dumps({name: value.as_dict() for name, value in updated.fields.items()}, sort_keys=True)
        self.con.execute(
            """INSERT INTO governed_profiles VALUES(?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET tenant_id=excluded.tenant_id,revision=excluded.revision,
               fields_json=excluded.fields_json,updated_at=excluded.updated_at""",
            (updated.user_id, updated.tenant_id, updated.revision, fields_json, updated.updated_at),
        )
        self.con.execute("INSERT INTO governed_profile_history VALUES(?,?,?,?,?)",
                         (updated.user_id,updated.revision,updated.tenant_id,fields_json,updated.updated_at))
        self.con.commit()
        return updated

    def profile(self, user_id: str) -> GovernedProfile | None:
        row = self.con.execute("SELECT * FROM governed_profiles WHERE user_id=?", (str(user_id),)).fetchone()
        if row is None:
            return None
        fields = {name: self._field(value) for name, value in json.loads(row["fields_json"]).items()}
        return GovernedProfile(row["user_id"], row["tenant_id"], fields, int(row["revision"]), row["updated_at"])

    def activate(self, conversation_id: str, user_id: str, override: ProfileOverride | None = None) -> EffectiveProfile:
        base = self.profile(user_id)
        if base is None:
            raise KeyError(f"unknown profile: {user_id}")
        if override is not None:
            self.con.execute(
                """INSERT INTO governed_profile_overrides VALUES(?,?,?,?,?)
                   ON CONFLICT(conversation_id) DO UPDATE SET user_id=excluded.user_id,
                   fields_json=excluded.fields_json,reason=excluded.reason,updated_at=excluded.updated_at""",
                (str(conversation_id), str(user_id), json.dumps({name: value.as_dict() for name, value in override.fields.items()}), override.reason, utc_now_iso()),
            )
        else:
            self.con.execute("DELETE FROM governed_profile_overrides WHERE conversation_id=?", (str(conversation_id),))
            self.con.execute(
                "INSERT INTO governed_profile_overrides VALUES(?,?,?,?,?)",
                (str(conversation_id), str(user_id), "{}", "base profile", utc_now_iso()),
            )
        self.con.commit()
        return self.effective(conversation_id)  # type: ignore[return-value]

    def effective(self, conversation_id: str) -> EffectiveProfile | None:
        row = self.con.execute("SELECT * FROM governed_profile_overrides WHERE conversation_id=?", (str(conversation_id),)).fetchone()
        if row is None:
            return None
        base = self.profile(row["user_id"])
        if base is None:
            return None
        overrides = {name: self._field(value) for name, value in json.loads(row["fields_json"]).items()}
        fields = dict(base.fields)
        fields.update(overrides)
        return EffectiveProfile(base.user_id, base.tenant_id, fields, base.revision, tuple(sorted(overrides)))

    def history(self, user_id: str) -> tuple[GovernedProfile, ...]:
        rows = self.con.execute("SELECT * FROM governed_profile_history WHERE user_id=? ORDER BY revision", (str(user_id),))
        return tuple(GovernedProfile(row["user_id"],row["tenant_id"],
                     {name:self._field(value) for name,value in json.loads(row["fields_json"]).items()},
                     int(row["revision"]),row["updated_at"]) for row in rows)

    def clear(self, conversation_id: str) -> None:
        self.con.execute("DELETE FROM governed_profile_overrides WHERE conversation_id=?", (str(conversation_id),))
        self.con.commit()

