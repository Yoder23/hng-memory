#!/usr/bin/env python3
"""Scaled private-memory isolation probe for the production SQLite evidence store.

The probe creates one private record for every (tenant, local-user) principal while
making the semantic state identical across all principals. It exhaustively checks
the scoped query path, exercises role/authority eligibility, overlaps readers with
writes, restarts the store, and verifies a logical backup ledger.

This is a storage/policy probe, not an authentication or authorization-system test.
The store's get/get_many methods are privileged raw primitives and are deliberately
reported as outside the scoped-query guarantee.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import random
import sqlite3
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(PACKAGE))

from hngfrontier.actor_policy import ActorPolicy, ProfileApplicability  # noqa: E402
from hngfrontier.governance import (  # noqa: E402
    EvidenceKind,
    EvidenceProvenance,
    EvidenceRecordV2,
    TemporalValidity,
)
from hngfrontier.profiles import EffectiveProfile, PerspectiveField  # noqa: E402
from hngfrontier.semantic import SemanticState, SemanticValue  # noqa: E402
from hngfrontier.storage_v2 import SQLiteEvidenceStore  # noqa: E402


SEED = 20260901
CREATED_AT = "2026-09-01T12:00:00+00:00"
ROLES = ("novice", "specialist", "senior_ic", "manager", "executive")
ROLE_AUTHORITY = {role: index + 1 for index, role in enumerate(ROLES)}


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def distribution(values: Sequence[float]) -> dict[str, float]:
    return {
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "mean": statistics.mean(values) if values else 0.0,
        "stdev": statistics.pstdev(values) if values else 0.0,
    }


def stable_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def principal(index: int, tenants: int) -> tuple[str, str, str]:
    tenant_index = index % tenants
    local_user_index = index // tenants
    return (
        f"tenant-{tenant_index:06d}",
        f"user-{local_user_index:06d}",
        ROLES[local_user_index % len(ROLES)],
    )


def identity_record(index: int, tenants: int) -> EvidenceRecordV2:
    tenant_id, user_id, role = principal(index, tenants)
    identifier = f"identity-{index:08d}"
    return EvidenceRecordV2(
        experience_id=identifier,
        evidence_group_id=f"principal-{index:08d}",
        source_event_id=f"principal-{index:08d}",
        episode_id="identical-episode",
        conversation_id="identical-conversation",
        kind=EvidenceKind.OBSERVATION,
        content=f"private marker {identifier}",
        semantics=SemanticState(
            {
                "state": SemanticValue.structured("identical-state"),
                "action": SemanticValue.structured("identical-action"),
                "sequence": SemanticValue.structured(1),
            }
        ),
        provenance=EvidenceProvenance(
            "system_telemetry",
            f"isolation:{identifier}",
            1.0,
            True,
            CREATED_AT,
            "probe",
            verifier="multi-user-isolation-probe",
            verification_status="verified",
            identity="local-isolation-probe",
        ),
        validity=TemporalValidity(valid_from="2026-01-01T00:00:00+00:00"),
        confidence=1.0,
        tenant_id=tenant_id,
        user_id=user_id,
        scope="private",
        role=role,
        authority_level=ROLE_AUTHORITY[role],
        abstraction_level=2,
        profile_revision=1,
        metadata={
            "probe_seed": SEED,
            "ordinal": index,
            "semantic_fixture": "identical-across-all-principals",
        },
        created_at=CREATED_AT,
    )


def concurrent_global_record(index: int) -> EvidenceRecordV2:
    identifier = f"concurrent-global-{index:08d}"
    return EvidenceRecordV2(
        experience_id=identifier,
        evidence_group_id=identifier,
        source_event_id=identifier,
        episode_id="concurrent-write",
        conversation_id="concurrent-write",
        kind=EvidenceKind.OBSERVATION,
        content=f"concurrent global write {index}",
        semantics=SemanticState({"state": SemanticValue.structured("identical-state")}),
        provenance=EvidenceProvenance(
            "system_telemetry",
            f"isolation:{identifier}",
            1.0,
            True,
            CREATED_AT,
            "probe",
            verifier="multi-user-isolation-probe",
            verification_status="verified",
            identity="local-isolation-probe",
        ),
        validity=TemporalValidity(valid_from="2026-01-01T00:00:00+00:00"),
        confidence=1.0,
        scope="global",
        metadata={"probe_seed": SEED, "concurrent_write": True},
        created_at=CREATED_AT,
    )


def effective_profile(tenant_id: str, user_id: str, role: str, authority: int) -> EffectiveProfile:
    fields = {
        "role": PerspectiveField(role, 1.0, "system_identity", user_confirmed=True),
        "authority_level": PerspectiveField(
            authority, 1.0, "system_identity", user_confirmed=True
        ),
        "abstraction_level": PerspectiveField(
            2, 1.0, "system_identity", user_confirmed=True
        ),
    }
    return EffectiveProfile(
        user_id=user_id,
        tenant_id=tenant_id,
        fields=fields,
        profile_revision=1,
    )


def logical_record(item: EvidenceRecordV2) -> dict[str, object]:
    return {
        "experience_id": item.experience_id,
        "group": item.evidence_group_id,
        "event": item.source_event_id,
        "content": item.content,
        "semantics": item.semantics.as_storage(),
        "provenance": item.provenance.as_dict(),
        "validity": item.validity.as_dict(),
        "tenant": item.tenant_id,
        "user": item.user_id,
        "scope": item.scope,
        "role": item.role,
        "authority": item.authority_level,
        "superseded_by": item.superseded_by,
        "invalidated_at": item.invalidated_at,
        "metadata": dict(item.metadata),
        "created_at": item.created_at,
    }


def ledger(store: SQLiteEvidenceStore) -> tuple[int, str]:
    records = store.all()
    return len(records), stable_hash([logical_record(item) for item in records])


def display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def write_result(path: Path, result: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _scoped_checks(
    store: SQLiteEvidenceStore,
    indices: Iterable[int],
    *,
    records: int,
    tenants: int,
) -> dict[str, object]:
    users_per_tenant = records // tenants
    authorized_misses = 0
    cross_tenant_leaks = 0
    cross_user_leaks = 0
    examples: list[dict[str, object]] = []
    authorized_ms: list[float] = []
    attack_ms: list[float] = []

    for index in indices:
        tenant_id, user_id, _ = principal(index, tenants)
        expected_id = f"identity-{index:08d}"

        phase = time.perf_counter()
        authorized = store.eligible_ids(
            tenant_id=tenant_id, user_id=user_id, scopes=("private",)
        )
        authorized_ms.append((time.perf_counter() - phase) * 1000.0)
        if authorized != {expected_id}:
            authorized_misses += 1
            if len(examples) < 20:
                examples.append(
                    {
                        "kind": "authorized_mismatch",
                        "victim": expected_id,
                        "returned": sorted(authorized),
                    }
                )

        tenant_index = index % tenants
        local_user_index = index // tenants
        other_tenant = f"tenant-{(tenant_index + 1) % tenants:06d}"
        phase = time.perf_counter()
        cross_tenant = store.eligible_ids(
            tenant_id=other_tenant, user_id=user_id, scopes=("private",)
        )
        attack_ms.append((time.perf_counter() - phase) * 1000.0)
        if expected_id in cross_tenant:
            cross_tenant_leaks += 1
            if len(examples) < 20:
                examples.append(
                    {
                        "kind": "cross_tenant_leak",
                        "victim": expected_id,
                        "returned": sorted(cross_tenant),
                    }
                )

        other_user = f"user-{(local_user_index + 1) % users_per_tenant:06d}"
        phase = time.perf_counter()
        cross_user = store.eligible_ids(
            tenant_id=tenant_id, user_id=other_user, scopes=("private",)
        )
        attack_ms.append((time.perf_counter() - phase) * 1000.0)
        if expected_id in cross_user:
            cross_user_leaks += 1
            if len(examples) < 20:
                examples.append(
                    {
                        "kind": "cross_user_leak",
                        "victim": expected_id,
                        "returned": sorted(cross_user),
                    }
                )

    return {
        "checks": len(authorized_ms),
        "authorized_misses": authorized_misses,
        "cross_tenant_leaks": cross_tenant_leaks,
        "cross_user_leaks": cross_user_leaks,
        "query_latency_ms": distribution(authorized_ms),
        "attack_query_latency_ms": distribution(attack_ms),
        "examples": examples,
    }


def _role_checks(records: int, tenants: int) -> dict[str, int]:
    policy = ActorPolicy()
    matching_failures = 0
    role_leaks = 0
    authority_leaks = 0
    for index in range(records):
        item = identity_record(index, tenants)
        tenant_id, user_id, role = principal(index, tenants)
        authority = ROLE_AUTHORITY[role]
        matching = policy.evaluate(
            item, effective_profile(tenant_id, user_id, role, authority)
        )
        if matching.applicability is not ProfileApplicability.APPLICABLE:
            matching_failures += 1

        wrong_role = ROLES[(ROLES.index(role) + 1) % len(ROLES)]
        incompatible_role = policy.evaluate(
            item, effective_profile(tenant_id, user_id, wrong_role, authority)
        )
        if incompatible_role.applicability is not ProfileApplicability.PERSPECTIVE_INCOMPATIBLE:
            role_leaks += 1

        incompatible_authority = policy.evaluate(
            item, effective_profile(tenant_id, user_id, role, authority - 1)
        )
        if incompatible_authority.applicability is not ProfileApplicability.PERSPECTIVE_INCOMPATIBLE:
            authority_leaks += 1
    return {
        "checks": records,
        "matching_failures": matching_failures,
        "role_leaks": role_leaks,
        "authority_leaks": authority_leaks,
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    database = args.database.resolve()
    backup = args.backup.resolve()
    if database.exists() or backup.exists():
        raise FileExistsError(
            "Refusing to overwrite preserved probe database/backup; select unused paths."
        )
    database.parent.mkdir(parents=True, exist_ok=True)
    backup.parent.mkdir(parents=True, exist_ok=True)

    append_ms: list[float] = []
    restart_checks: list[dict[str, object]] = []
    store = SQLiteEvidenceStore(database)
    started = time.perf_counter()
    try:
        for index in range(args.records):
            phase = time.perf_counter()
            store.append(identity_record(index, args.tenants))
            append_ms.append((time.perf_counter() - phase) * 1000.0)
            if (index + 1) % args.restart_every == 0 and index + 1 < args.records:
                expected_generation = index + 1
                store.close()
                reopen_started = time.perf_counter()
                store = SQLiteEvidenceStore(database)
                reopen_ms = (time.perf_counter() - reopen_started) * 1000.0
                sentinel = store.get(f"identity-{index:08d}")
                observed_generation = store.generation()
                restart_checks.append(
                    {
                        "records_written": index + 1,
                        "expected_generation": expected_generation,
                        "generation": observed_generation,
                        "sentinel_present": sentinel is not None,
                        "reopen_ms": reopen_ms,
                        "passed": (
                            observed_generation == expected_generation and sentinel is not None
                        ),
                    }
                )

        exhaustive = _scoped_checks(
            store, range(args.records), records=args.records, tenants=args.tenants
        )
        roles = _role_checks(args.records, args.tenants)

        rng = random.Random(SEED)
        sampled = rng.sample(
            range(args.records), min(args.concurrent_read_checks, args.records)
        )
        chunks = [sampled[offset:: args.reader_workers] for offset in range(args.reader_workers)]
        reader_stores = [SQLiteEvidenceStore(database) for _ in range(args.reader_workers)]

        def reader_task(worker: int) -> dict[str, object]:
            return _scoped_checks(
                reader_stores[worker],
                chunks[worker],
                records=args.records,
                tenants=args.tenants,
            )

        def writer_task(indices: Sequence[int]) -> tuple[int, list[float]]:
            latencies: list[float] = []
            for index in indices:
                phase = time.perf_counter()
                store.append(concurrent_global_record(index))
                latencies.append((time.perf_counter() - phase) * 1000.0)
            return len(indices), latencies

        writer_chunks = [
            list(range(worker, args.concurrent_writes, args.writer_workers))
            for worker in range(args.writer_workers)
        ]
        with ThreadPoolExecutor(
            max_workers=args.reader_workers + args.writer_workers
        ) as executor:
            reader_futures = [
                executor.submit(reader_task, worker)
                for worker in range(args.reader_workers)
            ]
            writer_futures = [
                executor.submit(writer_task, chunk) for chunk in writer_chunks
            ]
            concurrent_reader_results = [future.result() for future in reader_futures]
            concurrent_writer_results = [future.result() for future in writer_futures]
        for reader in reader_stores:
            reader.close()

        concurrent_read = {
            "checks": sum(int(item["checks"]) for item in concurrent_reader_results),
            "authorized_misses": sum(
                int(item["authorized_misses"]) for item in concurrent_reader_results
            ),
            "cross_tenant_leaks": sum(
                int(item["cross_tenant_leaks"]) for item in concurrent_reader_results
            ),
            "cross_user_leaks": sum(
                int(item["cross_user_leaks"]) for item in concurrent_reader_results
            ),
        }
        concurrent_write_latencies = [
            latency
            for _, latencies in concurrent_writer_results
            for latency in latencies
        ]
        concurrent_write = {
            "attempted": args.concurrent_writes,
            "completed": sum(count for count, _ in concurrent_writer_results),
            "latency_ms": distribution(concurrent_write_latencies),
        }

        lifecycle_ids = [
            f"identity-{index:08d}" for index in range(args.lifecycle_records)
        ]
        replacement = f"identity-{args.lifecycle_records:08d}"
        store.supersede(lifecycle_ids, replacement)
        invalidated_ids = [
            f"identity-{index:08d}"
            for index in range(args.lifecycle_records, args.lifecycle_records * 2)
        ]
        for identifier in invalidated_ids:
            store.invalidate(identifier, at="2026-09-01T12:30:00+00:00")

        # get is intentionally unscoped. Demonstrate and disclose that this
        # privileged primitive must not be exposed to an untrusted request path.
        raw_victim = "identity-00000000"
        privileged_direct_get_returns_record = store.get(raw_victim) is not None

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
                for identifier in lifecycle_ids
            ) and all(
                restored.get(identifier) is not None
                and restored.get(identifier).invalidated_at
                == "2026-09-01T12:30:00+00:00"
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

    scoped_zero_leakage = (
        exhaustive["authorized_misses"] == 0
        and exhaustive["cross_tenant_leaks"] == 0
        and exhaustive["cross_user_leaks"] == 0
        and roles["matching_failures"] == 0
        and roles["role_leaks"] == 0
        and roles["authority_leaks"] == 0
        and concurrent_read["authorized_misses"] == 0
        and concurrent_read["cross_tenant_leaks"] == 0
        and concurrent_read["cross_user_leaks"] == 0
    )
    all_passed = (
        scoped_zero_leakage
        and concurrent_write["completed"] == args.concurrent_writes
        and before_count == args.records + args.concurrent_writes
        and after_count == before_count
        and after_hash == before_hash
        and restored_generation == generation_before_backup
        and lifecycle_passed
        and all(bool(check["passed"]) for check in restart_checks)
    )
    elapsed = time.perf_counter() - started
    return {
        "schema_version": 1,
        "benchmark": "production_store_100k_principal_isolation_probe",
        "status": "PASS_WITH_BOUNDARY" if all_passed else "FAIL",
        "claim_boundary": (
            "Proves zero leakage only for scoped eligible_ids/query_structured-style "
            "access with trusted tenant/user context plus ActorPolicy role/authority "
            "eligibility. It is not an authentication test; privileged get/get_many "
            "remain deliberately unscoped."
        ),
        "command": [sys.executable, *sys.argv],
        "seed": SEED,
        "config": {
            "records": args.records,
            "synthetic_user_principals": args.records,
            "tenants": args.tenants,
            "local_users_per_tenant": args.records // args.tenants,
            "roles": list(ROLES),
            "restart_every": args.restart_every,
            "lifecycle_records": args.lifecycle_records,
            "concurrent_read_checks": args.concurrent_read_checks,
            "reader_workers": args.reader_workers,
            "concurrent_writes": args.concurrent_writes,
            "writer_workers": args.writer_workers,
            "semantic_state": "identical across all private records",
            "journal_mode": "WAL",
            "synchronous": "FULL",
        },
        "duration_seconds": elapsed,
        "append_latency_ms": distribution(append_ms),
        "restart_checks": restart_checks,
        "exhaustive_scoped_queries": exhaustive,
        "actor_policy": roles,
        "concurrent_read_queries": concurrent_read,
        "concurrent_global_writes": concurrent_write,
        "scoped_zero_leakage": scoped_zero_leakage,
        "privileged_raw_access": {
            "get_is_access_controlled": False,
            "get_many_is_access_controlled": False,
            "direct_get_returns_private_record_by_id": privileged_direct_get_returns_record,
            "deployment_requirement": (
                "Keep raw primitives behind a trusted service boundary and derive "
                "tenant_id/user_id from authenticated server-side context."
            ),
        },
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
        "database": display_path(database),
        "backup": display_path(backup),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=100_000)
    parser.add_argument("--tenants", type=int, default=1_000)
    parser.add_argument("--restart-every", type=int, default=25_000)
    parser.add_argument("--lifecycle-records", type=int, default=100)
    parser.add_argument("--concurrent-read-checks", type=int, default=10_000)
    parser.add_argument("--reader-workers", type=int, default=8)
    parser.add_argument("--concurrent-writes", type=int, default=800)
    parser.add_argument("--writer-workers", type=int, default=4)
    parser.add_argument(
        "--database",
        type=Path,
        default=(
            ROOT
            / "breakthrough_eval"
            / "reliability"
            / "run_data"
            / "multi_user_100k.sqlite"
        ),
    )
    parser.add_argument(
        "--backup",
        type=Path,
        default=(
            ROOT
            / "breakthrough_eval"
            / "reliability"
            / "run_data"
            / "multi_user_100k_backup.sqlite"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            ROOT
            / "breakthrough_eval"
            / "reliability"
            / "MULTI_USER_100K_ISOLATION.json"
        ),
    )
    args = parser.parse_args()
    positive = (
        args.records,
        args.tenants,
        args.restart_every,
        args.lifecycle_records,
        args.concurrent_read_checks,
        args.reader_workers,
        args.concurrent_writes,
        args.writer_workers,
    )
    if any(value <= 0 for value in positive):
        parser.error("all numeric arguments must be positive")
    if args.records % args.tenants:
        parser.error("records must be divisible by tenants")
    if args.records // args.tenants < 2:
        parser.error("at least two local users per tenant are required")
    if args.tenants < 2:
        parser.error("at least two tenants are required")
    if args.lifecycle_records * 2 >= args.records:
        parser.error("lifecycle-records must leave ordinary records")
    return args


def main() -> int:
    args = parse_args()
    try:
        result = run(args)
    except Exception as exc:
        result = {
            "schema_version": 1,
            "benchmark": "production_store_100k_principal_isolation_probe",
            "status": "ERROR",
            "error": f"{type(exc).__name__}: {exc}",
            "command": [sys.executable, *sys.argv],
        }
        write_result(args.output, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    write_result(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS_WITH_BOUNDARY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
