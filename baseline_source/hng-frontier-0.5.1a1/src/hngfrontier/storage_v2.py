from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import threading
from typing import Iterable, Protocol, runtime_checkable

from .governance import EvidenceKind, EvidenceProvenance, EvidenceRecordV2, TemporalValidity, utc_now_iso
from .semantic import SemanticState


@runtime_checkable
class EvidenceStore(Protocol):
    def append(self, record: EvidenceRecordV2) -> EvidenceRecordV2: ...
    def get(self, experience_id: str) -> EvidenceRecordV2 | None: ...
    def query_structured(self, *, tenant_id: str = "", user_id: str = "", scopes: tuple[str, ...] = ("private", "tenant", "global"), include_inactive: bool = False) -> tuple[EvidenceRecordV2, ...]: ...
    def supersede(self, old_ids: Iterable[str], new_id: str) -> None: ...
    def invalidate(self, experience_id: str, *, at: str | None = None) -> None: ...


class SQLiteEvidenceStore:
    """Transactional evidence truth. Retrieval indexes are disposable derived state."""

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=FULL")
        self.con.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS evidence(
              experience_id TEXT PRIMARY KEY,
              evidence_group_id TEXT NOT NULL,
              source_event_id TEXT NOT NULL,
              episode_id TEXT NOT NULL,
              conversation_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              content TEXT NOT NULL,
              semantics_json TEXT NOT NULL,
              provenance_json TEXT NOT NULL,
              source_type TEXT NOT NULL DEFAULT '',
              trust_score REAL NOT NULL DEFAULT 0.0,
              verified INTEGER NOT NULL DEFAULT 0,
              validity_json TEXT NOT NULL,
              environment_version TEXT NOT NULL DEFAULT '',
              policy_version TEXT NOT NULL DEFAULT '',
              outcome_score REAL NOT NULL,
              confidence REAL NOT NULL,
              tenant_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              scope TEXT NOT NULL,
              role TEXT NOT NULL,
              authority_level INTEGER,
              abstraction_level INTEGER,
              profile_revision INTEGER,
              supersedes_json TEXT NOT NULL,
              superseded_by TEXT,
              invalidated_at TEXT,
              metadata_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS evidence_access ON evidence(scope,tenant_id,user_id);
            CREATE INDEX IF NOT EXISTS evidence_group ON evidence(evidence_group_id,source_event_id);
            CREATE INDEX IF NOT EXISTS evidence_episode ON evidence(episode_id,conversation_id);
            CREATE INDEX IF NOT EXISTS evidence_active ON evidence(superseded_by,invalidated_at);
            CREATE TABLE IF NOT EXISTS working_state(
              conversation_id TEXT PRIMARY KEY,
              state_json TEXT NOT NULL,
              open_loops_json TEXT NOT NULL DEFAULT '[]',
              constraints_json TEXT NOT NULL DEFAULT '[]',
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            """
        )
        columns = {row[1] for row in self.con.execute("PRAGMA table_info(evidence)")}
        if "environment_version" not in columns:
            self.con.execute("ALTER TABLE evidence ADD COLUMN environment_version TEXT NOT NULL DEFAULT ''")
        if "policy_version" not in columns:
            self.con.execute("ALTER TABLE evidence ADD COLUMN policy_version TEXT NOT NULL DEFAULT ''")
        if "source_type" not in columns:
            self.con.execute("ALTER TABLE evidence ADD COLUMN source_type TEXT NOT NULL DEFAULT ''")
        if "trust_score" not in columns:
            self.con.execute("ALTER TABLE evidence ADD COLUMN trust_score REAL NOT NULL DEFAULT 0.0")
        if "verified" not in columns:
            self.con.execute("ALTER TABLE evidence ADD COLUMN verified INTEGER NOT NULL DEFAULT 0")
        self.con.execute("CREATE INDEX IF NOT EXISTS evidence_quality ON evidence(verified,trust_score,created_at)")
        self.con.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)", (str(self.SCHEMA_VERSION),))
        self.con.commit()

    @staticmethod
    def _record(row: sqlite3.Row) -> EvidenceRecordV2:
        provenance = json.loads(row["provenance_json"])
        validity = json.loads(row["validity_json"])
        return EvidenceRecordV2(
            experience_id=row["experience_id"], evidence_group_id=row["evidence_group_id"],
            source_event_id=row["source_event_id"], episode_id=row["episode_id"],
            conversation_id=row["conversation_id"], kind=EvidenceKind(row["kind"]), content=row["content"],
            semantics=SemanticState.from_storage(json.loads(row["semantics_json"])),
            provenance=EvidenceProvenance(**provenance), validity=TemporalValidity(**validity),
            outcome_score=float(row["outcome_score"]), confidence=float(row["confidence"]),
            tenant_id=row["tenant_id"], user_id=row["user_id"], scope=row["scope"], role=row["role"],
            authority_level=row["authority_level"], abstraction_level=row["abstraction_level"],
            profile_revision=row["profile_revision"], supersedes=tuple(json.loads(row["supersedes_json"])),
            superseded_by=row["superseded_by"], invalidated_at=row["invalidated_at"],
            metadata=json.loads(row["metadata_json"]), created_at=row["created_at"],
        )

    def append(self, record: EvidenceRecordV2) -> EvidenceRecordV2:
        values = (
            record.experience_id, record.evidence_group_id, record.source_event_id, record.episode_id,
            record.conversation_id, record.kind.value, record.content,
            json.dumps(record.semantics.as_storage(), sort_keys=True, separators=(",", ":")),
            json.dumps(record.provenance.as_dict(), sort_keys=True, separators=(",", ":")),
            record.provenance.source_type, record.provenance.trust_score, int(record.provenance.verified),
            json.dumps(record.validity.as_dict(), sort_keys=True, separators=(",", ":")),
            record.validity.environment_version, record.validity.policy_version,
            record.outcome_score, record.confidence, record.tenant_id, record.user_id, record.scope,
            record.role, record.authority_level, record.abstraction_level, record.profile_revision,
            json.dumps(list(record.supersedes)), record.superseded_by, record.invalidated_at,
            json.dumps(dict(record.metadata), sort_keys=True, separators=(",", ":")), record.created_at,
        )
        with self._lock:
            try:
                self.con.execute("BEGIN IMMEDIATE")
                self.con.execute(
                    """INSERT INTO evidence(
                    experience_id,evidence_group_id,source_event_id,episode_id,conversation_id,kind,content,
                    semantics_json,provenance_json,source_type,trust_score,verified,validity_json,environment_version,policy_version,
                    outcome_score,confidence,tenant_id,user_id,scope,role,authority_level,abstraction_level,
                    profile_revision,supersedes_json,superseded_by,invalidated_at,metadata_json,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
                if record.supersedes:
                    self.con.executemany(
                        "UPDATE evidence SET superseded_by=? WHERE experience_id=? AND superseded_by IS NULL",
                        [(record.experience_id, old_id) for old_id in record.supersedes],
                    )
                self.con.commit()
            except Exception:
                self.con.rollback()
                raise
        return record

    def get(self, experience_id: str) -> EvidenceRecordV2 | None:
        row = self.con.execute("SELECT * FROM evidence WHERE experience_id=?", (str(experience_id),)).fetchone()
        return None if row is None else self._record(row)

    def all(self) -> tuple[EvidenceRecordV2, ...]:
        return tuple(self._record(row) for row in self.con.execute("SELECT * FROM evidence ORDER BY created_at,experience_id"))

    def get_many(self, experience_ids: Iterable[str]) -> tuple[EvidenceRecordV2, ...]:
        ids = tuple(dict.fromkeys(str(value) for value in experience_ids))
        if not ids:
            return ()
        records: dict[str, EvidenceRecordV2] = {}
        for start in range(0, len(ids), 900):
            chunk = ids[start:start + 900]
            marks = ",".join("?" for _ in chunk)
            for row in self.con.execute(f"SELECT * FROM evidence WHERE experience_id IN ({marks})", chunk):
                record = self._record(row)
                records[record.experience_id] = record
        return tuple(records[value] for value in ids if value in records)

    def eligible_ids(self, *, tenant_id: str = "", user_id: str = "",
                     scopes: tuple[str, ...] = ("private", "tenant", "global"),
                     include_inactive: bool = False, environment_version: str = "",
                     policy_version: str = "") -> set[str]:
        visibility: list[str] = []
        args: list[object] = []
        if "global" in scopes:
            visibility.append("scope='global'")
        if "tenant" in scopes and tenant_id:
            visibility.append("(scope='tenant' AND tenant_id=?)")
            args.append(tenant_id)
        if "private" in scopes and user_id:
            visibility.append("(scope='private' AND user_id=? AND (tenant_id='' OR tenant_id=?))")
            args.extend((user_id, tenant_id))
        clauses = ["(" + " OR ".join(visibility or ["0"]) + ")"]
        if not include_inactive:
            clauses.append("superseded_by IS NULL AND invalidated_at IS NULL")
        if environment_version:
            clauses.append("(environment_version='' OR environment_version=?)")
            args.append(environment_version)
        if policy_version:
            clauses.append("(policy_version='' OR policy_version=?)")
            args.append(policy_version)
        rows = self.con.execute("SELECT experience_id FROM evidence WHERE " + " AND ".join(clauses), args)
        return {str(row[0]) for row in rows}

    def governance_priority_ids(self, *, tenant_id: str = "", user_id: str = "",
                                environment_version: str = "", policy_version: str = "",
                                include_inactive: bool = True, limit: int = 32) -> tuple[str, ...]:
        visibility = ["scope='global'"]
        args: list[object] = []
        if tenant_id:
            visibility.append("(scope='tenant' AND tenant_id=?)")
            args.append(tenant_id)
        if user_id:
            visibility.append("(scope='private' AND user_id=? AND (tenant_id='' OR tenant_id=?))")
            args.extend((user_id, tenant_id))
        clauses = ["(" + " OR ".join(visibility) + ")"]
        if not include_inactive:
            clauses.append("superseded_by IS NULL AND invalidated_at IS NULL")
        if environment_version:
            clauses.append("(environment_version='' OR environment_version=?)")
            args.append(environment_version)
        if policy_version:
            clauses.append("(policy_version='' OR policy_version=?)")
            args.append(policy_version)
        args.append(int(limit))
        rows = self.con.execute(
            "SELECT experience_id FROM evidence WHERE " + " AND ".join(clauses) +
            " ORDER BY verified DESC,trust_score DESC,created_at DESC LIMIT ?", args,
        )
        return tuple(str(row[0]) for row in rows)

    def query_structured(self, *, tenant_id: str = "", user_id: str = "",
                         scopes: tuple[str, ...] = ("private", "tenant", "global"),
                         include_inactive: bool = False) -> tuple[EvidenceRecordV2, ...]:
        ids = self.eligible_ids(tenant_id=tenant_id, user_id=user_id, scopes=scopes, include_inactive=include_inactive)
        return self.get_many(sorted(ids))

    def supersede(self, old_ids: Iterable[str], new_id: str) -> None:
        with self._lock:
            self.con.executemany(
                "UPDATE evidence SET superseded_by=? WHERE experience_id=? AND superseded_by IS NULL",
                [(str(new_id), str(old_id)) for old_id in old_ids],
            )
            self.con.commit()

    def invalidate(self, experience_id: str, *, at: str | None = None) -> None:
        with self._lock:
            self.con.execute(
                "UPDATE evidence SET invalidated_at=COALESCE(invalidated_at,?) WHERE experience_id=?",
                (at or utc_now_iso(), str(experience_id)),
            )
            self.con.commit()

    def put_working_state(self, conversation_id: str, state: SemanticState, *,
                          open_loops: tuple[str, ...] = (), constraints: tuple[str, ...] = ()) -> None:
        with self._lock:
            self.con.execute(
                """INSERT INTO working_state(conversation_id,state_json,open_loops_json,constraints_json,updated_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET
                   state_json=excluded.state_json,open_loops_json=excluded.open_loops_json,
                   constraints_json=excluded.constraints_json,updated_at=excluded.updated_at""",
                (str(conversation_id), json.dumps(state.as_storage()), json.dumps(open_loops), json.dumps(constraints), utc_now_iso()),
            )
            self.con.commit()

    def working_state(self, conversation_id: str) -> tuple[SemanticState, tuple[str, ...], tuple[str, ...]]:
        row = self.con.execute("SELECT * FROM working_state WHERE conversation_id=?", (str(conversation_id),)).fetchone()
        if row is None:
            return SemanticState(), (), ()
        return SemanticState.from_storage(json.loads(row["state_json"])), tuple(json.loads(row["open_loops_json"])), tuple(json.loads(row["constraints_json"]))

    def snapshot(self):
        return self.con

    def close(self) -> None:
        self.con.close()
