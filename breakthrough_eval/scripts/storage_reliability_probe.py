#!/usr/bin/env python3
"""Bounded production SQLite evidence-store write/restart/backup probe.

This is not an hours-long soak. It preserves the database, measures every append,
reopens at deterministic checkpoints, verifies tenant isolation, applies lifecycle
mutations, and compares a full logical ledger after SQLite backup/restore.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(PACKAGE))

from hngfrontier.governance import (  # noqa: E402
    EvidenceKind,
    EvidenceProvenance,
    EvidenceRecordV2,
    TemporalValidity,
)
from hngfrontier.semantic import SemanticState, SemanticValue  # noqa: E402
from hngfrontier.storage_v2 import SQLiteEvidenceStore  # noqa: E402


SEED = 20260831
CREATED_AT = "2026-08-31T12:00:00+00:00"


def percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def stable_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record(index: int, tenants: int) -> EvidenceRecordV2:
    tenant = f"tenant-{index % tenants:03d}"
    identifier = f"probe-{index:08d}"
    return EvidenceRecordV2(
        experience_id=identifier,
        evidence_group_id=f"event-{index:08d}",
        source_event_id=f"event-{index:08d}",
        episode_id=f"episode-{index // 10:08d}",
        conversation_id=f"conversation-{index // 100:08d}",
        kind=EvidenceKind.OBSERVATION,
        content=f"bounded reliability observation {index}",
        semantics=SemanticState({
            "state": SemanticValue.structured(f"state-{index % 17}"),
            "sequence": SemanticValue.structured(index),
        }),
        provenance=EvidenceProvenance(
            "system_telemetry",
            f"probe:{identifier}",
            1.0,
            True,
            CREATED_AT,
            "probe",
            verifier="storage-reliability-probe",
            verification_status="verified",
            identity="local-probe",
        ),
        validity=TemporalValidity(valid_from="2026-01-01T00:00:00+00:00"),
        outcome_score=0.0,
        confidence=1.0,
        tenant_id=tenant,
        user_id=f"user-{index % tenants:03d}",
        scope="tenant",
        metadata={"probe_seed": SEED, "ordinal": index},
        created_at=CREATED_AT,
    )


def logical_record(item: EvidenceRecordV2) -> dict[str, object]:
    return {
        "experience_id": item.experience_id,
        "group": item.evidence_group_id,
        "event": item.source_event_id,
        "episode": item.episode_id,
        "conversation": item.conversation_id,
        "kind": item.kind.value,
        "content": item.content,
        "semantics": item.semantics.as_storage(),
        "provenance": item.provenance.as_dict(),
        "validity": item.validity.as_dict(),
        "outcome": item.outcome_score,
        "confidence": item.confidence,
        "tenant": item.tenant_id,
        "user": item.user_id,
        "scope": item.scope,
        "superseded_by": item.superseded_by,
        "invalidated_at": item.invalidated_at,
        "metadata": dict(item.metadata),
        "created_at": item.created_at,
    }


def ledger(store: SQLiteEvidenceStore) -> tuple[int, str]:
    records = store.all()
    return len(records), stable_hash([logical_record(item) for item in records])


def write_result(path: Path, result: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, object]:
    database = args.database.resolve()
    backup = args.backup.resolve()
    if database.exists() or backup.exists():
        raise FileExistsError(
            "Refusing to overwrite preserved probe database/backup; select unused --database and --backup paths."
        )
    database.parent.mkdir(parents=True, exist_ok=True)
    backup.parent.mkdir(parents=True, exist_ok=True)
    append_ms: list[float] = []
    restart_checks = []
    store = SQLiteEvidenceStore(database)
    started = time.perf_counter()
    try:
        for index in range(args.records):
            phase = time.perf_counter()
            store.append(record(index, args.tenants))
            append_ms.append((time.perf_counter() - phase) * 1000.0)
            if (index + 1) % args.restart_every == 0 and index + 1 < args.records:
                expected_generation = index + 1
                store.close()
                reopen_started = time.perf_counter()
                store = SQLiteEvidenceStore(database)
                reopen_ms = (time.perf_counter() - reopen_started) * 1000.0
                sentinel = store.get(f"probe-{index:08d}")
                check = {
                    "records_written": index + 1,
                    "generation": store.generation(),
                    "expected_generation": expected_generation,
                    "sentinel_present": sentinel is not None,
                    "reopen_ms": reopen_ms,
                }
                check["passed"] = check["generation"] == expected_generation and check["sentinel_present"]
                restart_checks.append(check)

        # Two committed lifecycle transactions after all appends.
        superseded_ids = [f"probe-{index:08d}" for index in range(args.lifecycle_records)]
        replacement = f"probe-{args.lifecycle_records:08d}"
        store.supersede(superseded_ids, replacement)
        invalidated_ids = [
            f"probe-{index:08d}"
            for index in range(args.lifecycle_records, args.lifecycle_records * 2)
        ]
        for identifier in invalidated_ids:
            store.invalidate(identifier, at="2026-08-31T12:30:00+00:00")

        tenant_counts = {}
        expected_per_tenant = args.records // args.tenants
        for tenant_index in range(args.tenants):
            tenant = f"tenant-{tenant_index:03d}"
            ids = store.eligible_ids(tenant_id=tenant, scopes=("tenant",), include_inactive=True)
            tenant_counts[tenant] = len(ids)
        tenant_isolation_passed = (
            args.records % args.tenants == 0
            and all(value == expected_per_tenant for value in tenant_counts.values())
            and sum(tenant_counts.values()) == args.records
        )

        before_count, before_hash = ledger(store)
        generation_before_backup = store.generation()
        backup_connection = sqlite3.connect(backup)
        try:
            store.snapshot().backup(backup_connection)
        finally:
            backup_connection.close()
        store.close()

        restored = SQLiteEvidenceStore(backup)
        try:
            after_count, after_hash = ledger(restored)
            restored_generation = restored.generation()
            lifecycle_passed = all(
                restored.get(identifier) is not None
                and restored.get(identifier).superseded_by == replacement
                for identifier in superseded_ids
            ) and all(
                restored.get(identifier) is not None
                and restored.get(identifier).invalidated_at == "2026-08-31T12:30:00+00:00"
                for identifier in invalidated_ids
            )
        finally:
            restored.close()
    except Exception:
        try:
            store.close()
        except Exception:
            pass
        raise

    elapsed = time.perf_counter() - started
    all_passed = (
        before_count == args.records
        and after_count == before_count
        and after_hash == before_hash
        and restored_generation == generation_before_backup
        and tenant_isolation_passed
        and lifecycle_passed
        and all(bool(check["passed"]) for check in restart_checks)
    )
    return {
        "schema_version": 1,
        "benchmark": "bounded_sqlite_evidence_store_reliability_probe",
        "status": "PASS" if all_passed else "FAIL",
        "claim_boundary": "bounded local probe, not an hours/days production soak",
        "command": [sys.executable, *sys.argv],
        "seed": SEED,
        "config": {
            "records": args.records,
            "tenants": args.tenants,
            "restart_every": args.restart_every,
            "lifecycle_records": args.lifecycle_records,
            "journal_mode": "WAL",
            "synchronous": "FULL",
        },
        "duration_seconds": elapsed,
        "append_latency_ms": {
            "p50": percentile(append_ms, 0.50),
            "p95": percentile(append_ms, 0.95),
            "p99": percentile(append_ms, 0.99),
            "mean": statistics.mean(append_ms),
            "stdev": statistics.pstdev(append_ms),
        },
        "restart_checks": restart_checks,
        "tenant_counts": tenant_counts,
        "tenant_isolation_passed": tenant_isolation_passed,
        "lifecycle_passed": lifecycle_passed,
        "generation_before_backup": generation_before_backup,
        "restored_generation": restored_generation,
        "ledger": {
            "before_count": before_count,
            "after_count": after_count,
            "before_sha256": before_hash,
            "after_sha256": after_hash,
            "identical": before_count == after_count and before_hash == after_hash,
        },
        "database_bytes": database.stat().st_size,
        "backup_bytes": backup.stat().st_size,
        "database": str(database.relative_to(ROOT)).replace("\\", "/"),
        "backup": str(backup.relative_to(ROOT)).replace("\\", "/"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=10_000)
    parser.add_argument("--tenants", type=int, default=10)
    parser.add_argument("--restart-every", type=int, default=1_000)
    parser.add_argument("--lifecycle-records", type=int, default=10)
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / "breakthrough_eval" / "reliability" / "run_data" / "storage_probe.sqlite",
    )
    parser.add_argument(
        "--backup",
        type=Path,
        default=ROOT / "breakthrough_eval" / "reliability" / "run_data" / "storage_probe_backup.sqlite",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "breakthrough_eval" / "reliability" / "STORAGE_PROBE.json",
    )
    args = parser.parse_args()
    if args.records <= 0 or args.tenants <= 0 or args.restart_every <= 0:
        parser.error("records, tenants, and restart-every must be positive")
    if args.records % args.tenants:
        parser.error("records must be divisible by tenants for exact isolation accounting")
    if args.lifecycle_records <= 0 or args.lifecycle_records * 2 >= args.records:
        parser.error("lifecycle-records must be positive and leave ordinary records")
    return args


def main() -> int:
    args = parse_args()
    try:
        result = run(args)
    except Exception as exc:
        result = {
            "schema_version": 1,
            "benchmark": "bounded_sqlite_evidence_store_reliability_probe",
            "status": "ERROR",
            "error": f"{type(exc).__name__}: {exc}",
            "command": [sys.executable, *sys.argv],
        }
        write_result(args.output, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    write_result(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
