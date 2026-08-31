from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np


def _u64_hash(text: str) -> np.uint64:
    return np.frombuffer(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), dtype="<u8")[0]


@dataclass(frozen=True, slots=True)
class ExperienceRecord:
    slot: int
    timestamp_ns: int
    conversation_id: int
    episode_id: int
    tenant_id: str
    actor_user_id: str
    actor_role: str
    authority_level: int
    abstraction_level: int
    memory_scope: str
    perspective_version: int
    role: str
    record_type: str
    namespace: str
    importance: float
    deleted: bool
    head_mask: int
    source: str
    action: str
    outcome: str
    outcome_score: float
    extra: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class MemoryFilter:
    conversation_id: int | None = None
    episode_id: int | None = None
    role: str | None = None
    access_user_id: str | None = None
    access_tenant_id: str | None = None
    scopes: tuple[str, ...] = ()
    actor_role: str | None = None
    min_authority_level: int | None = None
    max_authority_level: int | None = None
    min_abstraction_level: int | None = None
    max_abstraction_level: int | None = None
    allow_unscoped_actor: bool = True
    record_type: str | None = None
    namespace: str | None = None
    min_importance: float | None = None
    include_deleted: bool = False
    tags_all: tuple[str, ...] = ()
    tags_any: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Relation:
    src_slot: int
    relation: str
    dst_slot: int
    weight: float = 1.0


