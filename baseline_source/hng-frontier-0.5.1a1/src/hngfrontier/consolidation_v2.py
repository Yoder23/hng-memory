from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json

from .consolidation import EvidenceConsolidator
from .governance import EvidenceRecordV2, utc_now_iso


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    retain_days: int = 365
    expire_unverified_days: int = 90
    authoritative_exempt: bool = True
    safety_kinds: tuple[str, ...] = ("constraint", "system_event")


class PersistedConsolidator:
    """Persists reversible patterns and forgetting eligibility; raw evidence is never deleted."""

    def __init__(self, connection, policy: RetentionPolicy | None = None):
        self.con = connection; self.policy = policy or RetentionPolicy(); self.builder = EvidenceConsolidator()
        self.con.executescript("""
        CREATE TABLE IF NOT EXISTS consolidated_patterns(
          pattern_id TEXT PRIMARY KEY,evidence_group_id TEXT NOT NULL,payload_json TEXT NOT NULL,
          source_groups_json TEXT NOT NULL,created_at TEXT NOT NULL,invalidated_at TEXT);
        CREATE TABLE IF NOT EXISTS evidence_retention(
          experience_id TEXT PRIMARY KEY,status TEXT NOT NULL,reason TEXT NOT NULL,evaluated_at TEXT NOT NULL);
        """); self.con.commit()

    def consolidate(self, records: tuple[EvidenceRecordV2, ...]) -> tuple[str, ...]:
        ids = []
        for pattern in self.builder.consolidate(records):
            source_groups = sorted({record.evidence_group_id for record in records
                                    if record.experience_id in pattern.source_experience_ids})
            self.con.execute("""INSERT INTO consolidated_patterns VALUES(?,?,?,?,?,NULL)
                ON CONFLICT(pattern_id) DO UPDATE SET payload_json=excluded.payload_json,
                source_groups_json=excluded.source_groups_json""",
                (pattern.pattern_id,pattern.evidence_group_id,json.dumps(pattern.as_dict(),sort_keys=True),
                 json.dumps(source_groups),utc_now_iso())); ids.append(pattern.pattern_id)
        self.con.commit(); return tuple(ids)

    def evaluate_retention(self, records: tuple[EvidenceRecordV2, ...], *, now: datetime | None = None) -> dict[str, str]:
        now = now or datetime.now(timezone.utc); decisions = {}
        for record in records:
            created = datetime.fromisoformat(record.created_at)
            authoritative = record.provenance.verified and record.provenance.source_type in {
                "system_telemetry", "authoritative_database", "human_confirmed"}
            safety = record.kind.value in self.policy.safety_kinds
            if self.policy.authoritative_exempt and (authoritative or safety):
                status, reason = "retained", "authoritative_or_safety_exempt"
            else:
                days = self.policy.expire_unverified_days if not record.provenance.verified else self.policy.retain_days
                eligible = created + timedelta(days=days) < now
                status, reason = ("forgetting_eligible", f"older_than_{days}_days") if eligible else ("retained", "within_retention")
            self.con.execute("""INSERT INTO evidence_retention VALUES(?,?,?,?)
                ON CONFLICT(experience_id) DO UPDATE SET status=excluded.status,reason=excluded.reason,
                evaluated_at=excluded.evaluated_at""", (record.experience_id,status,reason,utc_now_iso()))
            decisions[record.experience_id] = status
        self.con.commit(); return decisions

    def pattern(self, pattern_id: str) -> dict[str, object] | None:
        row = self.con.execute("SELECT payload_json FROM consolidated_patterns WHERE pattern_id=? AND invalidated_at IS NULL",
                               (pattern_id,)).fetchone()
        return None if row is None else json.loads(row[0])

    def invalidate_pattern(self, pattern_id: str) -> None:
        self.con.execute("UPDATE consolidated_patterns SET invalidated_at=? WHERE pattern_id=?", (utc_now_iso(),pattern_id)); self.con.commit()
