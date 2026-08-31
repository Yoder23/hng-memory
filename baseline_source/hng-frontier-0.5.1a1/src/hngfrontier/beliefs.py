from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Iterable

from .governance import utc_now_iso


@dataclass(frozen=True, slots=True)
class BeliefRevision:
    belief_id: str
    revision: int
    statement: str
    confidence: float
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    reason: str = ""
    revised_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True, slots=True)
class Belief:
    belief_id: str
    statement: str
    confidence: float
    provenance_id: str
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    revision: int = 1
    created_at: str = field(default_factory=utc_now_iso)
    revised_at: str = field(default_factory=utc_now_iso)
    superseded_by: str | None = None
    invalidated_at: str | None = None


class BeliefStore:
    def __init__(self, connection):
        self.con = connection
        self.con.executescript("""
        CREATE TABLE IF NOT EXISTS beliefs(
          belief_id TEXT PRIMARY KEY,statement TEXT NOT NULL,confidence REAL NOT NULL,provenance_id TEXT NOT NULL,
          support_json TEXT NOT NULL,contradict_json TEXT NOT NULL,revision INTEGER NOT NULL,
          created_at TEXT NOT NULL,revised_at TEXT NOT NULL,superseded_by TEXT,invalidated_at TEXT);
        CREATE TABLE IF NOT EXISTS belief_revisions(
          belief_id TEXT NOT NULL,revision INTEGER NOT NULL,payload_json TEXT NOT NULL,revised_at TEXT NOT NULL,
          PRIMARY KEY(belief_id,revision));
        """)
        self.con.commit()

    @staticmethod
    def _validate_confidence(value: float) -> float:
        value = float(value)
        if not 0.0 <= value <= 1.0:
            raise ValueError("belief confidence must be in [0,1]")
        return value

    def create(self, belief: Belief) -> Belief:
        confidence = self._validate_confidence(belief.confidence)
        payload = BeliefRevision(belief.belief_id, 1, belief.statement, confidence,
                                 belief.supporting_evidence_ids, belief.contradicting_evidence_ids, "created", belief.created_at)
        self.con.execute("BEGIN IMMEDIATE")
        try:
            self.con.execute("INSERT INTO beliefs VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                belief.belief_id, belief.statement, confidence, belief.provenance_id,
                json.dumps(belief.supporting_evidence_ids), json.dumps(belief.contradicting_evidence_ids),
                1, belief.created_at, belief.revised_at, belief.superseded_by, belief.invalidated_at))
            self._append_revision(payload)
            self.con.commit()
        except Exception:
            self.con.rollback(); raise
        return self.get(belief.belief_id)  # type: ignore[return-value]

    def _append_revision(self, revision: BeliefRevision) -> None:
        self.con.execute("INSERT INTO belief_revisions VALUES(?,?,?,?)", (
            revision.belief_id, revision.revision,
            json.dumps({"belief_id": revision.belief_id, "revision": revision.revision,
                        "statement": revision.statement, "confidence": revision.confidence,
                        "supporting_evidence_ids": list(revision.supporting_evidence_ids),
                        "contradicting_evidence_ids": list(revision.contradicting_evidence_ids),
                        "reason": revision.reason, "revised_at": revision.revised_at}, sort_keys=True), revision.revised_at))

    def revise(self, belief_id: str, *, statement: str | None = None, confidence: float | None = None,
               supporting_evidence_ids: Iterable[str] | None = None,
               contradicting_evidence_ids: Iterable[str] | None = None, reason: str = "") -> Belief:
        old = self.get(belief_id)
        if old is None: raise KeyError(belief_id)
        revision = old.revision + 1; at = utc_now_iso()
        new_statement = old.statement if statement is None else str(statement)
        new_confidence = old.confidence if confidence is None else self._validate_confidence(confidence)
        support = old.supporting_evidence_ids if supporting_evidence_ids is None else tuple(dict.fromkeys(map(str, supporting_evidence_ids)))
        contradict = old.contradicting_evidence_ids if contradicting_evidence_ids is None else tuple(dict.fromkeys(map(str, contradicting_evidence_ids)))
        self.con.execute("BEGIN IMMEDIATE")
        try:
            self.con.execute("UPDATE beliefs SET statement=?,confidence=?,support_json=?,contradict_json=?,revision=?,revised_at=? WHERE belief_id=?",
                             (new_statement,new_confidence,json.dumps(support),json.dumps(contradict),revision,at,belief_id))
            self._append_revision(BeliefRevision(belief_id,revision,new_statement,new_confidence,support,contradict,reason,at))
            self.con.commit()
        except Exception:
            self.con.rollback(); raise
        return self.get(belief_id)  # type: ignore[return-value]

    def get(self, belief_id: str) -> Belief | None:
        row = self.con.execute("SELECT * FROM beliefs WHERE belief_id=?", (str(belief_id),)).fetchone()
        if row is None: return None
        return Belief(row["belief_id"],row["statement"],float(row["confidence"]),row["provenance_id"],
                      tuple(json.loads(row["support_json"])),tuple(json.loads(row["contradict_json"])),int(row["revision"]),
                      row["created_at"],row["revised_at"],row["superseded_by"],row["invalidated_at"])

    def history(self, belief_id: str) -> tuple[BeliefRevision, ...]:
        rows = self.con.execute("SELECT payload_json FROM belief_revisions WHERE belief_id=? ORDER BY revision", (str(belief_id),))
        return tuple(BeliefRevision(**json.loads(row[0])) for row in rows)

    def supersede(self, belief_id: str, new_belief_id: str) -> None:
        self.con.execute("UPDATE beliefs SET superseded_by=? WHERE belief_id=?", (new_belief_id,belief_id)); self.con.commit()

    def invalidate(self, belief_id: str) -> None:
        self.con.execute("UPDATE beliefs SET invalidated_at=COALESCE(invalidated_at,?) WHERE belief_id=?", (utc_now_iso(),belief_id)); self.con.commit()