class ExperienceStore:
    """Single authoritative relational store for experience, evidence and commit state."""

    SCHEMA_VERSION = 3

    def __init__(self, path: str | Path, *, hv_dim: int, heads: Iterable[str], space_id: str,
                 read_only: bool = False):
        self.path = str(path)
        self.hv_dim = int(hv_dim)
        self.heads = tuple(str(x) for x in heads)
        if not self.heads or len(set(self.heads)) != len(self.heads):
            raise ValueError("heads must be non-empty and unique")
        if len(self.heads) > 62:
            raise ValueError("HNG Frontier supports at most 62 heads")
        self.head_bits = {name: 1 << i for i, name in enumerate(self.heads)}
        self.space_id = str(space_id)
        self.read_only = bool(read_only)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        if self.read_only:
            self.con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False)
        else:
            self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        if not self.read_only:
            self._init_schema()
        self._validate_identity()
        self.cache = EligibilityCache(self)

    def _init_schema(self):
        c = self.con
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA temp_store=MEMORY")
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS memories(
              slot INTEGER PRIMARY KEY,
              timestamp_ns INTEGER NOT NULL,
              conversation_id INTEGER NOT NULL DEFAULT 0,
              episode_id INTEGER NOT NULL DEFAULT 0,
              tenant_id TEXT NOT NULL DEFAULT '',
              actor_user_id TEXT NOT NULL DEFAULT '',
              actor_role TEXT NOT NULL DEFAULT '',
              authority_level INTEGER NOT NULL DEFAULT -1,
              abstraction_level INTEGER NOT NULL DEFAULT -1,
              memory_scope TEXT NOT NULL DEFAULT 'global',
              perspective_version INTEGER NOT NULL DEFAULT 0,
              role TEXT NOT NULL DEFAULT '',
              record_type TEXT NOT NULL DEFAULT '',
              namespace TEXT NOT NULL DEFAULT '',
              namespace_hash BLOB NOT NULL,
              importance REAL NOT NULL DEFAULT 0.0,
              deleted INTEGER NOT NULL DEFAULT 0,
              head_mask INTEGER NOT NULL DEFAULT 0,
              source TEXT NOT NULL,
              action TEXT NOT NULL DEFAULT '',
              outcome TEXT NOT NULL DEFAULT '',
              outcome_score REAL NOT NULL DEFAULT 0.0,
              extra_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS tags(
              slot INTEGER NOT NULL,
              tag TEXT NOT NULL,
              PRIMARY KEY(slot, tag)
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS relations(
              src_slot INTEGER NOT NULL,
              relation TEXT NOT NULL,
              dst_slot INTEGER NOT NULL,
              weight REAL NOT NULL DEFAULT 1.0,
              PRIMARY KEY(src_slot, relation, dst_slot)
            ) WITHOUT ROWID;
            CREATE INDEX IF NOT EXISTS idx_mem_episode ON memories(episode_id, slot);
            CREATE INDEX IF NOT EXISTS idx_mem_conversation ON memories(conversation_id, slot);
            CREATE INDEX IF NOT EXISTS idx_mem_namespace ON memories(namespace_hash, slot);
            CREATE INDEX IF NOT EXISTS idx_rel_src ON relations(src_slot, relation);
            CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag, slot);
            """
        )
        # Forward-migrate alpha stores without rewriting semantic vector slabs.
        cols = {str(r[1]) for r in c.execute("PRAGMA table_info(memories)")}
        additions = {
            "tenant_id": "TEXT NOT NULL DEFAULT ''",
            "actor_user_id": "TEXT NOT NULL DEFAULT ''",
            "actor_role": "TEXT NOT NULL DEFAULT ''",
            "authority_level": "INTEGER NOT NULL DEFAULT -1",
            "abstraction_level": "INTEGER NOT NULL DEFAULT -1",
            "memory_scope": "TEXT NOT NULL DEFAULT 'global'",
            "perspective_version": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, ddl in additions.items():
            if name not in cols:
                c.execute(f"ALTER TABLE memories ADD COLUMN {name} {ddl}")
        # Perspective indexes should not tax the dominant unscoped/global write path.
        # Partial indexes contain only actor/scoped memories; ordinary HDC transitions
        # therefore retain the pre-perspective insertion cost while personalized queries
        # still have targeted relational indexes available.
        c.execute("DROP INDEX IF EXISTS idx_mem_actor")
        c.execute("DROP INDEX IF EXISTS idx_mem_scope")
        c.execute("""CREATE INDEX IF NOT EXISTS idx_mem_actor ON memories(tenant_id,actor_user_id,actor_role,slot)
                     WHERE tenant_id<>'' OR actor_user_id<>'' OR actor_role<>''""")
        c.execute("""CREATE INDEX IF NOT EXISTS idx_mem_scope ON memories(memory_scope,tenant_id,actor_user_id,slot)
                     WHERE memory_scope<>'global'""")
        defaults = {
            "schema_version": str(self.SCHEMA_VERSION),
            "hv_dim": str(self.hv_dim),
            "space_id": self.space_id,
            "heads": json.dumps(self.heads, separators=(",", ":")),
            "committed_count": "0",
            "metadata_epoch": "0",
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO meta(key,value) VALUES(?,?)", (k, v))
        c.execute("UPDATE meta SET value=? WHERE key='schema_version'", (str(self.SCHEMA_VERSION),))
        c.commit()

    def _validate_identity(self):
        vals = dict(self.con.execute("SELECT key,value FROM meta").fetchall())
        if not vals:
            return
        if int(vals.get("schema_version", self.SCHEMA_VERSION)) != self.SCHEMA_VERSION:
            raise ValueError("schema version mismatch")
        if int(vals.get("hv_dim", self.hv_dim)) != self.hv_dim:
            raise ValueError("hv_dim mismatch")
        if vals.get("space_id", self.space_id) != self.space_id:
            raise ValueError("space_id mismatch")
        stored_heads = tuple(json.loads(vals.get("heads", "[]")))
        if stored_heads and stored_heads != self.heads:
            raise ValueError(f"head configuration mismatch: {stored_heads} != {self.heads}")

    @property
    def committed_count(self) -> int:
        row = self.con.execute("SELECT value FROM meta WHERE key='committed_count'").fetchone()
        return int(row[0]) if row else 0

    @property
    def metadata_epoch(self) -> int:
        row = self.con.execute("SELECT value FROM meta WHERE key='metadata_epoch'").fetchone()
        return int(row[0]) if row else 0

    def set_synchronous(self, mode: str) -> None:
        mode = mode.upper()
        if mode not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
            raise ValueError("invalid SQLite synchronous mode")
        self.con.execute(f"PRAGMA synchronous={mode}")

    def begin_write(self) -> int:
        if self.read_only:
            raise PermissionError("read-only experience store")
        self._lock.acquire()
        try:
            self.con.execute("BEGIN IMMEDIATE")
            return self.committed_count
        except Exception:
            self._lock.release()
            raise

    def rollback_write(self) -> None:
        try:
            self.con.rollback()
        finally:
            self._lock.release()

    def commit_memory(self, slot: int, source: str, *, head_names: Iterable[str], timestamp_ns: int | None = None,
                      conversation_id: int = 0, episode_id: int = 0, role: str = "", record_type: str = "",
                      namespace: str = "", importance: float = 0.0, tags: Iterable[str] = (), action: str = "",
                      tenant_id: str = "", actor_user_id: str = "", actor_role: str = "",
                      authority_level: int = -1, abstraction_level: int = -1, memory_scope: str = "global",
                      perspective_version: int = 0,
                      outcome: str = "", outcome_score: float = 0.0, extra: Mapping[str, object] | None = None,
                      relations: Iterable[Relation] = ()) -> None:
        try:
            expected = self.committed_count
            if int(slot) != expected:
                raise ValueError(f"slot {slot} is not next committed slot {expected}")
            mask = 0
            for name in head_names:
                if name not in self.head_bits:
                    raise ValueError(f"unknown semantic head: {name}")
                mask |= self.head_bits[name]
            ts = time.time_ns() if timestamp_ns is None else int(timestamp_ns)
            nh = hashlib.blake2b(str(namespace).encode("utf-8"), digest_size=8).digest()
            actor_defaults = (not tenant_id and not actor_user_id and not actor_role and
                              int(authority_level) == -1 and int(abstraction_level) == -1 and
                              str(memory_scope) == "global" and int(perspective_version) == 0)
            if actor_defaults:
                # Preserve the 0.3.x hot insert shape when perspective is not active.
                # New actor columns have database defaults, so unpersonalized HDC agents
                # pay essentially no bind/serialization tax for the 0.5 feature set.
                self.con.execute(
                    """INSERT INTO memories(slot,timestamp_ns,conversation_id,episode_id,role,record_type,
                       namespace,namespace_hash,importance,deleted,head_mask,source,action,outcome,outcome_score,extra_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (int(slot), ts, int(conversation_id), int(episode_id), str(role), str(record_type), str(namespace), nh,
                     float(importance), 0, int(mask), str(source), str(action), str(outcome), float(outcome_score),
                     json.dumps(dict(extra or {}), sort_keys=True, separators=(",", ":"))),
                )
            else:
                self.con.execute(
                    """INSERT INTO memories(slot,timestamp_ns,conversation_id,episode_id,tenant_id,actor_user_id,actor_role,
                       authority_level,abstraction_level,memory_scope,perspective_version,role,record_type,
                       namespace,namespace_hash,importance,deleted,head_mask,source,action,outcome,outcome_score,extra_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (int(slot), ts, int(conversation_id), int(episode_id), str(tenant_id), str(actor_user_id), str(actor_role),
                     int(authority_level), int(abstraction_level), str(memory_scope), int(perspective_version),
                     str(role), str(record_type), str(namespace), nh, float(importance), 0, int(mask), str(source),
                     str(action), str(outcome), float(outcome_score),
                     json.dumps(dict(extra or {}), sort_keys=True, separators=(",", ":"))),
                )
            self.con.executemany("INSERT OR IGNORE INTO tags(slot,tag) VALUES(?,?)",
                                 [(int(slot), str(t)) for t in tags])
            self.con.executemany("INSERT OR REPLACE INTO relations(src_slot,relation,dst_slot,weight) VALUES(?,?,?,?)",
                                 [(int(r.src_slot), str(r.relation), int(r.dst_slot), float(r.weight)) for r in relations])
            self.con.execute("UPDATE meta SET value=? WHERE key='committed_count'", (str(int(slot) + 1),))
            self.con.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='metadata_epoch'")
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise
        finally:
            self._lock.release()
        self.cache.append_committed_values(
            int(slot), conversation_id=int(conversation_id), episode_id=int(episode_id),
            importance=float(importance), deleted=False, head_mask=int(mask), namespace=str(namespace),
            tenant_id=str(tenant_id), actor_user_id=str(actor_user_id), actor_role=str(actor_role),
            authority_level=int(authority_level), abstraction_level=int(abstraction_level),
            memory_scope=str(memory_scope), role=str(role), record_type=str(record_type),
        )

    def get(self, slot: int) -> ExperienceRecord | None:
        r = self.con.execute("SELECT * FROM memories WHERE slot=?", (int(slot),)).fetchone()
        if r is None:
            return None
        return ExperienceRecord(
            slot=int(r["slot"]), timestamp_ns=int(r["timestamp_ns"]), conversation_id=int(r["conversation_id"]),
            episode_id=int(r["episode_id"]), tenant_id=str(r["tenant_id"]), actor_user_id=str(r["actor_user_id"]),
            actor_role=str(r["actor_role"]), authority_level=int(r["authority_level"]),
            abstraction_level=int(r["abstraction_level"]), memory_scope=str(r["memory_scope"]),
            perspective_version=int(r["perspective_version"]), role=str(r["role"]), record_type=str(r["record_type"]),
            namespace=str(r["namespace"]), importance=float(r["importance"]), deleted=bool(r["deleted"]),
            head_mask=int(r["head_mask"]), source=str(r["source"]), action=str(r["action"]),
            outcome=str(r["outcome"]), outcome_score=float(r["outcome_score"]),
            extra=json.loads(r["extra_json"] or "{}"),
        )

    def get_many(self, slots: Iterable[int]) -> list[ExperienceRecord]:
        slots = [int(s) for s in slots]
        if not slots:
            return []
        out: dict[int, ExperienceRecord] = {}
        for start in range(0, len(slots), 900):
            chunk = slots[start:start + 900]
            q = ",".join("?" for _ in chunk)
            for r in self.con.execute(f"SELECT * FROM memories WHERE slot IN ({q})", chunk):
                rec = ExperienceRecord(
                    slot=int(r["slot"]), timestamp_ns=int(r["timestamp_ns"]), conversation_id=int(r["conversation_id"]),
                    episode_id=int(r["episode_id"]), tenant_id=str(r["tenant_id"]), actor_user_id=str(r["actor_user_id"]),
                    actor_role=str(r["actor_role"]), authority_level=int(r["authority_level"]),
                    abstraction_level=int(r["abstraction_level"]), memory_scope=str(r["memory_scope"]),
                    perspective_version=int(r["perspective_version"]), role=str(r["role"]), record_type=str(r["record_type"]),
                    namespace=str(r["namespace"]), importance=float(r["importance"]), deleted=bool(r["deleted"]),
                    head_mask=int(r["head_mask"]), source=str(r["source"]), action=str(r["action"]),
                    outcome=str(r["outcome"]), outcome_score=float(r["outcome_score"]),
                    extra=json.loads(r["extra_json"] or "{}"),
                )
                out[rec.slot] = rec
        return [out[s] for s in slots if s in out]

    def episode(self, episode_id: int, *, conversation_id: int | None = None,
                include_deleted: bool = False) -> list[ExperienceRecord]:
        """Return one episode, optionally scoped to its conversation.

        Assistant-facing episode reconstruction should pass ``conversation_id`` because
        episode numbers are commonly local to a chat/session.  Leaving it unset preserves
        the lower-level ability to inspect the same episode identifier across conversations.
        """
        sql = "SELECT slot FROM memories WHERE episode_id=?"
        args: list[object] = [int(episode_id)]
        if conversation_id is not None:
            sql += " AND conversation_id=?"
            args.append(int(conversation_id))
        if not include_deleted:
            sql += " AND deleted=0"
        sql += " ORDER BY slot"
        return self.get_many(int(r[0]) for r in self.con.execute(sql, args))

    def outgoing(self, slot: int, relation: str | None = None) -> list[tuple[str, ExperienceRecord, float]]:
        if relation is None:
            rows = self.con.execute("SELECT relation,dst_slot,weight FROM relations WHERE src_slot=? ORDER BY relation,dst_slot",
                                    (int(slot),)).fetchall()
        else:
            rows = self.con.execute("SELECT relation,dst_slot,weight FROM relations WHERE src_slot=? AND relation=? ORDER BY dst_slot",
                                    (int(slot), str(relation))).fetchall()
        out = []
        for row in rows:
            rec = self.get(int(row["dst_slot"]))
            if rec is not None and not rec.deleted:
                out.append((str(row["relation"]), rec, float(row["weight"])))
        return out

    def head_slots(self, head: str) -> np.ndarray:
        bit = self.head_bits[head]
        rows = self.con.execute("SELECT slot FROM memories WHERE (head_mask & ?) != 0 ORDER BY slot", (int(bit),)).fetchall()
        return np.fromiter((int(r[0]) for r in rows), dtype=np.intp, count=len(rows))

    def sync(self) -> None:
        if self.read_only:
            return
        self.con.commit()
        self.con.execute("PRAGMA wal_checkpoint(FULL)")

    def close(self):
        self.con.close()


class EligibilityCache:
    def __init__(self, store: ExperienceStore):
        self.store = store
        self.epoch = -1
        self.count = 0
        self.capacity = 0
        self.conversation_id = np.empty(0, np.int64)
        self.episode_id = np.empty(0, np.int64)
        self.importance = np.empty(0, np.float32)
        self.deleted = np.empty(0, bool)
        self.head_mask = np.empty(0, np.int64)
        self.namespace_hash = np.empty(0, np.uint64)
        self._tenant_codes: dict[str, int] = {}
        self._actor_user_codes: dict[str, int] = {}
        self.tenant_code = np.empty(0, np.int32)
        self.actor_user_code = np.empty(0, np.int32)
        self.authority_level = np.empty(0, np.int8)
        self.abstraction_level = np.empty(0, np.int8)
        self._scope_codes: dict[str, int] = {}
        self.memory_scope = np.empty(0, np.int8)
        self._actor_role_codes: dict[str, int] = {}
        self.actor_role = np.empty(0, np.int16)
        self._role_codes: dict[str, int] = {}
        self._type_codes: dict[str, int] = {}
        self.role = np.empty(0, np.int16)
        self.record_type = np.empty(0, np.int16)
        self._tag_cache: dict[str, np.ndarray] = {}
        self.refresh(force=True)

    def _ensure(self, n: int):
        if n <= self.capacity:
            return
        cap = max(16, self.capacity or 0)
        while cap < n:
            cap *= 2
        def grow(old, dtype):
            out = np.empty(cap, dtype=dtype)
            if self.count:
                out[:self.count] = old[:self.count]
            return out
        self.conversation_id = grow(self.conversation_id, np.int64)
        self.episode_id = grow(self.episode_id, np.int64)
        self.importance = grow(self.importance, np.float32)
        self.deleted = grow(self.deleted, bool)
        self.head_mask = grow(self.head_mask, np.int64)
        self.namespace_hash = grow(self.namespace_hash, np.uint64)
        self.tenant_code = grow(self.tenant_code, np.int32)
        self.actor_user_code = grow(self.actor_user_code, np.int32)
        self.authority_level = grow(self.authority_level, np.int8)
        self.abstraction_level = grow(self.abstraction_level, np.int8)
        self.memory_scope = grow(self.memory_scope, np.int8)
        self.actor_role = grow(self.actor_role, np.int16)
        self.role = grow(self.role, np.int16)
        self.record_type = grow(self.record_type, np.int16)
        self.capacity = cap

    def _code(self, mapping: dict[str, int], text: str) -> int:
        if text not in mapping:
            mapping[text] = len(mapping) + 1
        return mapping[text]

    def _set_row(self, i: int, r):
        self.conversation_id[i] = int(r["conversation_id"])
        self.episode_id[i] = int(r["episode_id"])
        self.importance[i] = float(r["importance"])
        self.deleted[i] = bool(r["deleted"])
        self.head_mask[i] = int(r["head_mask"])
        self.namespace_hash[i] = _u64_hash(str(r["namespace"]))
        self.tenant_code[i] = self._code(self._tenant_codes, str(r["tenant_id"]))
        self.actor_user_code[i] = self._code(self._actor_user_codes, str(r["actor_user_id"]))
        self.authority_level[i] = int(r["authority_level"])
        self.abstraction_level[i] = int(r["abstraction_level"])
        self.memory_scope[i] = self._code(self._scope_codes, str(r["memory_scope"]))
        self.actor_role[i] = self._code(self._actor_role_codes, str(r["actor_role"]))
        self.role[i] = self._code(self._role_codes, str(r["role"]))
        self.record_type[i] = self._code(self._type_codes, str(r["record_type"]))

    def refresh(self, *, force: bool = False):
        epoch = self.store.metadata_epoch
        count = self.store.committed_count
        if not force and epoch == self.epoch and count == self.count:
            return
        rows = self.store.con.execute("SELECT slot,conversation_id,episode_id,importance,deleted,head_mask,namespace,tenant_id,actor_user_id,actor_role,authority_level,abstraction_level,memory_scope,role,record_type FROM memories ORDER BY slot").fetchall()
        self.count = 0
        self._ensure(len(rows))
        for r in rows:
            i = int(r["slot"])
            if i != self.count:
                raise ValueError("Frontier v0.2 requires dense global slots")
            self._set_row(i, r)
            self.count += 1
        self.epoch = epoch
        self._tag_cache.clear()

    def append_committed(self, slot: int):
        if slot != self.count:
            self.refresh(force=True)
            return
        self._ensure(slot + 1)
        r = self.store.con.execute("SELECT slot,conversation_id,episode_id,importance,deleted,head_mask,namespace,tenant_id,actor_user_id,actor_role,authority_level,abstraction_level,memory_scope,role,record_type FROM memories WHERE slot=?", (slot,)).fetchone()
        self._set_row(slot, r)
        self.count += 1
        self.epoch = self.store.metadata_epoch
        self._tag_cache.clear()

    def append_committed_values(self, slot: int, *, conversation_id: int, episode_id: int, importance: float,
                                deleted: bool, head_mask: int, namespace: str, tenant_id: str = "",
                                actor_user_id: str = "", actor_role: str = "", authority_level: int = -1,
                                abstraction_level: int = -1, memory_scope: str = "global", role: str = "",
                                record_type: str = "") -> None:
        """Append the just-committed row to the hot eligibility cache without re-reading SQLite.

        The writer already owns every field at commit time. Avoiding the post-commit SELECT
        recovers the pre-perspective write path while keeping the cache immediately coherent.
        """
        if int(slot) != self.count:
            self.refresh(force=True)
            return
        self._ensure(int(slot) + 1)
        i = int(slot)
        self.conversation_id[i] = int(conversation_id)
        self.episode_id[i] = int(episode_id)
        self.importance[i] = float(importance)
        self.deleted[i] = bool(deleted)
        self.head_mask[i] = int(head_mask)
        self.namespace_hash[i] = _u64_hash(str(namespace))
        if (not tenant_id and not actor_user_id and not actor_role and int(authority_level) < 0 and
                int(abstraction_level) < 0 and str(memory_scope) == "global"):
            # Unscoped/global is the dominant path for assistants not using perspective.
            # Seed/reuse the four canonical codes without repeated mapping lookups.
            tc = self._tenant_codes.setdefault("", len(self._tenant_codes) + 1)
            uc = self._actor_user_codes.setdefault("", len(self._actor_user_codes) + 1)
            sc = self._scope_codes.setdefault("global", len(self._scope_codes) + 1)
            rc = self._actor_role_codes.setdefault("", len(self._actor_role_codes) + 1)
            self.tenant_code[i] = tc
            self.actor_user_code[i] = uc
            self.authority_level[i] = -1
            self.abstraction_level[i] = -1
            self.memory_scope[i] = sc
            self.actor_role[i] = rc
        else:
            self.tenant_code[i] = self._code(self._tenant_codes, str(tenant_id))
            self.actor_user_code[i] = self._code(self._actor_user_codes, str(actor_user_id))
            self.authority_level[i] = int(authority_level)
            self.abstraction_level[i] = int(abstraction_level)
            self.memory_scope[i] = self._code(self._scope_codes, str(memory_scope))
            self.actor_role[i] = self._code(self._actor_role_codes, str(actor_role))
        self.role[i] = self._code(self._role_codes, str(role))
        self.record_type[i] = self._code(self._type_codes, str(record_type))
        self.count += 1
        # commit_memory increments metadata_epoch exactly once for every accepted row.
        self.epoch = max(0, int(self.epoch)) + 1
        self._tag_cache.clear()

    def _tag_mask(self, tag: str) -> np.ndarray:
        self.refresh()
        cached = self._tag_cache.get(tag)
        if cached is not None and cached.size == self.count:
            return cached
        out = np.zeros(self.count, dtype=bool)
        for r in self.store.con.execute("SELECT slot FROM tags WHERE tag=?", (str(tag),)):
            i = int(r[0])
            if 0 <= i < self.count:
                out[i] = True
        self._tag_cache[tag] = out
        return out

    def mask(self, slots: np.ndarray, f: MemoryFilter | None = None, *, require_head: str | None = None) -> np.ndarray:
        self.refresh()
        slots = np.asarray(slots, dtype=np.intp)
        if slots.size == 0:
            return np.empty(0, dtype=bool)
        if np.any(slots < 0) or np.any(slots >= self.count):
            raise IndexError("candidate outside committed prefix")
        m = np.ones(slots.size, dtype=bool)
        if require_head is not None:
            m &= (self.head_mask[slots] & self.store.head_bits[require_head]) != 0
        if f is None:
            return m & ~self.deleted[slots]
        if not f.include_deleted:
            m &= ~self.deleted[slots]
        if f.conversation_id is not None:
            m &= self.conversation_id[slots] == int(f.conversation_id)
        if f.episode_id is not None:
            m &= self.episode_id[slots] == int(f.episode_id)
        if f.scopes:
            allowed_scope_codes = {self._scope_codes.get(str(x), -9999) for x in f.scopes}
            sm = np.zeros(slots.size, dtype=bool)
            for code in allowed_scope_codes:
                sm |= self.memory_scope[slots] == code
            m &= sm
        if f.access_user_id is not None or f.access_tenant_id is not None:
            global_code = self._scope_codes.get("global", -9999)
            tenant_code = self._scope_codes.get("tenant", -9999)
            private_code = self._scope_codes.get("private", -9999)
            scope = self.memory_scope[slots]
            vis = scope == global_code
            if f.access_tenant_id is not None:
                th = self._tenant_codes.get(str(f.access_tenant_id), -9999)
                vis |= (scope == tenant_code) & (self.tenant_code[slots] == th)
                if f.access_user_id is not None:
                    uh = self._actor_user_codes.get(str(f.access_user_id), -9999)
                    vis |= (scope == private_code) & (self.tenant_code[slots] == th) & (self.actor_user_code[slots] == uh)
            elif f.access_user_id is not None:
                uh = self._actor_user_codes.get(str(f.access_user_id), -9999)
                vis |= (scope == private_code) & (self.actor_user_code[slots] == uh)
            m &= vis
        actor_unscoped = self.actor_role[slots] == self._actor_role_codes.get("", -9999)
        if f.actor_role is not None:
            code = self._actor_role_codes.get(str(f.actor_role), -9999)
            rm = self.actor_role[slots] == code
            if f.allow_unscoped_actor:
                rm |= actor_unscoped
            m &= rm
        authority_unscoped = self.authority_level[slots] < 0
        if f.min_authority_level is not None:
            am = self.authority_level[slots] >= int(f.min_authority_level)
            if f.allow_unscoped_actor:
                am |= authority_unscoped
            m &= am
        if f.max_authority_level is not None:
            am = self.authority_level[slots] <= int(f.max_authority_level)
            if f.allow_unscoped_actor:
                am |= authority_unscoped
            m &= am
        abstraction_unscoped = self.abstraction_level[slots] < 0
        if f.min_abstraction_level is not None:
            ab = self.abstraction_level[slots] >= int(f.min_abstraction_level)
            if f.allow_unscoped_actor:
                ab |= abstraction_unscoped
            m &= ab
        if f.max_abstraction_level is not None:
            ab = self.abstraction_level[slots] <= int(f.max_abstraction_level)
            if f.allow_unscoped_actor:
                ab |= abstraction_unscoped
            m &= ab
        if f.min_importance is not None:
            m &= self.importance[slots] >= float(f.min_importance)
        if f.namespace is not None:
            m &= self.namespace_hash[slots] == _u64_hash(f.namespace)
        if f.role is not None:
            code = self._role_codes.get(f.role, -1); m &= self.role[slots] == code
        if f.record_type is not None:
            code = self._type_codes.get(f.record_type, -1); m &= self.record_type[slots] == code
        for tag in f.tags_all:
            m &= self._tag_mask(tag)[slots]
        if f.tags_any:
            anym = np.zeros(slots.size, dtype=bool)
            for tag in f.tags_any:
                anym |= self._tag_mask(tag)[slots]
            m &= anym
        return m
